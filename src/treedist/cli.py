"""Command line entry point."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import io
import shutil
import sys
import tempfile
import traceback
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .dev.backtest import run_backtest
from .dev.model import load_model
from . import __version__, adapters, contract, resources, sent
from .check import FEL, check, felled_after_text, outside_text
from .config import Config, load_config
from .core.ledger import load_for_period, previous_period
from .core.pipeline import run_month
from .appendix import APPENDIX_STYLES, DIAMETER_FLOORS, AppendixLayout
from .bilaga import tier_volumes
from .report import DEVELOPER_DIR, slug, write_month
from .schema import AO, DEST, DONE
from .dev.simulate import SimParams, simulate


def _config(args: argparse.Namespace) -> Config:
    # With both, the configuration file changes some of the saved model's parameters.
    return load_config(args.config, base=resources.model(args.modell) if args.modell else None)


def _run(args: argparse.Namespace) -> int:
    cfg = _config(args)
    ledger = load_for_period(args.state, args.period)
    if ledger.period is None:
        print(f"Ny liggare: ingen månad före {args.period} är körd. Månaden behöver all skördardata som rapporterats "
              "hittills, också för virke som fälldes tidigare.")

    inputs = adapters.load(args.period, args.kalla, _files(args))
    diameter = DIAMETER_FLOORS if args.bilaga_diameter is None else _floors(args.bilaga_diameter)
    layout = AppendixLayout(args.bilaga, diameter, _floors(args.bilaga_langd))
    # What earlier months sent: a repeated load, a cumulative harvest or a new calibration stops the month here.
    found = sent.problems(args.state, args.period, inputs, cfg, layout, args.tillat_ny_kalibrering)
    stops = [text for level, text in found if level == sent.FEL]
    if stops:
        for text in stops:
            print(f"Fel: {text}", file=sys.stderr)
        print(f"{args.period} kördes inte; inget har sparats.", file=sys.stderr)
        return 1
    output = run_month(ledger, inputs.harvest, inputs.deliveries, args.period, inputs.transport_done, cfg)
    sources = {"kalla": args.kalla, **inputs.sources} if args.kalla else inputs.sources
    write_month(output, args.out, cfg, sources, layout, inputs.harvest, inputs.facts, args.utvecklare)
    output.step.ledger.save(args.state)
    sent.save(args.state, args.period, inputs, cfg, layout, output.step.closed)
    changed = _source_changed(args.state, args.period, args.kalla)

    print(f"{args.period}: utdata i {args.out}")
    for destination, lines in output.invoice.groupby(DEST):
        delivered = lines.loc[lines["radtyp"] == "LEVERANS", "volym_m3fub"].sum()
        print(f"  {destination}: {delivered:.3f} m3fub levererat, bilaga i bilagor/{slug(destination)}.html")
    apart = outside_text(inputs)
    if apart:
        print(f"OBS: {apart}")
    if changed:
        print(f"OBS: {changed}")
    for _, text in found:
        print(f"OBS: {text}")
    if output.step.felled_after:
        delivered = float(inputs.deliveries.loc[inputs.deliveries["volym_m3fub"] > 0, "volym_m3fub"].sum())
        print(f"OBS: {felled_after_text(output.step.felled_after, delivered)}")
    if args.utvecklare:
        _developer_notes(output, cfg, args.out)
    return 0


def _developer_notes(output, cfg: Config, out: Path) -> None:
    """What --utvecklare adds on screen: where each mill's volume came from, and what differs from the standard model."""
    print(f"Utvecklare: matriser, fördelning per avtalsobjekt och bilagan som text i {out / DEVELOPER_DIR}")
    for destination, volumes in tier_volumes(output).iterrows():
        parts = ", ".join(f"{tier} {volume:.3f}" for tier, volume in volumes.items())
        print(f"  {destination}: {parts} m3fub")
    standard = asdict(Config())
    differs = [f"{name} = {value}" for name, value in asdict(cfg).items() if value != standard[name]]
    print("  Parametrar som skiljer från standardmodellen: " + (", ".join(differs) if differs else "inga"))


# In place of floors: show the classes as the input has them, without groups.
CLASSES = "klasser"


