"""A source described in TOML: which file, which column is which, and in what unit.

    [leverans]
    fil = "export/inmatning_{period}.csv"   # relative to the TOML file; {period} is ÅÅÅÅ-MM
    separator = ";"                         # default ","
    kodning = "utf-8"                       # default utf-8
    datumformat = "%Y%m%d"                  # for the table's date columns; default ISO

    [leverans.kolumner]                     # canonical name = the source's column
    arbetsorder = "AO_Nr"
    handelssortiment = "InmattSortiment"
    volym_m3fub = "NettoFub"

    [leverans.enheter]                      # multiply the source's value
    volym_m3fub = 0.001                     # dm3 -> m3

    [leverans.konstanter]                   # the same value on every row
    matmetod = "stockmatning"

    [leverans.filter]                       # keep rows where the source column has the value
    Status = ["Godkänd", "Klar"]

A source column that already has the canonical name is read as it is, so a file
in treedist's own format needs only `fil`. Decimal commas are read as decimal
points everywhere, so `enheter` is only for converting units. Each table is one file read as it is: joining files, mapping
codes to names or changing ids needs a `.py` adapter instead.

Every error names what is allowed, so that whoever writes the mapping can fix it
from the message alone.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pandas as pd

from ..contract import TABLES

_SETTINGS = {"fil", "separator", "kodning", "datumformat", "kolumner", "enheter", "konstanter", "filter"}


def read(path: Path, period: str) -> tuple[dict[str, pd.DataFrame], dict[str, Path]]:
    # utf-8-sig: PowerShell 5.1 and older Notepad write a byte order mark that TOML does not allow.
    try:
        description = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        # A Windows path in "..." is read as escapes: C:\data\x.csv fails here.
        hint = ". Skriv sökvägar med / eller inom enkla citattecken: fil = 'C:\\data\\x.csv'" if "\\" in str(exc) else ""
        raise ValueError(f"{path}: {exc}{hint}") from None
    unknown = set(description) - set(TABLES)
    if unknown:
        raise ValueError(f"{path}: okända tabeller {sorted(unknown)}; tillåtna är {list(TABLES)}")

    raw, sources = {}, {}
    for key, settings in description.items():
        file = path.parent / str(settings.get("fil", "")).format(period=period)
        raw[key] = _table(key, settings, file)
        sources[key] = file
    return raw, sources


def _table(key: str, settings: dict, file: Path) -> pd.DataFrame:
    table = TABLES[key]
    where = f"[{key}]"
    unknown = set(settings) - _SETTINGS
    if unknown:
        raise ValueError(f"{where}: okända inställningar {sorted(unknown)}; tillåtna är {sorted(_SETTINGS)}")
    if "fil" not in settings:
        raise ValueError(f"{where}: ange fil = \"...\"")
    if not file.exists():
        raise FileNotFoundError(f"{where}: filen finns inte: {file}")

    columns = settings.get("kolumner", {})
    units = settings.get("enheter", {})
    constants = settings.get("konstanter", {})
    names = [c.name for c in table.columns]
    for part, given in (("kolumner", columns), ("enheter", units), ("konstanter", constants)):
        wrong = set(given) - set(names)
        if wrong:
            raise ValueError(f"{where}.{part}: okända kanoniska kolumner {sorted(wrong)}; tillåtna är {names}")

    source = pd.read_csv(
        file,
        sep=settings.get("separator", ","),
        encoding=settings.get("kodning", "utf-8"),
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )
    missing = sorted(set(columns.values()) - set(source.columns))
    if missing:
        raise ValueError(f"{where}: kolumnerna {missing} finns inte i {file.name}; där finns {list(source.columns)}")

    for column, values in settings.get("filter", {}).items():
        if column not in source.columns:
            raise ValueError(f"{where}.filter: kolumnen {column!r} finns inte i {file.name}")
        allowed = values if isinstance(values, list) else [values]
        source = source[source[column].isin([str(v) for v in allowed])]

    out = pd.DataFrame(index=source.index)
    for column in table.columns:
        if column.name in columns:
            values = source[columns[column.name]]
        elif column.name in constants:
            values = pd.Series(str(constants[column.name]), index=source.index)
        elif column.name in source.columns:
            values = source[column.name]
        else:
            continue
        if column.name in units:
            numbers = pd.to_numeric(values.str.replace(",", ".", regex=False), errors="coerce")
            values = (numbers * float(units[column.name])).map(lambda v: "" if pd.isna(v) else f"{v:.10g}")
            values = values.where(values != "", None)
        if column.kind == "datum" and "datumformat" in settings:
            dates = pd.to_datetime(values, format=settings["datumformat"], errors="coerce")
            wrong = values.notna() & dates.isna()
            if wrong.any():
                raise ValueError(
                    f"{where}: {int(wrong.sum())} värden i {columns.get(column.name, column.name)} följer inte "
                    f"datumformat {settings['datumformat']!r}, till exempel {values[wrong].iloc[0]!r}"
                )
            values = dates.dt.strftime("%Y-%m-%d").where(dates.notna(), None)
        out[column.name] = values
    return out.reset_index(drop=True)
