"""A source described in TOML: which file, which column is which, and in what unit.

    [matning]
    fil = "export/matning_{period}.csv"     # relative to the TOML file; {period} is ÅÅÅÅ-MM
    separator = ";"                         # default ","
    kodning = "utf-8"                       # default utf-8
    datumformat = "%Y%m%d"                  # for the table's date columns; default ISO

    [matning.kolumner]                      # canonical name = the source's column
    avtalsobjekt = "AO_Nr"                  # the source's own term, such as a company's arbetsorder
    handelssortiment = "InmattSortiment"
    volym_m3fub = "NettoFub"

    [matning.enheter]                       # multiply the source's value
    volym_m3fub = 0.001                     # dm3 -> m3

    [matning.konstanter]                    # the same value on every row
    matmetod = "stockmatning"

    [matning.filter]                        # keep rows where the source column has the value
    Status = ["Godkänd", "Klar"]

    [[matning.koppla]]                      # columns from another file, matched on a key; every row must match once
    fil = "export/lass_ao_{period}.csv"
    nyckel = "Lassnr"                       # the same name in both files, or ["Lassnr", "Lass"]: here, there

    [matning.koder.handelssortiment]        # a code in the source, the name treedist and the other tables use
    "110" = "TALL_SAG"
    "210" = "GRAN_SAG"
    # or from a file: fil = "sortimentskoder.csv", fran = "kod", till = "namn"

    [matning.format.avtalsobjekt]           # an id written another way than in the other tables
    ta_bort = "AO-"                         # this prefix goes, where there is one
    bredd = 5                               # leading zeros up to this many characters
    prefix = "AO"                           # this prefix comes, where it is missing

A source column that already has the canonical name is read as it is, so a file in treedist's own format needs
only `fil`. Decimal commas are read as decimal points everywhere, so `enheter` is only for converting units.
`koppla`, `koder` and `format` cover the three things a mapping most often lacked: a column kept in another file,
codes for names, and ids that differ between systems. Each stops rather than guesses: a row without a match, a key
that matches twice, or a code without a name is an error that names them. What they still cannot express needs a
`.py` adapter.

Every error names what is allowed, so that whoever writes the mapping can fix it from the message alone.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pandas as pd

from ..contract import TABLES

_SETTINGS = {"fil", "separator", "kodning", "datumformat", "kolumner", "enheter", "konstanter", "filter", "koppla",
             "koder", "format"}
_JOIN = {"fil", "separator", "kodning", "nyckel"}
_CODE_FILE = {"fil", "separator", "kodning", "fran", "till"}
_FORMAT = {"ta_bort", "bredd", "prefix"}


def read(path: Path, period: str) -> tuple[dict[str, pd.DataFrame], dict[str, Path]]:
    # utf-8-sig: PowerShell 5.1 and older Notepad write a byte order mark that TOML does not allow.
    try:
        description = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as exc:
        # A Windows path in "..." is read as escapes: C:\data\x.csv fails here.
        hint = ". Skriv sökvägar med / eller inom enkla citattecken: fil = 'C:\\data\\x.csv'" if "\\" in str(exc) else ""
        raise ValueError(f"{path}: {exc}{hint}") from None
    unknown = set(description) - set(TABLES)
    if "prislista" in unknown:
        raise ValueError(f"{path}: treedist läser ingen prislista; bilagan visar volym per klass, inte pris. "
                         "Ta bort tabellen [prislista]")
    if unknown:
        raise ValueError(f"{path}: okända tabeller {sorted(unknown)}; tillåtna är {list(TABLES)}")

    raw, sources = {}, {}
    for key, settings in description.items():
        raw[key] = _table(key, settings, path.parent, period)
        sources[key] = _file(path.parent, settings, period)
    return raw, sources


def _file(base: Path, settings: dict, period: str) -> Path:
    return base / str(settings.get("fil", "")).format(period=period)


def _csv(file: Path, settings: dict, where: str) -> pd.DataFrame:
    if not file.exists():
        raise FileNotFoundError(f"{where}: filen finns inte: {file}")
    return pd.read_csv(
        file,
        sep=settings.get("separator", ","),
        encoding=settings.get("kodning", "utf-8"),
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )


def _table(key: str, settings: dict, base: Path, period: str) -> pd.DataFrame:
    table = TABLES[key]
    where = f"[{key}]"
    unknown = set(settings) - _SETTINGS
    if unknown:
        raise ValueError(f"{where}: okända inställningar {sorted(unknown)}; tillåtna är {sorted(_SETTINGS)}")
    if "fil" not in settings:
        raise ValueError(f"{where}: ange fil = \"...\"")
    file = _file(base, settings, period)

    columns = settings.get("kolumner", {})
    units = settings.get("enheter", {})
    constants = settings.get("konstanter", {})
    codes = settings.get("koder", {})
    formats = settings.get("format", {})
    names = [c.name for c in table.columns]
    for part, given in (("kolumner", columns), ("enheter", units), ("konstanter", constants), ("koder", codes),
                        ("format", formats)):
        wrong = set(given) - set(names)
        if wrong:
            raise ValueError(f"{where}.{part}: okända kanoniska kolumner {sorted(wrong)}; tillåtna är {names}")

    source = _csv(file, settings, where)
    for join in _joins(settings.get("koppla", []), where):
        source = _join(source, join, base, period, where, file.name)

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
        if column.name in formats:
            values = _format(values, formats[column.name], f"{where}.format.{column.name}")
        if column.name in codes:
            values = _decode(values, codes[column.name], base, f"{where}.koder.{column.name}")
        out[column.name] = values
    return out.reset_index(drop=True)


def _joins(given, where: str) -> list[dict]:
    joins = [given] if isinstance(given, dict) else list(given)
    for join in joins:
        if not isinstance(join, dict):
            raise ValueError(f"{where}.koppla: skriv [[{where[1:-1]}.koppla]] med fil och nyckel")
        unknown = set(join) - _JOIN
        if unknown:
            raise ValueError(f"{where}.koppla: okända inställningar {sorted(unknown)}; tillåtna är {sorted(_JOIN)}")
        if "fil" not in join or "nyckel" not in join:
            raise ValueError(f"{where}.koppla: ange fil = \"...\" och nyckel = \"kolumn\" (eller [\"här\", \"där\"])")
    return joins


def _join(source: pd.DataFrame, join: dict, base: Path, period: str, where: str, name: str) -> pd.DataFrame:
    """The source with the columns of another file, matched on a key: every row must match exactly one row there."""
    file = _file(base, join, period)
    other = _csv(file, join, f"{where}.koppla")
    key = join["nyckel"]
    here, there = (key, key) if isinstance(key, str) else tuple(key) if len(key) == 2 else (None, None)
    if here is None:
        raise ValueError(f"{where}.koppla: nyckel är ett kolumnnamn, eller två: [\"i {name}\", \"i {file.name}\"]")
    if here not in source.columns:
        raise ValueError(f"{where}.koppla: nyckeln {here!r} finns inte i {name}; där finns {list(source.columns)}")
    if there not in other.columns:
        raise ValueError(f"{where}.koppla: nyckeln {there!r} finns inte i {file.name}; där finns {list(other.columns)}")
    # A row given twice, the same in every column, says nothing new.
    other = other.drop_duplicates()
    twice = other[other[there].duplicated(keep=False)][there]
    if len(twice):
        raise ValueError(f"{where}.koppla: {twice.nunique()} nycklar står mer än en gång i {file.name}, till exempel "
                         f"{twice.iloc[0]!r}; varje rad ska bara kunna kopplas till en")
    both = sorted((set(other.columns) - {there}) & set(source.columns))
    if both:
        raise ValueError(f"{where}.koppla: kolumnerna {both} finns i både {name} och {file.name}; "
                         "ta bara med en av dem, eller koppla på en fil utan dem")
    lonely = ~source[here].isin(set(other[there]))
    if lonely.any():
        raise ValueError(f"{where}.koppla: {int(lonely.sum())} rader i {name} har ingen motsvarighet i {file.name}, "
                         f"till exempel {here} = {source.loc[lonely, here].iloc[0]!r}")
    joined = source.merge(other.rename(columns={there: here}) if there != here else other, on=here, how="left",
                          validate="many_to_one")
    joined.index = source.index
    return joined


def _format(values: pd.Series, rule: dict, where: str) -> pd.Series:
    """An id written as the other tables write it: a prefix taken away, zeros added in front, a prefix put on."""
    unknown = set(rule) - _FORMAT
    if unknown:
        raise ValueError(f"{where}: okända inställningar {sorted(unknown)}; tillåtna är {sorted(_FORMAT)}")
    out = values.astype(object)
    known = out.notna()
    text = out[known].astype(str).str.strip()
    if "ta_bort" in rule:
        cut = str(rule["ta_bort"])
        text = text.where(~text.str.startswith(cut), text.str[len(cut):])
    if "bredd" in rule:
        text = text.str.zfill(int(rule["bredd"]))
    if "prefix" in rule:
        put = str(rule["prefix"])
        text = text.where(text.str.startswith(put), put + text)
    out[known] = text
    return out


def _decode(values: pd.Series, rule: dict, base: Path, where: str) -> pd.Series:
    """Codes as the names the other tables use, from the mapping itself or from a file; an unknown code stops."""
    if "fil" in rule:
        unknown = set(rule) - _CODE_FILE
        if unknown:
            raise ValueError(f"{where}: okända inställningar {sorted(unknown)}; med fil är tillåtna {sorted(_CODE_FILE)}")
        if "fran" not in rule or "till" not in rule:
            raise ValueError(f"{where}: ange fran = \"kolumnen med koden\" och till = \"kolumnen med namnet\"")
        table = _csv(base / str(rule["fil"]), rule, where)
        for column in (rule["fran"], rule["till"]):
            if column not in table.columns:
                raise ValueError(f"{where}: kolumnen {column!r} finns inte i {rule['fil']}; där finns {list(table.columns)}")
        twice = table[table[rule["fran"]].duplicated(keep=False)][rule["fran"]]
        if len(twice):
            raise ValueError(f"{where}: koden {twice.iloc[0]!r} står mer än en gång i {rule['fil']}")
        names = dict(zip(table[rule["fran"]].str.strip(), table[rule["till"]].str.strip()))
    else:
        names = {str(code): str(name) for code, name in rule.items()}
    known = values.notna()
    text = values[known].astype(str).str.strip()
    missing = sorted(set(text) - set(names))
    if missing:
        raise ValueError(f"{where}: koderna {missing[:5]} har inget namn; lägg till dem, till exempel \"{missing[0]}\" = \"…\"")
    out = values.astype(object)
    out[known] = text.map(names)
    return out