def _floors(text: str | None) -> tuple[int, ...]:
    if not text or text.strip().lower() == CLASSES:
        return ()  # The classes as the input has them.
    try:
        return tuple(int(part) for part in text.replace(" ", "").split(",") if part)
    except ValueError:
        raise ValueError(f"Ange gränserna som heltal i cm med komma emellan, till exempel 340,370,400: {text!r}") from None


def _source_changed(state: Path, period: str, source: Path | None) -> str:
    """Remember which source description ran the month, and say if it differs from last month's.

    A changed adapter between months is often intended, but a run with an older copy is easy to miss.
    """
    if source is None:
        return ""
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (state / period / "kalla.json").write_text(json.dumps({"fil": str(source), "sha256": digest}) + "\n", encoding="utf-8")
    before = state / previous_period(period) / "kalla.json"
    if not before.exists() or json.loads(before.read_text(encoding="utf-8"))["sha256"] == digest:
        return ""
    return f"källbeskrivningen {source.name} har ändrats sedan {previous_period(period)}; kontrollera att ändringen är avsedd"


def _browser() -> str | None:
    """Edge or Chrome, which print HTML to PDF headless; TREEDIST_BROWSER overrides."""
    candidates = [os.environ.get("TREEDIST_BROWSER", "")]
    for root in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""), os.environ.get("LOCALAPPDATA", "")):
        if root:
            candidates += [rf"{root}\Microsoft\Edge\Application\msedge.exe", rf"{root}\Google\Chrome\Application\chrome.exe"]
    candidates += ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    candidates += [shutil.which(name) or "" for name in ("msedge", "microsoft-edge", "google-chrome", "chromium", "chrome")]
    return next((c for c in candidates if c and Path(c).exists()), None)


# Ways to ask a browser for a PDF, best first. Versions differ in which flags they know, and a flag one
# version rejects can stop it from writing anything; the last way prints the browser's own header and footer.
# A fresh profile keeps a browser that is already open from taking the job, but some installations refuse it.
_PDF_FLAGS = [
    ["--headless=new", "--disable-gpu", "--no-pdf-header-footer", "PROFILE"],
    ["--headless=new", "--disable-gpu", "--no-pdf-header-footer"],
    ["--headless", "--disable-gpu", "--print-to-pdf-no-header"],
    ["--headless", "--disable-gpu"],
]


def _print_pdf(browser: str, flags: list[str], page: Path, pdf: Path) -> tuple[int, str]:
    """Pages written, and what the browser said."""
    pdf.unlink(missing_ok=True)
    # Absolute paths, and the page as a plain path rather than a file:/// URL: that is what works headless.
    with tempfile.TemporaryDirectory() as profile:
        flags = [f"--user-data-dir={profile}" if flag == "PROFILE" else flag for flag in flags]
        try:
            done = subprocess.run([browser, *flags, f"--print-to-pdf={pdf}", str(page)],
                                  capture_output=True, text=True, timeout=120)
            said = (done.stderr or done.stdout or "").strip()
        except subprocess.TimeoutExpired:
            said = "inget svar på 120 sekunder"
    pages = len(re.findall(rb"/Type\s*/Page\b", pdf.read_bytes())) if pdf.exists() else 0
    return pages, said


def _pdf(args: argparse.Namespace) -> int:
    """Print each appendix's HTML to PDF next to it, and check that every file came out with pages."""
    pages = sorted((args.out / "bilagor").glob("*.html"))
    if not pages:
        raise FileNotFoundError(f"Inga bilagor i {args.out / 'bilagor'}; kör treedist run först")
    browser = _browser()
    if browser is None:
        raise FileNotFoundError("Hittar varken Edge eller Chrome; ange webbläsaren i TREEDIST_BROWSER")
    ways, failed = list(_PDF_FLAGS), 0
    for page in pages:
        pdf, said = page.with_suffix(".pdf").resolve(), ""
        for flags in list(ways):
            count, said = _print_pdf(browser, flags, page.resolve(), pdf)
            if count:
                print(f"{pdf}: {count} sidor" + (", med webbläsarens sidhuvud" if flags is _PDF_FLAGS[-1] else ""))
                break
            ways.remove(flags)  # A way that failed once fails for the next page too.
        else:
            failed += 1
            print(f"Fel: ingen PDF för {page}. {browser} svarade: {said[-500:] or 'inget'}", file=sys.stderr)
            ways = list(_PDF_FLAGS)
    return 1 if failed else 0


