"""Reading and validation of the canonical tables in contract.py.

A problem in the input stops the run: these numbers end up on an invoice.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .contract import (  # noqa: F401  re-exported for the rest of the package
    AO,
    BRUTTO,
    MEASURING_METHODS,
    DELIVERED,
    DEST,
    DIA,
    DONE,
    LEN,
    LOAD_ID,
    LOGS,
    MEASURED,
    NO_CLASS,
    NO_DESTINATION,
    OUTSIDE,
    PRODUCED,
    PRODUCED_FOR,
    SORT,
    TABLES,
    TIER,
    UNKNOWN_CLASS,
    VINTAGE,
    LANDING,
    VOL,
)

HARVEST_REQUIRED = TABLES["produktion"].required
DELIVERY_REQUIRED = TABLES["matning"].required


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


def _numeric(df: pd.DataFrame, column: str, name: str, signed: bool = False) -> pd.Series:
    parsed = pd.to_numeric(df[column].astype(str).str.replace(",", "."), errors="coerce")
    if parsed.isna().any():
        raise ValueError(f"{name}: icke-numeriskt värde i {column}: {df.loc[parsed.isna(), column].iloc[0]!r}")
    if not signed and (parsed < 0).any():
        raise ValueError(f"{name}: negativt värde i {column}")
    return parsed


def period_bounds(period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    p = pd.Period(period, freq="M")
    return p.start_time.normalize(), p.end_time.normalize()


def validate_harvest(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Harvest rows reported in `period`; they may be dated earlier, never later. They keep the contract's names:
    the assortment the harvester produced and the mottagningsplats it produced the wood for."""
    name = "Produktion"
    _require_columns(df, HARVEST_REQUIRED, name)
    _require_keys(df, [AO, PRODUCED, PRODUCED_FOR], name)

    out = df[HARVEST_REQUIRED].copy()
    out[AO] = out[AO].astype(str).str.strip()
    out[PRODUCED] = out[PRODUCED].astype(str).str.strip()
    # The mottagningsplats the harvester cut the wood for: its stock is that mottagningsplats' own.
    out[PRODUCED_FOR] = out[PRODUCED_FOR].astype(str).str.strip()
    out[DIA] = df[DIA].map(_normalize_group).astype(object)
    out[LEN] = df[LEN].map(_normalize_group).astype(object)
    out[VOL] = _numeric(df, VOL, name)
    if ((out[DIA] == UNKNOWN_CLASS) | (out[LEN] == UNKNOWN_CLASS)).any():
        raise ValueError(f"{name}: {UNKNOWN_CLASS} är en reserverad klass")

    out[LOGS] = _numeric(df, LOGS, name) if LOGS in df.columns else float("nan")
    out[LANDING] = _text_or_none(df, LANDING)

    dates = pd.to_datetime(df[VINTAGE], errors="coerce")
    if dates.isna().any():
        raise ValueError(f"{name}: avverkningsdatum saknas eller är ogiltigt på {int(dates.isna().sum())} rader")
    if (dates > period_bounds(period)[1]).any():
        raise ValueError(f"{name}: avverkningsdatum efter perioden {period}")
    out[VINTAGE] = dates.dt.strftime("%Y-%m-%d")
    # An empty row carries no distribution and would divide by zero downstream.
    return out[out[VOL] > 0].reset_index(drop=True)


