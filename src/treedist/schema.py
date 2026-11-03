"""Input columns, reading and validation.

Column names are Swedish since they mirror the source systems. A problem in the
input stops the run: these numbers end up on an invoice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import Config

AO = "arbetsorder"
SORT = "handelssortiment"
PRODUCED = "producerat_handelssortiment"
BILLED = "fakturerat_handelssortiment"
DIA = "diametergrupp"
LEN = "langdgrupp"
VOL = "volym_m3fub"
BRUTTO = "brutto_m3fub"
DEST = "destination"
LOGS = "antal_stockar"
VINTAGE = "avverkningsdatum"
TIER = "sakerhetsklass"

NO_CLASS = "-"
NO_DESTINATION = "-"
UNKNOWN_CLASS = "OKÄND"

HARVEST_REQUIRED = [AO, SORT, DIA, LEN, VOL]
DELIVERY_REQUIRED = [AO, SORT, VOL]


@dataclass(frozen=True)
class WorkOrders:
    """What is known about work orders before any wood is measured."""

    destinations: dict[str, str] = field(default_factory=dict)
    groups: dict[str, str] = field(default_factory=dict)


def group_sort_key(group: str) -> tuple[int, float, str]:
    """Numeric class floors first in numeric order, then labels, OKÄND last."""
    if group == UNKNOWN_CLASS:
        return (2, 0.0, group)
    try:
        return (0, float(group), group)
    except ValueError:
        return (1, 0.0, group)


def sorted_groups(groups) -> list[str]:
    return sorted(set(groups), key=group_sort_key)


def _normalize_group(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    if not text:
        return NO_CLASS
    try:
        number = float(text.replace(",", "."))
    except ValueError:
        return text
    return str(int(number)) if number.is_integer() else str(number)


def _require_columns(df: pd.DataFrame, required: list[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{name}: kolumner saknas: {missing}")


def _require_keys(df: pd.DataFrame, columns: list[str], name: str) -> None:
    for column in columns:
        bad = df[column].isna() | (df[column].astype(str).str.strip() == "")
        if bad.any():
            raise ValueError(f"{name}: tomt värde i {column} på {int(bad.sum())} rader")


def _numeric(df: pd.DataFrame, column: str, name: str) -> pd.Series:
    parsed = pd.to_numeric(df[column].astype(str).str.replace(",", "."), errors="coerce")
    if parsed.isna().any():
        raise ValueError(f"{name}: icke-numeriskt värde i {column}: {df.loc[parsed.isna(), column].iloc[0]!r}")
    if (parsed < 0).any():
        raise ValueError(f"{name}: negativt värde i {column}")
    return parsed


def period_bounds(period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    p = pd.Period(period, freq="M")
    return p.start_time.normalize(), p.end_time.normalize()


def validate_harvest(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Harvest rows reported in `period`; they may be dated earlier, never later."""
    name = "Skördardata"
    _require_columns(df, HARVEST_REQUIRED, name)
    _require_keys(df, [AO, SORT], name)

    out = df[HARVEST_REQUIRED].copy()
    out[AO] = out[AO].astype(str).str.strip()
    out[SORT] = out[SORT].astype(str).str.strip()
    out[DIA] = df[DIA].map(_normalize_group).astype(object)
    out[LEN] = df[LEN].map(_normalize_group).astype(object)
    out[VOL] = _numeric(df, VOL, name)
    if ((out[DIA] == UNKNOWN_CLASS) | (out[LEN] == UNKNOWN_CLASS)).any():
        raise ValueError(f"{name}: {UNKNOWN_CLASS} är en reserverad klass")

    out[LOGS] = _numeric(df, LOGS, name) if LOGS in df.columns else float("nan")

    start, end = period_bounds(period)
    if "avverkningsdatum" in df.columns:
        dates = pd.to_datetime(df["avverkningsdatum"], errors="coerce")
        if dates.isna().any():
            raise ValueError(f"{name}: ogiltigt avverkningsdatum på {int(dates.isna().sum())} rader")
        if (dates > end).any():
            raise ValueError(f"{name}: avverkningsdatum efter perioden {period}")
        out[VINTAGE] = dates.dt.strftime("%Y-%m-%d")
    else:
        # Without a date the wood counts as available the whole month.
        out[VINTAGE] = start.strftime("%Y-%m-%d")
    # An empty row carries no distribution and would divide by zero downstream.
    return out[out[VOL] > 0].reset_index(drop=True)