def _files(args: argparse.Namespace) -> dict[str, Path | None]:
    if args.kalla is None and not (args.produktion and args.matning):
        raise ValueError("Ange --kalla, eller --produktion och --matning")
    return {
        "produktion": args.produktion,
        "matning": args.matning,
        "avtalsobjekt": args.avtalsobjekt,
        "avverkningsformer": args.avverkningsformer,
    }


def _check(args: argparse.Namespace) -> int:
    findings = check(args.period, _config(args), args.kalla, _files(args), args.state)
    for finding in findings:
        print(finding)
    return 1 if any(f.level == FEL for f in findings) else 0


def _contract(args: argparse.Namespace) -> int:
    print(contract.markdown())
    return 0


def _simulate(args: argparse.Namespace) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    done: set[str] = set()
    for month in simulate(SimParams(start=args.start, months=args.manader, seed=args.seed)):
        month.harvest.to_csv(args.out / f"produktion_{month.period}.csv", index=False)
        month.deliveries.to_csv(args.out / f"matning_{month.period}.csv", index=False)
        month.truth.to_csv(args.out / f"facit_{month.period}.csv", index=False)
        done |= month.transport_done
        table = pd.DataFrame({AO: sorted(month.destinations)})
        table[DONE] = table[AO].isin(done).map({True: "true", False: "false"})
        table.to_csv(args.out / f"avtalsobjekt_{month.period}.csv", index=False)
    print(f"{args.manader} månader simulerade i {args.out}")
    return 0


def _models(args: argparse.Namespace) -> int:
    print("Utan --modell körs standardmodellen. Byt bara om en person ber om det.\n")
    for name, path in resources.models().items():
        about = resources.describe(path)
        share = f"{about['prestanda'] * 100:.0f} % av standardmodellens förbättring" if "prestanda" in about else ""
        parts = f"{about['delar']} av {about['delar_av']} delar" if "delar" in about else ""
        print(f"{name}: {', '.join(x for x in (parts, share) if x)}")
        if "beskrivning" in about:
            print(f"    {about['beskrivning']}")
    return 0


def _init(args: argparse.Namespace) -> int:
    """Put AGENTS.md and the examples where a person or a model will connect a source."""
    args.dir.mkdir(parents=True, exist_ok=True)
    copies = [
        (resources.path("AGENTS.md"), args.dir / "AGENTS.md"),
        # The example source and the prototypes beside it: start from the one closest to the new source.
        *[(example, args.dir / "examples" / example.name)
          for example in sorted((resources.path("examples")).glob("kalla*")) if example.is_dir()],
        (resources.path("examples") / "demo", args.dir / "examples" / "demo"),
    ]
    for source, target in copies:
        if target.exists():
            print(f"Finns redan, orörd: {target}")
        elif source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            print(f"Skapad: {target}/")
        else:
            shutil.copy(source, target)
            print(f"Skapad: {target}")
    print(f"\nLäs {args.dir / 'AGENTS.md'} och börja med `treedist selftest`.")
    return 0