def validate_deliveries(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """Measured volumes per delivery, avtalsobjekt and assortment.

    `volym_m3fub` is the net volume that is paid for, `brutto_m3fub` what left the landing. `mottagningsplats` is
    where the wood was measured, and `producerat_for_mottagningsplats` the one it was cut for: the stock it left.
    """
    name = "Mätning"
    _require_columns(df, DELIVERY_REQUIRED, name)
    _require_keys(df, [LOAD_ID, AO, SORT, PRODUCED, DEST, PRODUCED_FOR], name)

    leaked = [c for c in (DIA, LEN) if c in df.columns]
    if leaked:
        raise ValueError(f"{name}: oväntade kolumner {leaked}; leveranser bär ingen klassinformation")

    out = df[DELIVERY_REQUIRED].copy()
    # Wood reclassified at the mill is invoiced as measured but leaves the stock of the assortment the harvester
    # produced, for the mottagningsplats it was produced for.
    for column in (LOAD_ID, AO, SORT, PRODUCED, DEST, PRODUCED_FOR):
        out[column] = out[column].astype(str).str.strip()
    # A negative row reverses a load, often one accounted for in an earlier month.
    out[VOL] = _numeric(df, VOL, name, signed=True)
    out[BRUTTO] = _numeric(df, BRUTTO, name, signed=True)
    if (out[VOL] * out[BRUTTO] < 0).any():
        raise ValueError(f"{name}: nettovolym och bruttovolym har olika tecken")
    if (out[VOL].abs() > out[BRUTTO].abs() + 1e-9).any():
        raise ValueError(f"{name}: nettovolym större än bruttovolym")

    # A truck may carry several assortments, or wood from several contract objects. A load that was
    # reversed may be booked again under its id, so only loads without a reversal must be unique.
    reversed_ids = set(out.loc[out[VOL] < 0, LOAD_ID])
    duplicated = out.duplicated([LOAD_ID, AO, SORT, PRODUCED]) & ~out[LOAD_ID].isin(reversed_ids)
    if duplicated.any():
        raise ValueError(f"{name}: dubblerat leveransnummer: {out.loc[duplicated, LOAD_ID].iloc[0]}")

    end = period_bounds(period)[1]
    # A load driven late in one month may be measured in the next.
    dates = pd.to_datetime(df[DELIVERED], errors="coerce")
    if dates.isna().any() or (dates > end).any():
        raise ValueError(f"{name}: leveransdatum saknas eller ligger efter perioden {period}")
    out[DELIVERED] = dates
    # The source chooses the month's rows by when they were accounted for; the stock is drawn in the order the loads
    # were driven.
    measured = pd.to_datetime(df[MEASURED], errors="coerce")
    if measured.isna().any() or (measured > end).any():
        raise ValueError(f"{name}: matdatum saknas eller ligger efter perioden {period}")
    early = measured.dt.normalize() < out[DELIVERED].dt.normalize()
    if early.any():
        row = out.loc[early].iloc[0]
        raise ValueError(f"{name}: matdatum före leveransdatum för {int(early.sum())} rader, till exempel "
                         f"avtalsobjekt {row[AO]}; mätningen sker samma dag som transporten eller senare")
    out[MEASURED] = measured

    out[LANDING] = _text_or_none(df, LANDING)

    if "matmetod" in df.columns:
        out["matmetod"] = df["matmetod"].fillna("okand").astype(str).str.strip().str.lower()
    else:
        out["matmetod"] = "okand"
    unknown = set(out["matmetod"]) - set(MEASURING_METHODS)
    if unknown:
        raise ValueError(f"{name}: okänd matmetod {sorted(unknown)}; tillåtna är {list(MEASURING_METHODS)}")

    if "antal_matenheter" in df.columns:
        units = pd.to_numeric(df["antal_matenheter"], errors="coerce")
    else:
        units = pd.Series(float("nan"), index=df.index)
    # Only the evaluation's Monte Carlo reads the count; it stands in a typical one where it is missing.
    out["antal_matenheter"] = units.where(units > 0)
    return out


def without_harvest(df: pd.DataFrame, name: str = "Mätning") -> pd.Series:
    """True for the measurement's rows of wood that comes from no harvest in the source: bought wood, import, wood from
    a terminal. The method has nothing to distribute them by, so they are kept apart from the rows it reads."""
    if OUTSIDE not in df.columns:
        return pd.Series(False, index=df.index)
    flags = df[OUTSIDE].astype(object).where(df[OUTSIDE].notna(), "").astype(str).str.strip().str.lower()
    wrong = ~flags.isin(["true", "false"])
    if wrong.any():
        raise ValueError(f"{name}: {OUTSIDE} ska vara true eller false, inte {flags[wrong].iloc[0]!r}; översätt "
                         "källans värden i källbeskrivningen")
    return flags == "true"


def _text_or_none(df: pd.DataFrame, column: str) -> pd.Series:
    """A text column, with "-" where the source has none."""
    if column not in df.columns:
        return pd.Series(NO_DESTINATION, index=df.index, dtype=object)
    text = df[column].astype(object).where(df[column].notna(), "").astype(str).str.strip()
    return text.where(text != "", NO_DESTINATION)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


def validate_work_orders(df: pd.DataFrame, name: str = "Avtalsobjekt") -> frozenset[str]:
    """The avtalsobjekt whose transport is finished."""
    _require_columns(df, TABLES["avtalsobjekt"].required, name)
    _require_keys(df, [AO], name)
    keys = df[AO].astype(str).str.strip()
    # A table read with pandas holds True and False; their text is the same values.
    flags = df[DONE].astype(object).where(df[DONE].notna(), "").astype(str).str.strip().str.lower()
    wrong = ~flags.isin(["true", "false"])
    if wrong.any():
        raise ValueError(f"{name}: {DONE} ska vara true eller false, inte {flags[wrong].iloc[0]!r} "
                         f"(avtalsobjekt {keys[wrong].iloc[0]}); översätt källans värden i adaptern")
    return frozenset(keys[flags == "true"])
