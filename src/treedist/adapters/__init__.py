"""Adapters turn a source system's exports into the canonical tables in contract.py.

This is the only part that changes when the method moves to new data. There are
three ways to connect a source, simplest first:

    csv_files   the exports already are the canonical CSV files
    mapping     a TOML file renames columns, converts units and sets constants, so that a source's own
                terms, such as a company's arbetsorder, become VIOL 3's
    a .py file  your own `read(period) -> dict[str, DataFrame]`, for what a
                mapping cannot express (joins, derived columns)

All three give raw tables keyed as in contract.TABLES; `validate` then checks
them the same way whichever adapter produced them.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..contract import AO, DONE, ORIGIN, OUTSIDE, REQUIRED_TABLES
from ..schema import (
    validate_deliveries,
    validate_harvest,
    validate_work_orders,
    without_harvest,
)
from ..workorders import Facts, measures
from . import csv_files, mapping

Raw = dict[str, pd.DataFrame]


@dataclass
class Inputs:
    harvest: pd.DataFrame
    deliveries: pd.DataFrame
    # The avtalsobjekt whose transport the month's table says is finished.
    transport_done: frozenset[str]
    # The avverkningsformer, for the appendix only; the method never reads them.
    facts: Facts = field(default_factory=Facts)
    # Files read, for the manifest's checksums.
    sources: dict[str, Path] = field(default_factory=dict)


def read_raw(period: str, source: Path | None = None, files: dict[str, Path | None] | None = None) -> tuple[Raw, dict[str, Path]]:
    """Raw canonical tables from a source description, or from canonical CSV files."""
    if source is None:
        return csv_files.read(files or {})
    if source.suffix == ".toml":
        return mapping.read(source, period)
    if source.suffix == ".py":
        return _python(source, period), {"adapter": source}
    raise ValueError(f"Okänd källa {source}: ange en .toml-mappning eller en .py-adapter")


def validate(raw: Raw, period: str) -> Inputs:
    for key in REQUIRED_TABLES:
        if key not in raw:
            raise ValueError(f"Källan gav ingen tabell {key!r}")
    if "avtalsobjekt" in raw:
        _one_row_per_contract_object(raw["avtalsobjekt"])
    harvest = validate_harvest(raw["produktion"], period)
    # Wood from no harvest is validated like the rest and then kept apart: the method never reads it.
    outside = without_harvest(raw["matning"])
    deliveries = validate_deliveries(raw["matning"][~outside], period)
    apart = validate_deliveries(raw["matning"][outside], period) if outside.any() else deliveries.iloc[0:0]
    _outside_is_the_whole_contract_object(apart, deliveries, harvest)
    return Inputs(
        harvest=harvest,
        deliveries=deliveries,
        transport_done=validate_work_orders(raw["avtalsobjekt"]) if "avtalsobjekt" in raw else frozenset(),
        facts=Facts(measures(raw.get("avverkningsformer")), apart, _origins(raw["matning"])),
    )


def _origins(measured: pd.DataFrame) -> pd.Series:
    """Anskaffningsform per avtalsobjekt, for the appendix; empty when the source has none."""
    if ORIGIN not in measured.columns:
        return pd.Series(dtype=object)
    rows = measured[[AO, ORIGIN]].dropna().astype(str).apply(lambda c: c.str.strip())
    rows = rows[rows[ORIGIN] != ""].drop_duplicates()
    several = sorted(rows.loc[rows[AO].duplicated(keep=False), AO].unique())
    if several:
        listed = ", ".join(several[:5]) + (f" och {len(several) - 5} till" if len(several) > 5 else "")
        raise ValueError(f"Mätning: {len(several)} avtalsobjekt har flera olika {ORIGIN}: {listed}. En per avtalsobjekt")
    return rows.set_index(AO)[ORIGIN]


def _outside_is_the_whole_contract_object(apart: pd.DataFrame, deliveries: pd.DataFrame, harvest: pd.DataFrame) -> None:
    """Wood from no harvest is told by the avtalsobjekt's kind, so an avtalsobjekt is either all outside or not at all,
    and has no harvester data. Marking single loads would be a way past the stop for a load without harvester data."""
    if not len(apart):
        return
    marked = set(apart[AO])
    for other, what in ((set(deliveries[AO]), f"har också leveranser som inte är märkta {OUTSIDE}"),
                        (set(harvest[AO]), "har skördardata i månadens produktion")):
        both = sorted(marked & other)
        if both:
            listed = ", ".join(both[:5]) + (f" och {len(both) - 5} till" if len(both) > 5 else "")
            raise ValueError(f"Mätning: {len(both)} avtalsobjekt är märkta {OUTSIDE} men {what}: {listed}. Sätt "
                             f"{OUTSIDE} ur avtalsobjektets typ, lika för alla dess leveranser, aldrig för att "
                             "skördardata saknas")


def _one_row_per_contract_object(frame: pd.DataFrame) -> None:
    """An avtalsobjekt with two rows that disagree: which one counts would be a guess."""
    if AO not in frame.columns:
        return
    columns = [c for c in (AO, DONE) if c in frame.columns]
    rows = frame[columns].astype(str).apply(lambda c: c.str.strip()).drop_duplicates()
    repeated = rows[rows[AO].duplicated(keep=False)]
    if len(repeated):
        ids = sorted(repeated[AO].unique())
        listed = ", ".join(ids[:5]) + (f" och {len(ids) - 5} till" if len(ids) > 5 else "")
        raise ValueError(f"Avtalsobjekt: {len(ids)} avtalsobjekt har flera rader som skiljer sig åt: "
                         f"{listed}. En rad per avtalsobjekt")


def load(period: str, source: Path | None = None, files: dict[str, Path | None] | None = None) -> Inputs:
    raw, sources = read_raw(period, source, files)
    inputs = validate(raw, period)
    inputs.sources = sources
    return inputs


def _python(path: Path, period: str) -> Raw:
    spec = importlib.util.spec_from_file_location(f"treedist_adapter_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Kan inte läsa adaptern {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "read"):
        raise ValueError(f"{path} saknar funktionen read(period)")
    raw = module.read(period)
    return {key: frame.astype(str).where(frame.notna(), None) for key, frame in raw.items()}