def _selftest(args: argparse.Namespace) -> int:
    """The demo's four months must give exactly the invoices and matrices they always have."""
    demo, answer = resources.path("examples") / "demo", resources.path("facit")
    periods = sorted(p.stem.removeprefix("faktura_rader_") for p in answer.glob("faktura_rader_*.csv"))
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for period in periods:
            out = Path(tmp) / "out" / period
            files = {
                "--produktion": demo / f"produktion_{period}.csv",
                "--matning": demo / f"matning_{period}.csv",
                "--avtalsobjekt": demo / f"avtalsobjekt_{period}.csv",
            }
            # The matrices and the reconciliation are developer output; the answer is compared with them all the same.
            argv = ["run", "--period", period, "--state", str(Path(tmp) / "state"), "--out", str(out), "--utvecklare"]
            with contextlib.redirect_stdout(io.StringIO()):
                if main(argv + [str(x) for pair in files.items() for x in pair]) != 0:
                    failures.append(f"{period}: körningen misslyckades")
                    break
            comparisons = [(out / "faktura_rader.csv", answer / f"faktura_rader_{period}.csv")]
            if period == periods[-1]:
                comparisons += [(out / DEVELOPER_DIR / name, answer / f"{name.removesuffix('.csv')}_{period}.csv")
                                for name in ("matriser_lang.csv", "avstamning_ao.csv")]
            for actual, expected in comparisons:
                try:
                    pd.testing.assert_frame_equal(pd.read_csv(actual), pd.read_csv(expected), check_exact=False, rtol=1e-9)
                except AssertionError as error:
                    failures.append(f"{period} {actual.name}: {str(error).splitlines()[0]}")
    for failure in failures:
        print(f"FEL {failure}")
    if failures:
        if resources.PACKAGED.exists():
            print("treedist räknar inte som det ska i den här miljön. Kör inte månader förrän det är rättat.")
        else:
            # A clone or a local copy: what differs is most likely a change to the code here.
            print("Siffrorna skiljer från facit i den här kopian av treedist. Har koden ändrats, flyttar ändringen "
                  "volym mellan klasser: rätta den om det inte är meningen, och fråga annars en person innan facit "
                  "skrivs om. Se AGENTS.md, Ändra koden.")
        return 1
    print(f"OK: demons {len(periods)} månader ger samma bilagerader och matriser som facit (treedist {__version__}).")
    return 0


def _backtest(args: argparse.Namespace) -> int:
    if args.modell and args.config:
        raise ValueError("Ange --modell eller --config, inte båda")
    # The evaluation reads the whole model: the method's parameters and its Monte Carlo's.
    model = load_model(resources.model(args.modell) if args.modell else args.config)
    result = run_backtest(SimParams(months=args.manader, seed=args.seed), model)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        result.per_month.round(4).to_csv(args.out, index=False)
    for name, value in result.summary.items():
        print(f"{name}: {value:.3f}")
    return 0


DEVELOPER_FLAG = "--utvecklare"
# Tools for developing the method, not for running months: listed in the help only with --utvecklare.
DEVELOPER_COMMANDS = ("simulate", "backtest")


