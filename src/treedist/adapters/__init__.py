"""Adapters turn a source system's exports into the canonical tables in contract.py.

This is the only part that changes when the method moves to new data. There are
three ways to connect a source, simplest first:

    csv_files   the exports already are the canonical CSV files
    mapping     a TOML file renames columns, converts units and sets constants
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

from ..config import Config
from ..contract import REQUIRED_TABLES
from ..core.invoice import PriceList
from ..schema import (
    WorkOrders,
    validate_closed_aos,
    validate_deliveries,
    validate_harvest,
    validate_work_orders,
)
from . import csv_files, mapping

Raw = dict[str, pd.DataFrame]


@dataclass
class Inputs:
    harvest: pd.DataFrame
    deliveries: pd.DataFrame
    # None when the source has no price list: matrices and appendices, no invoice basis.
    prices: PriceList | None
    work_orders: WorkOrders
    closed_aos: set[str]
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


def validate(raw: Raw, period: str, cfg: Config) -> Inputs:
    for key in REQUIRED_TABLES:
        if key not in raw:
            raise ValueError(f"Källan gav ingen tabell {key!r}")
    work_orders = validate_work_orders(raw["arbetsordrar"]) if "arbetsordrar" in raw else WorkOrders()
    return Inputs(
        harvest=validate_harvest(raw["skordning"], period),
        deliveries=validate_deliveries(raw["leverans"], period, cfg, work_orders),
        prices=PriceList.from_frame(raw["prislista"]) if "prislista" in raw else None,
        work_orders=work_orders,
        closed_aos=validate_closed_aos(raw["avslutade_ao"]) if "avslutade_ao" in raw else set(),
    )


def load(period: str, cfg: Config, source: Path | None = None, files: dict[str, Path | None] | None = None) -> Inputs:
    raw, sources = read_raw(period, source, files)
    inputs = validate(raw, period, cfg)
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
