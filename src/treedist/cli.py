"""Command line entry point."""

from __future__ import annotations

import argparse
import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

from .dev.backtest import run_backtest
from . import __version__, adapters, contract, resources
from .check import FEL, check
from .config import Config, load_config
from .core.invoice import invoice_total_kr
from .core.ledger import load_for_period
from .core.pipeline import run_month
from .report import slug, warnings_for, write_month
from .schema import AO, DEST
from .dev.simulate import SimParams, example_price_list, simulate


def _config(args: argparse.Namespace) -> Config:
    if args.modell and args.config:
        raise ValueError("Ange --modell eller --config, inte båda")
    return load_config(resources.model(args.modell) if args.modell else args.config)


def _run(args: argparse.Namespace) -> int:
    cfg = _config(args)
    ledger = load_for_period(args.state, args.period)
    if ledger.period is None:
        print(f"Kallstart: ingen liggare före {args.period}. Virke skördat tidigare saknar skördardata.")

    inputs = adapters.load(args.period, cfg, args.kalla, _files(args))
    output = run_month(
        ledger, inputs.harvest, inputs.deliveries, inputs.prices, args.period, inputs.closed_aos, cfg, inputs.work_orders
    )
    write_month(output, args.out, cfg, inputs.sources)
    output.step.ledger.save(args.state)

    print(f"{args.period}: utdata i {args.out}")
    for destination, lines in output.invoice.groupby(DEST):
        delivered = lines.loc[lines["radtyp"] == "LEVERANS", "volym_m3fub"].sum()
        amount = f", att fakturera {invoice_total_kr(lines):.2f} kr exkl. moms" if output.priced else ""
        print(f"  {destination}: {delivered:.3f} m3fub levererat, bilaga i bilagor/{slug(destination)}.md{amount}")
    if not output.priced:
        print("Ingen prislista: matriser och bilagor, inget fakturaunderlag.")
    for note in warnings_for(output):
        print(f"OBS: {note}")
    return 0


def _files(args: argparse.Namespace) -> dict[str, Path | None]:
    if args.kalla is None and not (args.skordning and args.leverans):
        raise ValueError("Ange --kalla, eller --skordning och --leverans")
    return {
        "skordning": args.skordning,
        "leverans": args.leverans,
        "prislista": args.prislista,
        "arbetsordrar": args.arbetsordrar,
        "avslutade_ao": args.avslutade_ao,
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
    example_price_list().to_csv(args.out / "prislista.csv", index=False)
    for month in simulate(SimParams(start=args.start, months=args.manader, seed=args.seed)):
        month.harvest.to_csv(args.out / f"skordning_{month.period}.csv", index=False)
        month.deliveries.to_csv(args.out / f"leverans_{month.period}.csv", index=False)
        month.truth.to_csv(args.out / f"facit_{month.period}.csv", index=False)
        pd.DataFrame({AO: sorted(month.closed_aos)}).to_csv(args.out / f"avslutade_ao_{month.period}.csv", index=False)
    work_orders = pd.DataFrame({DEST: month.work_orders.destinations, "grupp": month.work_orders.groups})
    work_orders.rename_axis(AO).reset_index().to_csv(args.out / "arbetsordrar.csv", index=False)
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
        (resources.path("examples") / "kalla", args.dir / "examples" / "kalla"),
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
                "--skordning": demo / f"skordning_{period}.csv",
                "--leverans": demo / f"leverans_{period}.csv",
                "--prislista": demo / "prislista.csv",
                "--arbetsordrar": demo / "arbetsordrar.csv",
                "--avslutade-ao": demo / f"avslutade_ao_{period}.csv",
            }
            argv = ["run", "--period", period, "--state", str(Path(tmp) / "state"), "--out", str(out)]
            with contextlib.redirect_stdout(io.StringIO()):
                if main(argv + [str(x) for pair in files.items() for x in pair]) != 0:
                    failures.append(f"{period}: körningen misslyckades")
                    break
            comparisons = [(out / "faktura_rader.csv", answer / f"faktura_rader_{period}.csv")]
            if period == periods[-1]:
                comparisons += [(out / name, answer / f"{name.removesuffix('.csv')}_{period}.csv")
                                for name in ("matriser_lang.csv", "avstamning_ao.csv")]
            for actual, expected in comparisons:
                try:
                    pd.testing.assert_frame_equal(pd.read_csv(actual), pd.read_csv(expected), check_exact=False, rtol=1e-9)
                except AssertionError as error:
                    failures.append(f"{period} {actual.name}: {str(error).splitlines()[0]}")
    for failure in failures:
        print(f"FEL {failure}")
    if failures:
        print("treedist räknar inte som det ska i den här miljön. Kör inte månader förrän det är rättat.")
        return 1
    print(f"OK: demons {len(periods)} månader ger samma fakturor och matriser som facit (treedist {__version__}).")
    return 0


