"""Hill climb towards a better method, one judged change at a time.

A candidate is a set of Config overrides. It is scored against the current best
on the same simulations (paired), and taken only if it is better by more than
the noise between seeds. The development seeds are used for every decision; the
control seeds only to check a finished climb, so that the climb cannot tune
itself to them. Every evaluation is appended to climb/logg.jsonl, and the
current best lives in climb/basta.json.

    uv run python scripts/climb.py params --budget 40     climb the parameters automatically
    uv run python scripts/climb.py compare --set k=v      judge one change, e.g. a new flag
    uv run python scripts/climb.py holdout                the best against the defaults, on control seeds
    uv run python scripts/climb.py status                 the best so far and the latest entries

Structural changes go behind a Config flag that defaults to off; see
.claude/skills/metod-klattring/SKILL.md for the loop.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import fields, replace
from pathlib import Path

import numpy as np
import pandas as pd
from compare_methods import _month_scores, _run_ledger

from treedist.dev.backtest import _score
from treedist.config import Config
from treedist.core.invoice import PriceList
from treedist.dev.simulate import SimParams, example_price_list, simulate

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "climb"
BEST = STATE / "basta.json"
LOG = STATE / "logg.jsonl"

# Each scenario stands for something we are unsure of in reality. The last one
# keeps the climb from leaning on the simulator's link between size and mill.
SCENARIOS = {
    "bas": {},
    "30 % utan skördardata": {"no_harvester_data_share": 0.30},
    "stora skillnader inom AO": {"landing_diameter_sd": 0.20},
    "destination oberoende av grovlek": {"destination_noise": 1.0},
}
DEV_SEEDS = (301, 302, 303, 304, 305, 306)
HOLDOUT_SEEDS = (401, 402, 403, 404, 405, 406, 407, 408)
MONTHS = 12
MC_DRAWS = 300

# One percentage point of coverage away from 90 % costs as much as 0.3 kr/m3fub of price error.
CALIBRATION_WEIGHT = 0.3
NOMINAL = 0.90
# A change must beat the noise between seeds by this many standard errors, and gain at least this much.
SIGNIFICANCE = 2.0
MIN_GAIN = 0.05
# A simplification may cost at most this much in score per step. The budget for a
# whole simplification climb is SIMPLIFY_BUDGET, counted from where it started.
SIMPLIFY_TOLERANCE = 0.25
SIMPLIFY_BUDGET = 1.0

# Parameters the climb may move: step kind, step, lower and upper bound. Calibration from
# published sources (harvester_bias, handling_loss) and the volume error model stay out:
# the simulator was built from the same numbers, so climbing them would only fit it.
PARAMS = {
    "donor_destination_weight": ("mul", 2.0, 1.0, 256.0),
    "donor_group_weight": ("mul", 2.0, 1.0, 64.0),
    "donor_sibling_cm": ("mul", 1.5, 0.25, 8.0),
    "pool_min_pairs": ("add", 1, 2, 10),
    "design_effect": ("mul", 1.5, 5.0, 1000.0),
    "pool_remaining_share": ("add", 0.15, 0.1, 0.9),
}


def _job(args: tuple[dict, str, int]) -> dict:
    overrides, scenario, seed = args
    cfg = replace(Config(mc_draws=MC_DRAWS), **overrides)
    prices = PriceList.from_frame(example_price_list())
    months = simulate(SimParams(months=MONTHS, seed=seed, **SCENARIOS[scenario]))
    rows = []

    def collect(month, output) -> None:
        scores = _month_scores(output.step.allocation, month.truth, prices)
        covered = [_score(month, m, prices, None) for m in output.matrices.values() if m.delivered.sum() > 0]
        scores["varde_90"] = float(np.mean([c["varde_inom_90"] for c in covered]))
        rows.append(scores)

    _run_ledger(months, cfg, prices, True, collect)
    month = pd.DataFrame(rows).mean()
    score = month["prisfel"] + CALIBRATION_WEIGHT * abs(month["varde_90"] - NOMINAL) * 100
    return {
        "scenario": scenario,
        "seed": seed,
        "prisfel": float(month["prisfel"]),
        "felindex": float(month["index_matris"]),
        "varde_90": float(month["varde_90"]),
        "poang": float(score),
    }


def evaluate(pool: ProcessPoolExecutor, candidates: list[dict], seeds) -> list[pd.DataFrame]:
    """Per-simulation results for each candidate, all run in one pool."""
    jobs = [(c, s, seed) for c in candidates for s in SCENARIOS for seed in seeds]
    results = list(pool.map(_job, jobs))
    per = len(SCENARIOS) * len(seeds)
    return [pd.DataFrame(results[i * per : (i + 1) * per]) for i in range(len(candidates))]


def judge(base: pd.DataFrame, candidate: pd.DataFrame) -> dict:
    """Paired difference in score: negative is better."""
    diff = candidate["poang"].to_numpy() - base["poang"].to_numpy()
    se = float(diff.std(ddof=1) / np.sqrt(len(diff)))
    mean = float(diff.mean())
    return {
        "diff": round(mean, 3),
        "se": round(se, 3),
        "battre": mean < -max(SIGNIFICANCE * se, MIN_GAIN),
        "per_scenario": candidate.groupby("scenario")["prisfel"].mean().sub(
            base.groupby("scenario")["prisfel"].mean()
        ).round(2).to_dict(),
    }


def summary(frame: pd.DataFrame) -> dict:
    return {
        "poang": round(float(frame["poang"].mean()), 3),
        "prisfel": round(float(frame["prisfel"].mean()), 2),
        "felindex": round(float(frame["felindex"].mean()), 4),
        "varde_90": round(float(frame["varde_90"].mean()), 3),
    }


def _git() -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        dirty = subprocess.run(["git", "status", "--porcelain", "src"], cwd=ROOT, capture_output=True, text=True)
        return rev.stdout.strip() + ("+ändrad" if dirty.stdout.strip() else "")
    except OSError:
        return "okänd"


def log(entry: dict) -> None:
    STATE.mkdir(exist_ok=True)
    entry = {"tid": time.strftime("%Y-%m-%d %H:%M"), "kod": _git(), **entry}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_best() -> dict:
    return json.loads(BEST.read_text(encoding="utf-8")) if BEST.exists() else {"overrides": {}}


def save_best(overrides: dict, result: dict, reason: str) -> None:
    STATE.mkdir(exist_ok=True)
    BEST.write_text(
        json.dumps({"overrides": overrides, "utveckling": result, "skal": reason, "kod": _git()}, indent=2,
                   ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    toml = "\n".join(f"{k} = {json.dumps(v)}" for k, v in sorted(overrides.items()))
    (STATE / "basta.toml").write_text(toml + "\n", encoding="utf-8")


def _step(name: str, value, scale: float, direction: int):
    kind, step, low, high = PARAMS[name]
    if kind == "mul":
        moved = value * step**scale if direction > 0 else value / step**scale
    else:
        moved = value + direction * step * scale
    moved = min(max(moved, low), high)
    return int(round(moved)) if isinstance(step, int) else round(float(moved), 4)


def climb_params(budget: int) -> None:
    defaults = Config()
    best = load_best()["overrides"]
    scale = 1.0
    used = 0
    with ProcessPoolExecutor() as pool:
        (base,) = evaluate(pool, [best], DEV_SEEDS)
        print(f"Start: {summary(base)}  {best or 'standardvärden'}")
        while used < budget:
            accepted = False
            for name in np.random.default_rng(used).permutation(list(PARAMS)):
                if used >= budget:
                    break
                current = best.get(name, getattr(defaults, name))
                moves = {_step(name, current, scale, d) for d in (-1, 1)} - {current}
                if not moves:
                    continue
                candidates = [{**best, name: m} for m in sorted(moves)]
                results = evaluate(pool, candidates, DEV_SEEDS)
                used += len(candidates)
                verdicts = [judge(base, r) for r in results]
                for c, r, v in zip(candidates, results, verdicts):
                    log({"typ": "parameter", "andring": {name: c[name]}, "kandidat": c, **summary(r), **v})
                    print(f"  {name} {current} -> {c[name]}: diff {v['diff']:+.3f} ± {v['se']:.3f}"
                          f"{'  TAGEN' if v['battre'] else ''}")
                winner = min(range(len(candidates)), key=lambda i: verdicts[i]["diff"])
                if verdicts[winner]["battre"]:
                    best, base = candidates[winner], results[winner]
                    save_best(best, summary(base), f"{name} {current} -> {best[name]}")
                    accepted = True
            if not accepted:
                if scale < 0.5:
                    break
                scale /= 2
                print(f"Inget steg togs; halverar stegen till {scale}.")
    print(f"Slut efter {used} kandidater: {summary(base)}  {best}")


def _parse(sets: list[str]) -> dict:
    change = {}
    known = {f.name for f in fields(Config)}
    for item in sets:
        key, _, raw = item.partition("=")
        if key not in known:
            raise SystemExit(f"Okänd parameter: {key}")
        change[key] = json.loads(raw) if raw not in ("true", "false") else raw == "true"
    return change


def compare(sets: list[str], note: str, take: bool) -> None:
    best = load_best()["overrides"]
    change = _parse(sets)
    candidate = {**best, **change}
    with ProcessPoolExecutor() as pool:
        base, result = evaluate(pool, [best, candidate], DEV_SEEDS)
    verdict = judge(base, result)
    log({"typ": "jamforelse", "andring": change, "anteckning": note, "kandidat": candidate, **summary(result),
         **verdict})
    print(f"Bäst hittills: {summary(base)}")
    print(f"Kandidat:      {summary(result)}")
    print(f"Skillnad {verdict['diff']:+.3f} ± {verdict['se']:.3f} -> {'BÄTTRE' if verdict['battre'] else 'inte bättre'}")
    print(f"Prisfel per scenario, ändring: {verdict['per_scenario']}")
    if take and verdict["battre"]:
        save_best(candidate, summary(result), note or str(change))
        print("Sparad som bäst.")


def simplify(candidates: list[str], note: str) -> None:
    """Screen removals against the best: each `candidate` is a comma separated set of k=v.

    A removal is acceptable when it costs at most SIMPLIFY_TOLERANCE in score.
    Unlike `compare`, nothing has to be gained: the point is fewer parts.
    """
    best = load_best()["overrides"]
    changes = [_parse(c.split(",")) for c in candidates]
    with ProcessPoolExecutor() as pool:
        base, *results = evaluate(pool, [best, *({**best, **c} for c in changes)], DEV_SEEDS)
    print(f"Bäst hittills: {summary(base)}")
    for change, result in zip(changes, results):
        verdict = judge(base, result)
        acceptable = verdict["diff"] <= SIMPLIFY_TOLERANCE
        log({"typ": "forenkling", "andring": change, "anteckning": note, "kandidat": {**best, **change},
             **summary(result), **verdict, "godtagbar": acceptable})
        print(f"{change}: {summary(result)}  skillnad {verdict['diff']:+.3f} ± {verdict['se']:.3f}"
              f" -> {'godtagbar' if acceptable else 'för dyr'}  {verdict['per_scenario']}")


def holdout(against: list[str]) -> None:
    """The best against the defaults, or against `against`: the settings that undo the steps to check."""
    best = load_best()["overrides"]
    reference = _parse(against)
    with ProcessPoolExecutor() as pool:
        default, result = evaluate(pool, [reference, best], HOLDOUT_SEEDS)
    verdict = judge(default, result)
    log({"typ": "kontroll", "kandidat": best, "mot": reference, "standard": summary(default), **summary(result),
         **verdict})
    print(f"Jämförelse:     {summary(default)}  {reference or 'standardvärden'}")
    print(f"Bästa:          {summary(result)}  {best}")
    print(f"Skillnad {verdict['diff']:+.3f} ± {verdict['se']:.3f} -> {'håller' if verdict['battre'] else 'håller inte'}")
    print(f"Prisfel per scenario, ändring: {verdict['per_scenario']}")


def status() -> None:
    print(json.dumps(load_best(), indent=2, ensure_ascii=False))
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines()[-10:]:
            e = json.loads(line)
            print(f"{e['tid']} {e['typ']:10s} {e.get('andring', '')} diff {e.get('diff')} ± {e.get('se')} "
                  f"{'tagen' if e.get('battre') else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    params = commands.add_parser("params", help="Klättra i parametrarna")
    params.add_argument("--budget", type=int, default=40, help="Högst så många kandidater")
    comp = commands.add_parser("compare", help="Bedöm en ändring mot bästa hittills")
    comp.add_argument("--set", action="append", default=[], metavar="NYCKEL=VÄRDE")
    comp.add_argument("--note", default="")
    comp.add_argument("--take", action="store_true", help="Spara som bäst om den är bättre")
    hold = commands.add_parser("holdout", help="Bästa mot standardvärden på kontrollfrön")
    hold.add_argument("--mot", action="append", default=[], metavar="NYCKEL=VÄRDE",
                      help="Jämför i stället mot detta, t.ex. strukturella steg avstängda")
    simp = commands.add_parser("forenkla", help="Pröva borttagningar som får kosta lite")
    simp.add_argument("kandidater", nargs="+", metavar="NYCKEL=VÄRDE[,NYCKEL=VÄRDE]")
    simp.add_argument("--note", default="")
    commands.add_parser("status", help="Visa bästa och senaste försöken")
    args = parser.parse_args()

    if args.command == "params":
        climb_params(args.budget)
    elif args.command == "compare":
        compare(args.set, args.note, args.take)
    elif args.command == "holdout":
        holdout(args.mot)
    elif args.command == "forenkla":
        simplify(args.kandidater, args.note)
    else:
        status()


if __name__ == "__main__":
    main()