def validate_deliveries(
    df: pd.DataFrame, period: str, cfg: Config, work_orders: WorkOrders | None = None
) -> pd.DataFrame:
    """Measured volumes per truck, or summed per work order and assortment.

    `volym_m3fub` is the net volume that is paid for. Without `brutto_m3fub` the
    gross equals the net. Without `leveransdatum` the rows count as delivered at
    the end of the month. `mottagningsplats` is where the wood actually went;
    without it a delivery counts as going to the work order's planned destination.
    """
    name = "Inmätning"
    _require_columns(df, DELIVERY_REQUIRED, name)
    _require_keys(df, [AO, SORT], name)

    leaked = [c for c in (DIA, LEN) if c in df.columns]
    if leaked:
        raise ValueError(f"{name}: oväntade kolumner {leaked}; leveranser bär ingen klassinformation")

    out = df[DELIVERY_REQUIRED].copy()
    for column in (AO, SORT):
        out[column] = out[column].astype(str).str.strip()
    # Wood reclassified at the mill is invoiced as measured but leaves the
    # stock of the assortment the harvester produced.
    out[PRODUCED] = out[SORT]
    if PRODUCED in df.columns:
        produced = df[PRODUCED].astype(object).str.strip()
        out[PRODUCED] = produced.where(produced.notna() & (produced != ""), out[SORT])
    out[VOL] = _numeric(df, VOL, name)

    out[BRUTTO] = _numeric(df, BRUTTO, name) if BRUTTO in df.columns else out[VOL]
    if (out[VOL] > out[BRUTTO] + 1e-9).any():
        raise ValueError(f"{name}: nettovolym större än bruttovolym")

    if "leverans_id" in df.columns:
        out["leverans_id"] = df["leverans_id"].astype(str).str.strip()
        # A truck may carry several assortments, or wood from several work orders.
        duplicated = out.duplicated(["leverans_id", AO, SORT, PRODUCED])
        if duplicated.any():
            raise ValueError(f"{name}: dubblerat leverans_id: {out.loc[duplicated, 'leverans_id'].iloc[0]}")

    end = period_bounds(period)[1]
    if "leveransdatum" in df.columns:
        # A load transported late in one month may be accounted for in the next.
        dates = pd.to_datetime(df["leveransdatum"], errors="coerce")
        if dates.isna().any() or (dates > end).any():
            raise ValueError(f"{name}: leveransdatum saknas eller ligger efter perioden {period}")
        out["leveransdatum"] = dates
    else:
        out["leveransdatum"] = end

    planned = (work_orders or WorkOrders()).destinations
    if planned:
        destination = out[AO].map(planned)
    else:
        destination = pd.Series(NO_DESTINATION, index=out.index, dtype=object)
    if "mottagningsplats" in df.columns:
        actual = df["mottagningsplats"].astype(object).str.strip()
        destination = actual.where(actual.notna() & (actual != ""), destination)
    if destination.isna().any():
        missing = sorted(out.loc[destination.isna(), AO].unique())
        raise ValueError(f"{name}: destination saknas för arbetsorder {missing[:5]}")
    out[DEST] = destination.astype(object)

    if "matmetod" in df.columns:
        out["matmetod"] = df["matmetod"].fillna("okand").astype(str).str.strip().str.lower()
    else:
        out["matmetod"] = "okand"
    unknown = set(out["matmetod"]) - set(cfg.volume_methods)
    if unknown:
        raise ValueError(f"{name}: okänd matmetod {sorted(unknown)}; lägg till under volume_methods i konfigurationen")

    if "antal_matenheter" in df.columns:
        units = pd.to_numeric(df["antal_matenheter"], errors="coerce")
    else:
        units = pd.Series(float("nan"), index=df.index)
    defaults = out["matmetod"].map(lambda m: cfg.volume_methods[m].default_units)
    out["antal_matenheter"] = units.where(units > 0, defaults)
    return out


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


def read_work_orders(path: Path | None) -> WorkOrders:
    """Planned destination per work order, and optionally a comparable group."""
    if path is None:
        return WorkOrders()
    df = read_csv(path)
    _require_columns(df, [AO, DEST], str(path))
    _require_keys(df, [AO, DEST], str(path))
    keys = df[AO].astype(str).str.strip()
    groups = {}
    if "grupp" in df.columns:
        labelled = df["grupp"].notna()
        groups = dict(zip(keys[labelled], df.loc[labelled, "grupp"].astype(str).str.strip()))
    return WorkOrders(dict(zip(keys, df[DEST].astype(str).str.strip())), groups)


def read_closed_aos(path: Path | None) -> set[str]:
    if path is None:
        return set()
    df = read_csv(path)
    _require_columns(df, [AO], str(path))
    return set(df[AO].astype(str).str.strip())
