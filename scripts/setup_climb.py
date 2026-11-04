"""Hill climb the setup experience: how cheaply a cheap model connects a new source, and how often right.

Each evaluation builds treedist from the working tree into a fresh environment, as `pip install`
would, makes one `treedist init` folder per task and run, and lets a cheap model connect the
source with the Claude Code CLI, headless, from inside that folder. It sees only what a pip user
sees: the installed package, the folder's AGENTS.md and the task. The source description it
writes is graded against the hidden answer with portability_bench, and the run's cost is logged
to climb/setup_logg.jsonl.

    uv run python scripts/setup_climb.py prova --not "baslinje" [--uppgifter dev|kontroll] [--korningar 2]
    uv run python scripts/setup_climb.py jamfor ID [ID]        a run, or a candidate against a baseline
    uv run python scripts/setup_climb.py friktion ID           where the turns went

A step changes one thing a cheap model meets on the way (AGENTS.md, what `init` writes, what
`check` and `run` print), and is kept only if no task fails that passed before and the cost
falls by more than the noise. Decisions use the development tasks; the control tasks, other
sources and other seeds, only check the finished climb.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import portability_bench as bench

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "climb" / "setup_logg.jsonl"
WORK = Path(os.environ.get("TREEDIST_KLATTRING", "/tmp/treedist-setup-climb"))

TASKS = {
    "dev": {**bench.VARIANTS, **bench.PLATFORMS, **bench.HISTORY},
    "kontroll": {**bench.CONTROL, **bench.PLATFORM_CONTROL, **bench.HISTORY_CONTROL},
}
MODEL = "haiku"
# Shell commands run in Claude Code's sandbox, which keeps writes inside the project folder and has no
# network, so compound commands need no allow-list entry of their own.
SANDBOX = {"sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True}}
# Everything else is refused without asking: the model reads, writes its source description and runs treedist.
ALLOWED = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(treedist:*)", "Bash(python:*)", "Bash(python3:*)",
           "Bash(ls:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(cat:*)", "Bash(wc:*)", "Bash(file:*)", "Bash(cd:*)",
           "Bash(find:*)", "Bash(grep:*)", "Bash(sort:*)", "Bash(echo:*)", "Bash(sqlite3:*)"]
PARALLEL = 6
TIMEOUT_S = 1200
BUDGET_USD = 3.0
# What a person would type: the task, nothing about how treedist works.
PROMPT = "Koppla in källan i kallor/{task} till treedist. Uppgiften står i kallor/{task}/UPPGIFT.md."
# Score per task: mean cost plus this much per failed run, about ten runs' worth: a setup that
# ends wrong costs a person far more than a slow one. A step must cut the score by this many
# standard errors, and by at least this share.
FAILURE_USD = 0.25
SIGNIFICANCE = 2.0
MIN_GAIN = 0.05


def _git() -> str:
    rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "src", "AGENTS.md", "examples", "modeller"],
                           cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return rev + ("+ändrad" if dirty else "")


def _install(run_dir: Path, ref: str | None) -> Path:
    """The working tree, or a commit, as a pip user would get it: a wheel in a fresh environment."""
    dist, venv, source = run_dir / "dist", run_dir / "venv", ROOT
    if ref:
        source = run_dir / "kod"
        subprocess.run(["git", "worktree", "add", "--detach", "-q", str(source), ref], cwd=ROOT, check=True)
    subprocess.run(["uv", "build", "--wheel", "-q", "--out-dir", str(dist)], cwd=source, check=True)
    if ref:
        subprocess.run(["git", "worktree", "remove", "--force", str(source)], cwd=ROOT, check=True)
    subprocess.run(["uv", "venv", "-q", str(venv)], check=True)
    wheel = next(dist.glob("treedist-*.whl"))
    subprocess.run(["uv", "pip", "install", "-q", "--python", str(venv / "bin" / "python"), str(wheel)], check=True)
    return venv / "bin"


def _one(bin_dir: Path, tasks_dir: Path, project: Path, task: str) -> dict:
    project.mkdir(parents=True)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "VIRTUAL_ENV": str(bin_dir.parent)}
    subprocess.run(["treedist", "init", "."], cwd=project, env=env, check=True, capture_output=True)
    shutil.copytree(tasks_dir / "uppgifter" / task, project / "kallor" / task)
    command = [
        "claude", "-p", PROMPT.format(task=task), "--model", MODEL, "--output-format", "stream-json", "--verbose",
        "--permission-mode", "dontAsk", "--allowedTools", *ALLOWED, "--settings", json.dumps(SANDBOX),
        "--strict-mcp-config", "--setting-sources", "project",
        "--no-session-persistence", "--max-budget-usd", str(BUDGET_USD),
    ]
    start = time.time()
    # The model's every step, kept beside the project and out of its sight, for `friktion`.
    transcript = project.parent.parent / "logg" / f"{project.name}.jsonl"
    transcript.parent.mkdir(exist_ok=True)
    try:
        done = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
        transcript.write_text(done.stdout)
        events = [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")]
        result = next((e for e in reversed(events) if e.get("type") == "result"), None) or {
            "is_error": True, "result": done.stderr[-500:]}
    except subprocess.TimeoutExpired:
        result = {"is_error": True, "result": "tidsgräns"}
    failure = bench.grade_task(project / "kallor" / task, tasks_dir / "facit" / task)
    usage = result.get("usage", {})
    return {
        "uppgift": task,
        "godkand": failure is None,
        "fel": failure,
        "kostnad_usd": result.get("total_cost_usd"),
        "turer": result.get("num_turns"),
        "sekunder": round(time.time() - start),
        "tokens_in": sum(usage.get(k, 0) or 0 for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")),
        "tokens_ut": usage.get("output_tokens"),
        "avbruten": bool(result.get("is_error")),
        "nekade": len(result.get("permission_denials") or []),
        "nekat": sorted({str(d.get("tool_input", {}).get("command", d.get("tool_name")))[:80]
                         for d in result.get("permission_denials") or []})[:5],
        "svar": (result.get("result") or "")[-1500:],
        "katalog": str(project),
    }


def prova(note: str, which: str, runs: int, only: list[str] | None, ref: str | None = None) -> str:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    run_dir = WORK / run_id
    tasks = {k: v for k, v in TASKS[which].items() if not only or k in only}
    tasks_dir = run_dir / "bank"
    bench.make(tasks_dir, tasks)
    bin_dir = _install(run_dir, ref)
    jobs = [(task, k) for k in range(runs) for task in tasks]
    with ThreadPoolExecutor(PARALLEL) as pool:
        rows = list(pool.map(lambda job: _one(bin_dir, tasks_dir, run_dir / "prov" / f"{job[0]}-{job[1]}", job[0]), jobs))
    meta = {"id": run_id, "kod": ref or _git(), "not": note, "uppgifter": which, "modell": MODEL}
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps({**meta, **row}, ensure_ascii=False) + "\n")
    _summary(pd.DataFrame(rows), run_id, note)
    return run_id


def _load(run_id: str) -> pd.DataFrame:
    rows = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    frame = pd.DataFrame([r for r in rows if r["id"] == run_id])
    if frame.empty:
        raise SystemExit(f"Ingen körning {run_id} i {LOG}")
    return frame


def _summary(frame: pd.DataFrame, run_id: str, note: str) -> None:
    invalid = len(frame) - len(_valid(frame))
    frame = _valid(frame)
    per_task = frame.groupby("uppgift").agg(godkanda=("godkand", "sum"), korningar=("godkand", "size"),
                                            kostnad=("kostnad_usd", "mean"), turer=("turer", "mean"),
                                            sekunder=("sekunder", "mean"), nekade=("nekade", "mean"))
    print(f"\n{run_id}  {note}")
    print(per_task.round(3).to_string())
    print(f"Poäng {_per_task(frame)['poang'].mean():.3f} USD per uppgift. "
          f"Godkända {int(frame['godkand'].sum())} av {len(frame)}, kostnad {frame['kostnad_usd'].mean():.3f} USD, "
          f"{frame['turer'].mean():.1f} turer och {frame['sekunder'].mean():.0f} s per körning"
          + (f"; {invalid} ogiltiga, stoppade av testets behörigheter" if invalid else ""))
    for row in frame[~frame["godkand"]].itertuples():
        print(f"  UNDERKÄND {row.uppgift}: {row.fel}")


def jamfor(base_id: str, cand_id: str | None) -> None:
    base = _load(base_id)
    if cand_id is None:
        _summary(base, base_id, base["not"].iloc[0])
        return
    cand = _load(cand_id)
    _summary(base, base_id, base["not"].iloc[0])
    _summary(cand, cand_id, cand["not"].iloc[0])
    b, c = _per_task(base), _per_task(cand)
    both = b.add_suffix("_bas").join(c.add_suffix("_kand"), how="inner")
    diff = both["poang_kand"] - both["poang_bas"]
    se = float(diff.std(ddof=1) / np.sqrt(len(diff)))
    share = float(diff.mean() / both["poang_bas"].mean())
    better = float(diff.mean()) < -SIGNIFICANCE * se and share < -MIN_GAIN
    print(f"\nPoäng per uppgift (kostnad + {FAILURE_USD} USD per underkänd), kandidat mot bas: "
          f"{diff.mean():+.3f} ± {se:.3f} USD ({share:+.0%})")
    print(f"Godkända {int(_valid(cand)['godkand'].sum())} av {len(_valid(cand))} mot {int(_valid(base)['godkand'].sum())} av {len(_valid(base))}; kostnad "
          f"{(both['kostnad_kand'] - both['kostnad_bas']).mean():+.4f} USD och turer "
          f"{(both['turer_kand'] - both['turer_bas']).mean():+.1f} per körning")
    print("BÄTTRE: ta steget" if better else "Inte bättre: behåll basen")


def _valid(frame: pd.DataFrame) -> pd.DataFrame:
    """Runs that stopped on the test's own permission refusal, before writing anything, say nothing about treedist."""
    stopped = (frame["fel"] == "ingen källbeskrivning") & (frame.get("nekade", 0) > 0)
    return frame[~stopped]