def _backtest(args: argparse.Namespace) -> int:
    cfg = _config(args)
    result = run_backtest(SimParams(months=args.manader, seed=args.seed), cfg)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        result.per_month.round(4).to_csv(args.out, index=False)
    for name, value in result.summary.items():
        print(f"{name}: {value:.3f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treedist", description=__doc__)
    parser.add_argument("--version", action="version", version=f"treedist {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Lägg AGENTS.md och exemplen i en katalog, för att koppla in en källa")
    init.add_argument("dir", type=Path, nargs="?", default=Path("."))
    init.set_defaults(handler=_init)

    selftest = commands.add_parser("selftest", help="Kör demon och jämför med facit: räknar treedist rätt här?")
    selftest.set_defaults(handler=_selftest)

    models = commands.add_parser("modeller", help="De sparade modellerna som --modell kan välja")
    models.set_defaults(handler=_models)

    run = commands.add_parser("run", help="Stäng en månad: matriser och bilagor per mottagare, faktura och ny liggare")
    _input_arguments(run)
    run.add_argument("--state", required=True, type=Path, help="Katalog med liggaren")
    run.add_argument("--out", required=True, type=Path)
    run.set_defaults(handler=_run)

    checker = commands.add_parser("check", help="Pröva en källas data mot kontraktet och mot rimliga värden")
    _input_arguments(checker)
    checker.add_argument("--state", type=Path, help="Liggaren, för en provkörning som inget sparar")
    checker.set_defaults(handler=_check)

    printer = commands.add_parser("kontrakt", help="Skriv ut de kanoniska tabellerna")
    printer.set_defaults(handler=_contract)

    sim = commands.add_parser("simulate", help="Skapa syntetisk indata med facit")
    sim.add_argument("--out", required=True, type=Path)
    sim.add_argument("--start", default="2026-01")
    sim.add_argument("--manader", type=int, default=6)
    sim.add_argument("--seed", type=int, default=7)
    sim.set_defaults(handler=_simulate)

    backtest = commands.add_parser("backtest", help="Utvärdera metoden mot simulerat facit")
    backtest.add_argument("--manader", type=int, default=10)
    backtest.add_argument("--seed", type=int, default=7)
    backtest.add_argument("--out", type=Path)
    _model_arguments(backtest)
    backtest.set_defaults(handler=_backtest)
    return parser


def _input_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--period", required=True, help="Månad, ÅÅÅÅ-MM")
    parser.add_argument("--kalla", type=Path, help="Källans beskrivning: en .toml-mappning eller en .py-adapter")
    parser.add_argument("--skordning", type=Path, help="Kanonisk CSV, om --kalla inte används")
    parser.add_argument("--leverans", type=Path)
    parser.add_argument("--prislista", type=Path, help="Valfri. Utan den blir det matriser och bilagor, ingen faktura")
    parser.add_argument("--avslutade-ao", type=Path)
    parser.add_argument("--arbetsordrar", type=Path, help="Planerad destination och grupp per arbetsorder")
    _model_arguments(parser)


def _model_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--modell", help="En sparad modell, se `treedist modeller`. Utan den körs standardmodellen")
    parser.add_argument("--config", type=Path, help="En egen konfigurationsfil, i stället för --modell")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, FileNotFoundError) as error:
        print(f"Fel: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