def build_parser(developer: bool = False) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treedist", description=__doc__)
    parser.add_argument("--version", action="version", version=f"treedist {__version__}")
    parser.add_argument(DEVELOPER_FLAG, action="store_true",
                        help="Utvecklarläge: hela felspårningen vid ett fel, och kommandona för simulering och "
                             "utvärdering i den här hjälpen. Efter run eller check ger flaggan också mer utdata")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Lägg AGENTS.md och exemplen i en katalog, för att koppla in en källa")
    init.add_argument("dir", type=Path, nargs="?", default=Path("."))
    init.set_defaults(handler=_init)

    selftest = commands.add_parser("selftest", help="Kör demon och jämför med facit: räknar treedist rätt här?")
    selftest.set_defaults(handler=_selftest)

    models = commands.add_parser("modeller", help="De sparade modellerna som --modell kan välja")
    models.set_defaults(handler=_models)

    run = commands.add_parser("run", help="Stäng en månad: matriser och bilagor per mottagare och ny liggare")
    _input_arguments(run)
    run.add_argument("--state", required=True, type=Path, help="Katalog med liggaren")
    run.add_argument("--out", required=True, type=Path)
    run.add_argument("--bilaga", choices=APPENDIX_STYLES, default="volym",
                     help="Celler i bilagan som text, som skrivs med --utvecklare: volym i m3fub, eller andel i procent "
                          "av diameterklassens volym")
    run.add_argument("--bilaga-langd", help="Visa längden i grupper med dessa nedre gränser i cm, till exempel 340,370,400")
    run.add_argument("--bilaga-diameter",
                     help="Visa diametern i grupper med dessa nedre gränser i cm; den sista gruppen är öppen uppåt. "
                          f"Förval {DIAMETER_FLOORS[0]},{DIAMETER_FLOORS[1]},...,{DIAMETER_FLOORS[-1]}: en kolumn per cm, "
                          f"med allt under {DIAMETER_FLOORS[0]} cm i en kolumn och allt från {DIAMETER_FLOORS[-1]} cm i en "
                          f"annan. '{CLASSES}' visar klasserna som underlaget har dem")
    run.add_argument("--tillat-ny-kalibrering", action="store_true",
                     help="Kör trots att kalibreringen skiljer från förra månadens; liggarens lager blandar då två skalor")
    _developer_argument(run, "Skriv också matriserna, fördelningen per avtalsobjekt och bilagan som text och rader "
                             f"i {DEVELOPER_DIR}/, och visa volym per källa och ändrade parametrar")
    run.set_defaults(handler=_run)

    pdf = commands.add_parser("pdf", help="Skriv ut månadens bilagor som PDF med Edge eller Chrome")
    pdf.add_argument("--out", required=True, type=Path, help="Månadens utdatakatalog, som i treedist run")
    pdf.set_defaults(handler=_pdf)

    checker = commands.add_parser("check", help="Pröva en källas data mot kontraktet och mot rimliga värden")
    _input_arguments(checker)
    checker.add_argument("--state", type=Path, help="Liggaren, för en provkörning som inget sparar")
    _developer_argument(checker, "Visa hela felspårningen om kontrollen stoppar på ett fel")
    checker.set_defaults(handler=_check)

    printer = commands.add_parser("kontrakt", help="Skriv ut de kanoniska tabellerna")
    printer.set_defaults(handler=_contract)

    sim = commands.add_parser("simulate", **_developer_help(developer, "Skapa syntetisk indata med facit"))
    sim.add_argument("--out", required=True, type=Path)
    sim.add_argument("--start", default="2026-01")
    sim.add_argument("--manader", type=int, default=6)
    sim.add_argument("--seed", type=int, default=7)
    sim.set_defaults(handler=_simulate)

    backtest = commands.add_parser("backtest", **_developer_help(developer, "Utvärdera metoden mot simulerat facit"))
    backtest.add_argument("--manader", type=int, default=10)
    backtest.add_argument("--seed", type=int, default=7)
    backtest.add_argument("--out", type=Path)
    _model_arguments(backtest)
    backtest.set_defaults(handler=_backtest)
    shown = [name for name in commands.choices if developer or name not in DEVELOPER_COMMANDS]
    commands.metavar = "{" + ",".join(shown) + "}"
    return parser


def _developer_help(developer: bool, text: str) -> dict[str, str]:
    """A command without a help text is left out of the list of commands; it still runs."""
    return {"help": text} if developer else {}


def _developer_argument(parser: argparse.ArgumentParser, text: str) -> None:
    # No default here: the flag may also stand before the command, and a default would overwrite it.
    parser.add_argument(DEVELOPER_FLAG, action="store_true", default=argparse.SUPPRESS, help=text)


def _input_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--period", required=True, help="Månad, ÅÅÅÅ-MM")
    parser.add_argument("--kalla", type=Path, help="Källans beskrivning: en .toml-mappning eller en .py-adapter")
    parser.add_argument("--produktion", type=Path, help="Skördarens produktion som CSV i kontraktets form, om --kalla "
                        "inte används")
    parser.add_argument("--matning", type=Path, help="Mätningen som CSV i kontraktets form")
    parser.add_argument("--avtalsobjekt", type=Path, help="Valfri. Månadens avtalsobjekt och om transporten "
                        "är avslutad")
    parser.add_argument("--avverkningsformer", type=Path, help="Valfri. Avverkningsformer per avtalsobjekt, med "
                        "medelstam")
    _model_arguments(parser)


def _model_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--modell", help="En sparad modell, se `treedist modeller`. Utan den körs standardmodellen")
    parser.add_argument("--config", type=Path, help="En egen konfigurationsfil. Med --modell ändrar den bara de "
                        "parametrar den anger")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser(DEVELOPER_FLAG in argv).parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, FileNotFoundError) as error:
        if args.utvecklare:
            traceback.print_exc()
        print(f"Fel: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