def _per_task(frame: pd.DataFrame) -> pd.DataFrame:
    per = _valid(frame).groupby("uppgift").agg(godkand=("godkand", "mean"), kostnad=("kostnad_usd", "mean"), turer=("turer", "mean"))
    return per.assign(poang=per["kostnad"] + FAILURE_USD * (1 - per["godkand"]))


def friktion(run_id: str) -> None:
    """Where the turns went: what the model ran, how often treedist said FEL, and which calls failed."""
    frame = _load(run_id)
    calls, errors = [], []
    for row in frame.itertuples():
        transcript = Path(row.katalog).parent.parent / "logg" / f"{Path(row.katalog).name}.jsonl"
        if not transcript.exists():
            continue
        for line in transcript.read_text().splitlines():
            event = json.loads(line) if line.startswith("{") else {}
            message = event.get("message") if isinstance(event.get("message"), dict) else {}
            for part in message.get("content") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "tool_use":
                    command = part["input"].get("command", "")
                    words = command.split()
                    kind = part["name"] if not words else "Bash " + " ".join(words[:2] if words[0] == "treedist" else words[:1])
                    calls.append({"uppgift": row.uppgift, "verktyg": kind, "fil": part["input"].get("file_path", "")})
                elif part.get("type") == "tool_result" and part.get("is_error"):
                    text = part.get("content")
                    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
                    errors.append(text[:120].replace("\n", " "))
    calls = pd.DataFrame(calls)
    if calls.empty:
        raise SystemExit("Inga loggar för körningen")
    runs = len(frame)
    print(f"Verktygsanrop per körning, {runs} körningar:")
    print((calls["verktyg"].value_counts() / runs).round(2).head(15).to_string())
    read = calls[calls["verktyg"] == "Read"]["fil"].map(lambda f: Path(f).name).value_counts() / runs
    print("\nLästa filer per körning:")
    print(read.round(2).head(10).to_string())
    print(f"\nMisslyckade verktygsanrop: {len(errors) / runs:.1f} per körning. Vanligast:")
    for text, count in pd.Series(errors).value_counts().head(8).items():
        print(f"  {count}× {text}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("prova")
    run.add_argument("--not", dest="note", required=True)
    run.add_argument("--uppgifter", choices=list(TASKS), default="dev")
    run.add_argument("--korningar", type=int, default=2)
    run.add_argument("--bara", nargs="*", help="Bara dessa uppgifter")
    run.add_argument("--kod", help="Pröva en commit i stället för arbetskatalogen, till exempel baslinjen")
    compare = commands.add_parser("jamfor")
    compare.add_argument("ids", nargs="+")
    friction = commands.add_parser("friktion", help="Vad modellen lade turerna på i en körning")
    friction.add_argument("id")
    args = parser.parse_args()
    if args.command == "prova":
        prova(args.note, args.uppgifter, args.korningar, args.bara, args.kod)
    elif args.command == "friktion":
        friktion(args.id)
    else:
        jamfor(args.ids[0], args.ids[1] if len(args.ids) > 1 else None)


if __name__ == "__main__":
    main()
