"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .backtest import run_backtest
from .config import load_config
from .invoice import PriceList, invoice_total_kr
from .ledger import load_for_period
from .pipeline import run_month
from .report import warnings_for, write_month
from .schema import AO, read_closed_aos, read_csv, validate_deliveries, validate_harvest
from .simulate import SimParams, example_price_list, simulate


def _run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    ledger = load_for_period(args.state, args.period)
    if ledger.period is None:
        print(f"Kallstart: ingen liggare före {args.period}. Virke skördat tidigare saknar skördardata.")

    harvest = validate_harvest(read_csv(args.skordning), args.period)
    deliveries = validate_deliveries(read_csv(args.leverans), args.period, cfg)
    prices = PriceList.read(args.prislista)
    closed = read_closed_aos(args.avslutade_ao)

    output = run_month(ledger, harvest, deliveries, prices, args.period, closed, cfg)

    inputs = {"skordning": args.skordning, "leverans": args.leverans, "prislista": args.prislista}
    if args.avslutade_ao:
        inputs["avslutade_ao"] = args.avslutade_ao
    write_month(output, args.out, cfg, inputs)
    output.step.ledger.save(args.state)

    print(f"{args.period}: att fakturera {invoice_total_kr(output.invoice):.2f} kr exkl. moms. Utdata i {args.out}")
    for note in warnings_for(output):
        print(f"OBS: {note}")
    return 0


def _simulate(args: argparse.Namespace) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    example_price_list().to_csv(args.out / "prislista.csv", index=False)
    for month in simulate(SimParams(start=args.start, months=args.manader, seed=args.seed)):
        month.harvest.to_csv(args.out / f"skordning_{month.period}.csv", index=False)
        month.deliveries.to_csv(args.out / f"leverans_{month.period}.csv", index=False)
        month.truth.to_csv(args.out / f"facit_{month.period}.csv", index=False)
        pd.DataFrame({AO: sorted(month.closed_aos)}).to_csv(args.out / f"avslutade_ao_{month.period}.csv", index=False)
    print(f"{args.manader} månader simulerade i {args.out}")
    return 0


def _backtest(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    result = run_backtest(SimParams(months=args.manader, seed=args.seed), cfg)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        result.per_month.round(4).to_csv(args.out, index=False)
    for name, value in result.summary.items():
        print(f"{name}: {value:.3f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="treedist", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Stäng en månad: matriser, faktura och ny liggare")
    run.add_argument("--period", required=True, help="Månad, ÅÅÅÅ-MM")
    run.add_argument("--skordning", required=True, type=Path)
    run.add_argument("--leverans", required=True, type=Path)
    run.add_argument("--prislista", required=True, type=Path)
    run.add_argument("--state", required=True, type=Path, help="Katalog med liggaren")
    run.add_argument("--out", required=True, type=Path)
    run.add_argument("--avslutade-ao", type=Path)
    run.add_argument("--config", type=Path)
    run.set_defaults(handler=_run)

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
    backtest.add_argument("--config", type=Path)
    backtest.set_defaults(handler=_backtest)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ValueError, FileNotFoundError) as error:
        print(f"Fel: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
