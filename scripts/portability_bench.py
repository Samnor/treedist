"""How well does treedist move to new data? Two measures for the portability climb.

    uv run python scripts/portability_bench.py felkatalog
        Plants common mapping mistakes in examples/kalla and counts how many
        `treedist check` notices. Deterministic.

    uv run python scripts/portability_bench.py skapa --dir BENCH [--kontroll] [--plattform | --historik]
        Writes simulated months as foreign exports, each with its own quirks,
        under BENCH/uppgifter/<variant>/ with a data owner's description, and
        the canonical answer under BENCH/facit/<variant>/. A model gets only the
        task folder and AGENTS.md and writes the source description.

    uv run python scripts/portability_bench.py rätta --dir BENCH
        Scores each task's kalla.toml or kalla.py against the answer: the
        validated tables and the invoice must be exactly the same.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from treedist.adapters import load
from treedist.check import FEL, OK, VARNING, check
from treedist.config import Config
from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.dev.simulate import SimParams, example_price_list, simulate

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "kalla"
PERIOD = "2026-01"
CFG = Config(intervals=False)


# --- Mistakes a mapping can make: (name, text in kalla.toml, replacement). ---

MISTAKES = [
    ("diameter i mm som cm", "diameter_grupp_placeholder", ""),
    ("redovisningsdatum som leveransdatum", 'leveransdatum = "TransportDatum"', 'leveransdatum = "RedovisningDatum"'),
    ("brutto och netto bytta", 'volym_m3fub = "NettoFub"\nbrutto_m3fub = "BruttoFub"',
     'volym_m3fub = "BruttoFub"\nbrutto_m3fub = "NettoFub"'),
    ("brutto samma kolumn som netto", 'brutto_m3fub = "BruttoFub"', 'brutto_m3fub = "NettoFub"'),
    ("längd i dm", "[skordning.enheter]\n", "[skordning.enheter]\nlangdgrupp = 0.1\n"),
    ("inmätt volym i dm3", "[leverans.filter]", "[leverans.enheter]\nvolym_m3fub = 1000\nbrutto_m3fub = 1000\n\n[leverans.filter]"),
    ("skördad volym i dm3", "[skordning.enheter]\n", "[skordning.enheter]\nvolym_m3fub = 1000\n"),
    ("lassnummer som arbetsorder", 'leverans_id = "Lassnr"\narbetsorder = "AO_Nr"', 'leverans_id = "Lassnr"\narbetsorder = "Lassnr"'),
    ("leveransdatum saknas", 'leveransdatum = "TransportDatum"   # transportdatum, inte RedovisningDatum\n', ""),
    ("makulerade lass med", '[leverans.filter]\nStatus = "Godkänd"\n', ""),
    ("diameter som klassmitt", "diametergrupp = 0.1   # mm -> cm", "diametergrupp = 0.1   # mm -> cm\n# MITT"),
    ("antal stockar från fel kolumn", 'antal_stockar = "AntalStockar"', 'antal_stockar = "DiamKlassMM"'),
    # From the first round's control.
    ("mottagare som sortiment", 'handelssortiment = "InmattSortiment"', 'handelssortiment = "Mottagare"'),
    ("arbetsorder som mottagningsplats", 'mottagningsplats = "Mottagare"', 'mottagningsplats = "AO_Nr"'),
    ("antal stockar som skördad volym", 'volym_m3fub = "VolymFub"', 'volym_m3fub = "AntalStockar"'),
    ("dag och månad bytta i leveransdatum", 'separator = ";"\ndatumformat = "%Y%m%d"\n\n[leverans.kolumner]',
     'separator = ";"\ndatumformat = "%Y%d%m"\n\n[leverans.kolumner]'),
    ("grupp som planerad destination", 'destination = "PlaneradMottagare"', 'destination = "Jamforgrupp"'),
    ("arbetsorder som lassnummer", 'leverans_id = "Lassnr"', 'leverans_id = "AO_Nr"'),
]


# Control: written before the second round's decisions and used once, to see whether the checks generalise.
# The first round's control mistakes moved into MISTAKES once decisions used them.
CONTROL_MISTAKES = [
    ("diameter och längd bytta", 'diametergrupp = "DiamKlassMM"\nlangdgrupp = "LangdKlassCM"',
     'diametergrupp = "LangdKlassCM"\nlangdgrupp = "DiamKlassMM"'),
    ("mottagare som arbetsorder i arbetsordrar", 'arbetsorder = "AO"\ndestination = "PlaneradMottagare"',
     'arbetsorder = "PlaneradMottagare"\ndestination = "PlaneradMottagare"'),
    ("ett sortiment som konstant i inmätningen", [('handelssortiment = "InmattSortiment"\n', ""),
     ("[leverans.filter]", '[leverans.konstanter]\nhandelssortiment = "TALL_SAG"\n\n[leverans.filter]')]),
    ("antal enheter som bruttovolym", 'brutto_m3fub = "BruttoFub"', 'brutto_m3fub = "AntalEnheter"'),
    ("dag och månad bytta i fällningsdatum", '[skordning]\nfil = "export/produktion_{period}.csv"\nseparator = ";"\ndatumformat = "%Y%m%d"',
     '[skordning]\nfil = "export/produktion_{period}.csv"\nseparator = ";"\ndatumformat = "%Y%d%m"'),
]


def _mistake_source(tmp: Path, edits: list[tuple[str, str]]) -> Path:
    text = (EXAMPLE / "kalla.toml").read_text(encoding="utf-8")
    export = EXAMPLE / "export"
    for old, new in edits:
        if old == "diameter_grupp_placeholder":
            old, new = "diametergrupp = 0.1   # mm -> cm", ""
        if new.endswith("# MITT"):
            # Class midpoints: export the class bottom plus half a 2 cm class.
            export = tmp / "export"
            shutil.copytree(EXAMPLE / "export", export, dirs_exist_ok=True)
            harvest = pd.read_csv(export / f"produktion_{PERIOD}.csv", sep=";", dtype=str)
            harvest["DiamKlassMM"] = (harvest["DiamKlassMM"].astype(int) + 10).astype(str)
            harvest.to_csv(export / f"produktion_{PERIOD}.csv", sep=";", index=False)
            new = new.replace("\n# MITT", "")
        if old not in text:
            raise SystemExit(f"Felkatalogen passar inte längre kalla.toml: {old!r}")
        text = text.replace(old, new)
    text = text.replace('"export/', f'"{export}/').replace('"../demo/', f'"{EXAMPLE.parent}/demo/')
    path = tmp / "kalla.toml"
    path.write_text(text, encoding="utf-8")
    return path


def mistakes(catalog=MISTAKES) -> int:
    import tempfile

    baseline = {(f.level, f.message) for f in check(PERIOD, CFG, source=EXAMPLE / "kalla.toml") if f.level != OK}
    found = 0
    for name, *edit in catalog:
        edits = edit[0] if len(edit) == 1 else [tuple(edit)]
        with tempfile.TemporaryDirectory() as tmp:
            source = _mistake_source(Path(tmp), edits)
            findings = check(PERIOD, CFG, source=source)
        raised = [f for f in findings if f.level in (FEL, VARNING) and (f.level, f.message) not in baseline]
        found += bool(raised)
        print(f"{'UPPTÄCKT' if raised else 'MISSAD  '} {name}: {raised[0] if raised else ''}")
    print(f"\n{found} av {len(catalog)} upptäckta")
    return found


def false_alarms(bench: Path | None) -> int:
    """Warnings on sources whose mapping is right: each one costs a person or a model a judgement."""
    sources = [EXAMPLE / "kalla.toml"]
    if bench is not None:
        sources += [s for s in map(_entry, sorted((bench / "uppgifter").iterdir())) if s is not None]
    total = 0
    for source in sources:
        raised = [f for f in check(PERIOD, CFG, source=source) if f.level not in (OK, "INFO")]
        total += len(raised)
        for finding in raised:
            print(f"FALSKLARM {source.parent.name}: {finding}")
    print(f"\n{total} falsklarm på {len(sources)} korrekta källor")
    return total


# --- Foreign exports a model has to map. ---


@dataclass
class Month:
    harvest: pd.DataFrame
    deliveries: pd.DataFrame
    orders: pd.DataFrame
    closed: pd.DataFrame
    period: str = PERIOD


def _months(seed: int, count: int = 1) -> list[Month]:
    months = []
    for month in simulate(SimParams(months=count, seed=seed, work_orders_per_month=10)):
        orders = pd.DataFrame({"destination": month.work_orders.destinations, "grupp": month.work_orders.groups})
        months.append(Month(
            month.harvest,
            month.deliveries,
            orders.rename_axis("arbetsorder").reset_index(),
            pd.DataFrame({"arbetsorder": sorted(month.closed_aos)}),
            month.period,
        ))
    return months


def _month(seed: int) -> Month:
    return _months(seed)[0]


def _comma(values: pd.Series) -> pd.Series:
    return values.map(lambda v: f"{v:g}".replace(".", ","))


def _semicolon(m: Month, out: Path) -> str:
    """Like the example, but with its own names."""
    h, d = m.harvest, m.deliveries
    pd.DataFrame({
        "Arbetsorder": h["arbetsorder"], "Sort": h["handelssortiment"], "Diam_mm": h["diametergrupp"].astype(int) * 10,
        "Langd_cm": h["langdgrupp"], "Fub": _comma(h["volym_m3fub"]), "Stammar": h["antal_stockar"],
        "Avverkad": h["avverkningsdatum"].str.replace("-", ""),
    }).to_csv(out / f"skord_{PERIOD}.csv", sep=";", index=False)
    pd.DataFrame({
        "Lass": d["leverans_id"], "Arbetsorder": d["arbetsorder"], "Sort": d["handelssortiment"],
        "Mottagare": d["mottagningsplats"], "Kordatum": d["leveransdatum"].str.replace("-", ""),
        "Bokford": f"{PERIOD.replace('-', '')}28", "NettoFub": _comma(d["volym_m3fub"]),
        "BruttoFub": _comma(d["brutto_m3fub"]), "Metod": d["matmetod"], "Enheter": d["antal_matenheter"],
    }).to_csv(out / f"mat_{PERIOD}.csv", sep=";", index=False)
    m.orders.rename(columns={"arbetsorder": "Arbetsorder", "destination": "Planerad", "grupp": "Omrade"}).to_csv(
        out / "ao.csv", sep=";", index=False)
    return (
        "Exporterna är semikolonseparerade med decimalkomma.\n\n"
        f"- `skord_{PERIOD}.csv`: skördarens produktion. Diam_mm är diameterklassens nedre gräns i millimeter, "
        "Langd_cm längdklassens nedre gräns i centimeter, Fub volym under bark i m3, Stammar antal stockar, "
        "Avverkad fällningsdag som ÅÅÅÅMMDD.\n"
        f"- `mat_{PERIOD}.csv`: inmätning vid industri per lass. Kordatum är när lasset kördes, Bokford när det "
        "bokfördes. NettoFub är fakturerad volym, BruttoFub volym före avdrag. Metod är mätmetoden.\n"
        "- `ao.csv`: arbetsordrar med planerad mottagare och jämförbart område.\n"
    )


def _english(m: Month, out: Path) -> str:
    """Tab separated latin-1 with English names, lengths in dm and delivered volume in dm3."""
    h, d = m.harvest, m.deliveries
    day = lambda s: pd.to_datetime(s).dt.strftime("%d.%m.%Y")  # noqa: E731
    pd.DataFrame({
        "WorkOrder": h["arbetsorder"], "Assortment": h["handelssortiment"], "DiaClassCm": h["diametergrupp"],
        "LenClassDm": (h["langdgrupp"].astype(int) // 10), "VolUB_m3": h["volym_m3fub"], "Logs": h["antal_stockar"],
        "FellingDate": day(h["avverkningsdatum"]),
    }).to_csv(out / f"harvest_{PERIOD}.txt", sep="\t", index=False, encoding="latin-1")
    pd.DataFrame({
        "TruckLoad": d["leverans_id"], "WorkOrder": d["arbetsorder"], "Assortment": d["handelssortiment"],
        "Mill": d["mottagningsplats"], "HaulDate": day(d["leveransdatum"]),
        "NetUB_dm3": (d["volym_m3fub"] * 1000).round(0).astype(int), "GrossUB_dm3": (d["brutto_m3fub"] * 1000).round(0).astype(int),
        "Method": d["matmetod"], "Units": d["antal_matenheter"], "Säsong": "vinter",
    }).to_csv(out / f"scaling_{PERIOD}.txt", sep="\t", index=False, encoding="latin-1")
    m.orders.rename(columns={"arbetsorder": "WorkOrder", "destination": "PlannedMill", "grupp": "Stratum"}).to_csv(
        out / "workorders.txt", sep="\t", index=False, encoding="latin-1")
    return (
        "Tabbseparerade textfiler i latin-1.\n\n"
        f"- `harvest_{PERIOD}.txt`: skördarens produktion. DiaClassCm är diameterklassens nedre gräns i cm, "
        "LenClassDm längdklassens nedre gräns i decimeter, VolUB_m3 volym under bark, Logs antal stockar, "
        "FellingDate fällningsdag som DD.MM.ÅÅÅÅ.\n"
        f"- `scaling_{PERIOD}.txt`: inmätning per lass. HaulDate är transportdagen. NetUB_dm3 är fakturerad "
        "volym och GrossUB_dm3 volym före avdrag, båda i kubikdecimeter under bark.\n"
        "- `workorders.txt`: arbetsordrar med planerat sågverk och stratum.\n"
    )


def _join(m: Month, out: Path) -> str:
    """The deliveries name only the truck; which work order it came from is in another file."""
    h, d = m.harvest, m.deliveries
    h.to_csv(out / f"produktion_{PERIOD}.csv", index=False)
    d.drop(columns=["arbetsorder"]).rename(columns={"leverans_id": "lass"}).to_csv(
        out / f"inmatning_{PERIOD}.csv", index=False)
    d[["leverans_id", "arbetsorder"]].rename(columns={"leverans_id": "lass", "arbetsorder": "ao"}).to_csv(
        out / f"lass_ao_{PERIOD}.csv", index=False)
    m.orders.to_csv(out / "arbetsordrar.csv", index=False)
    return (
        "Kommaseparerade filer med punkt som decimaltecken.\n\n"
        f"- `produktion_{PERIOD}.csv`: skördarens produktion, redan i treedists kolumnnamn.\n"
        f"- `inmatning_{PERIOD}.csv`: inmätning per lass, i treedists kolumnnamn men utan arbetsorder. "
        "Kolumnen lass är lassnumret.\n"
        f"- `lass_ao_{PERIOD}.csv`: vilken arbetsorder (ao) varje lass kom från.\n"
        "- `arbetsordrar.csv`: arbetsordrar i treedists format.\n"
    )


def _codes(m: Month, out: Path) -> str:
    """Assortments as codes, work orders without their prefix in the delivery system."""
    h, d = m.harvest, m.deliveries
    codes = {"TALL_SAG": "110", "GRAN_SAG": "210"}
    h.assign(handelssortiment=h["handelssortiment"].map(codes)).to_csv(out / f"skord_{PERIOD}.csv", index=False)
    d.assign(
        arbetsorder=d["arbetsorder"].str.replace("AO", "", regex=False),
        handelssortiment=d["handelssortiment"].map(codes),
    ).to_csv(out / f"inmatning_{PERIOD}.csv", index=False)
    m.orders.to_csv(out / "arbetsordrar.csv", index=False)
    pd.DataFrame({"kod": list(codes.values()), "namn": list(codes)}).to_csv(out / "sortimentskoder.csv", index=False)
    return (
        "Kommaseparerade filer i treedists kolumnnamn, men med två skillnader mot treedist:\n\n"
        "- Sortiment anges som koder i både skördardata och inmätning. `sortimentskoder.csv` ger namnet "
        "för varje kod, och det är namnen som prislistan och arbetsordrarna använder.\n"
        "- Inmätningssystemet tar bort prefixet AO från arbetsordernumret: AO00012 i skördardatan heter 00012 "
        "i inmätningen.\n"
    )


# --- Other kinds of platform than a file export: none of these can be read by a TOML mapping alone. ---


def _decimal(values: pd.Series, comma: bool = True) -> pd.Series:
    text = values.map(lambda v: f"{v:.3f}".rstrip("0").rstrip("."))
    return text.str.replace(".", ",", regex=False) if comma else text


def _warehouse(m: Month, out: Path) -> str:
    """A data warehouse: surrogate keys, dimension tables, volumes in dm3 and superseded versions of loads."""
    _star(out, m.harvest, m.deliveries, m.orders, {})
    return WAREHOUSE_TEXT


def _warehouse_history(months: list[Month], out: Path) -> str:
    """The same warehouse with every month so far: the month's harvest is what was reported in it."""
    report_month = [m.harvest["avverkningsdatum"].map(lambda _, p=m.period: int(p.replace("-", ""))) for m in months]
    harvest = pd.concat([m.harvest for m in months], ignore_index=True)
    _star(out, harvest, pd.concat([m.deliveries for m in months], ignore_index=True), months[-1].orders,
          {"rapport_manad": pd.concat(report_month, ignore_index=True)})
    return WAREHOUSE_TEXT + (
        "\nLagret har alla månader hittills. I `fakta_skord` är rapport_manad månaden skördaren rapporterade "
        "raden, som ÅÅÅÅMM.\n"
    )


_warehouse_history.months = 2


def _star(out: Path, h: pd.DataFrame, d: pd.DataFrame, o: pd.DataFrame, extra_harvest: dict) -> None:
    rng = np.random.default_rng(len(d))
    ao_key = {ao: 1000 + 7 * i for i, ao in enumerate(o["arbetsorder"])}
    sort_key = {"TALL_SAG": 11, "GRAN_SAG": 12}
    mills = sorted(set(o["destination"]) | set(d["mottagningsplats"]))
    mill_key = {name: 501 + i for i, name in enumerate(mills)}
    day_key = lambda s: s.str.replace("-", "").astype(int)  # noqa: E731
    dm3 = lambda v: (v * 1000).round(0).astype(int)  # noqa: E731

    loads = pd.DataFrame({
        "lass_id": d["leverans_id"], "version": 1, "giltig": 1, "ao_key": d["arbetsorder"].map(ao_key),
        "sortiment_key": d["handelssortiment"].map(sort_key), "mottagare_key": d["mottagningsplats"].map(mill_key),
        "kord_datum_key": day_key(d["leveransdatum"]), "netto_dm3": dm3(d["volym_m3fub"]),
        "brutto_dm3": dm3(d["brutto_m3fub"]), "matmetod": d["matmetod"], "matenheter": d["antal_matenheter"],
    })
    # A remeasurement writes a new version of the load and keeps the old one as invalid.
    remeasured = rng.random(len(loads)) < 0.15
    old = loads[remeasured].assign(giltig=0, netto_dm3=lambda t: (t["netto_dm3"] * 0.94).round(0).astype(int))
    loads.loc[remeasured, "version"] = 2
    loads = pd.concat([old, loads]).sample(frac=1, random_state=1)

    with sqlite3.connect(out / "lager.sqlite") as db:
        pd.DataFrame({
            "ao_key": o["arbetsorder"].map(ao_key), "ao_nr": o["arbetsorder"],
            "planerad_mottagare_key": o["destination"].map(mill_key), "jamforgrupp": o["grupp"],
        }).to_sql("dim_ao", db, index=False)
        pd.DataFrame({"mottagare_key": list(mill_key.values()), "namn": list(mill_key)}).to_sql("dim_mottagare", db, index=False)
        pd.DataFrame({"sortiment_key": list(sort_key.values()), "namn": list(sort_key)}).to_sql("dim_sortiment", db, index=False)
        pd.DataFrame({
            "ao_key": h["arbetsorder"].map(ao_key), "sortiment_key": h["handelssortiment"].map(sort_key),
            "diameter_mm": h["diametergrupp"].astype(int) * 10, "langd_cm": h["langdgrupp"].astype(int),
            "fallt_datum_key": day_key(h["avverkningsdatum"]), "volym_dm3": dm3(h["volym_m3fub"]),
            "antal_stockar": h["antal_stockar"], **extra_harvest,
        }).to_sql("fakta_skord", db, index=False)
        loads.to_sql("fakta_lass", db, index=False)


WAREHOUSE_TEXT = (
    "Allt ligger i datalagret `lager.sqlite` (SQLite), som en stjärnmodell med surrogatnycklar.\n\n"
    "- `dim_ao`: arbetsordrar. ao_nr är arbetsordernumret, planerad_mottagare_key pekar på dim_mottagare, "
    "jamforgrupp är jämförbar grupp.\n"
    "- `dim_mottagare` och `dim_sortiment`: namnen bakom nycklarna.\n"
    "- `fakta_skord`: skördarens produktion. diameter_mm är diameterklassens nedre gräns i millimeter, langd_cm "
    "längdklassens nedre gräns, fallt_datum_key fällningsdagen som heltal ÅÅÅÅMMDD, volym_dm3 volym under bark "
    "i kubikdecimeter.\n"
    "- `fakta_lass`: inmätning per lass. kord_datum_key är dagen lasset kördes. netto_dm3 är fakturerad volym "
    "och brutto_dm3 volym före avdrag, i kubikdecimeter under bark. En ommätning skriver en ny version av "
    "lasset; bara raden med giltig = 1 gäller.\n"
)


def _api(m: Month, out: Path) -> str:
    """JSON from a REST API: nested harvest, loads in pages with UTC timestamps, work orders keyed by number."""
    h, d, o = m.harvest, m.deliveries, m.orders
    rng = np.random.default_rng(len(d))
    harvest = [
        {"arbetsorder": ao, "sortiment": sort, "klasser": [
            {"d_cm": int(r.diametergrupp), "l_cm": int(r.langdgrupp), "fallt": r.avverkningsdatum,
             "m3fub": float(r.volym_m3fub), "stockar": int(r.antal_stockar)} for r in group.itertuples()]}
        for (ao, sort), group in h.groupby(["arbetsorder", "handelssortiment"])
    ]
    (out / f"skord_{PERIOD}.json").write_text(json.dumps({"antal": len(harvest), "data": harvest}, ensure_ascii=False))

    # Night loads: a load driven just after midnight in Sweden is the day before in UTC.
    minutes = np.where(rng.random(len(d)) < 0.25, rng.integers(0, 60, len(d)), rng.integers(60, 24 * 60, len(d)))
    local = pd.to_datetime(d["leveransdatum"]) + pd.to_timedelta(minutes, unit="min")
    utc = local.dt.tz_localize("Europe/Stockholm").dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    loads = [
        {"lass": r.leverans_id, "arbetsorder": r.arbetsorder, "sortiment": r.handelssortiment,
         "mottagare": {"kod": r.mottagningsplats}, "kord_utc": stamp,
         "matning": {"metod": r.matmetod, "enheter": int(r.antal_matenheter), "netto_m3fub": float(r.volym_m3fub),
                     "brutto_m3fub": float(r.brutto_m3fub)}}
        for r, stamp in zip(d.itertuples(), utc)
    ]
    for page, start in enumerate(range(0, len(loads), 20), start=1):
        lines = [json.dumps(load, ensure_ascii=False) for load in loads[start:start + 20]]
        (out / f"lass_{PERIOD}_sida{page}.jsonl").write_text("\n".join(lines) + "\n")
    orders = {r.arbetsorder: {"planerad_mottagare": r.destination, "grupp": r.grupp} for r in o.itertuples()}
    (out / "arbetsordrar.json").write_text(json.dumps(orders, ensure_ascii=False, indent=2))
    return (
        "JSON hämtat från leverantörens REST-API.\n\n"
        f"- `skord_{PERIOD}.json`: skördarens produktion per arbetsorder och sortiment, med en lista av klasser. "
        "d_cm och l_cm är klassernas nedre gränser i cm, fallt fällningsdagen, m3fub volym under bark, stockar "
        "antal stockar.\n"
        f"- `lass_{PERIOD}_sida1.jsonl`, `sida2` och så vidare: inmätning per lass, ett JSON-objekt per rad, "
        "hämtat i sidor om 20 lass. kord_utc är när lasset kördes, i UTC; transportdagen räknas i svensk tid. "
        "netto_m3fub är fakturerad volym, brutto_m3fub volym före avdrag.\n"
        "- `arbetsordrar.json`: arbetsordrar med planerad mottagare och grupp, med arbetsordernumret som nyckel.\n"
    )


def _report(m: Month, out: Path) -> str:
    """A BI report saved as CSV: a preamble, harvest pivoted wide by diameter, subtotals and a footer."""
    h, d = m.harvest, m.deliveries
    m.harvest = h.drop(columns=["antal_stockar"])  # the report has no log counts, so neither does the answer
    preamble = lambda title: [title, "Utskriven 2026-02-03 07:12 av rapportservern", f"Period: {PERIOD}", ""]  # noqa: E731

    wide = h.assign(d=h["diametergrupp"].astype(int)).pivot_table(
        index=["arbetsorder", "handelssortiment", "langdgrupp", "avverkningsdatum"], columns="d",
        values="volym_m3fub", aggfunc="sum")
    labels = {c: f"{c}–{c + 1},9 cm" for c in wide.columns}
    rows = []
    for ao, block in wide.groupby(level="arbetsorder"):
        for (_, sort, length, day), values in block.iterrows():
            rows.append([ao, sort, length, day] + [_decimal(pd.Series([v]))[0] if pd.notna(v) else "" for v in values])
        rows.append([f"Summa {ao}", "", "", ""] + [_decimal(pd.Series([v]))[0] for v in block.sum().round(3)])
    rows.append(["Totalt", "", "", ""] + [_decimal(pd.Series([v]))[0] for v in wide.sum().round(3)])
    header = ["Arbetsorder", "Sortiment", "Längd (cm)", "Fällningsdag"] + [labels[c] for c in wide.columns]
    lines = preamble("Rapport: Skördad volym per diameterklass, m3fub") + [";".join(header)]
    lines += [";".join(str(x) for x in row) for row in rows]
    (out / f"skordrapport_{PERIOD}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    table = pd.DataFrame({
        "Lass nr": d["leverans_id"], "Arbetsorder": d["arbetsorder"], "Sortiment": d["handelssortiment"],
        "Mottagare": d["mottagningsplats"], "Kördag": d["leveransdatum"], "Netto m3fub": _decimal(d["volym_m3fub"]),
        "Brutto m3fub": _decimal(d["brutto_m3fub"]), "Mätmetod": d["matmetod"], "Mätenheter": d["antal_matenheter"],
    })
    lines = preamble("Rapport: Inmätta lass") + [table.to_csv(sep=";", index=False).rstrip("\n"), "", f"Antal lass: {len(d)}"]
    (out / f"lassrapport_{PERIOD}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    m.orders.to_csv(out / "arbetsordrar.csv", index=False)
    return (
        "Två rapporter sparade som CSV ur rapportverktyget, semikolon och decimalkomma, med några rader text "
        "överst.\n\n"
        f"- `skordrapport_{PERIOD}.csv`: skördad volym under bark, m3fub, en kolumn per diameterklass med klassens "
        "gränser i rubriken. En rad per arbetsorder, sortiment, längdklass (nedre gräns i cm) och fällningsdag. "
        "Tom cell betyder ingen volym. Rapporten har delsummor per arbetsorder och en totalrad. Antal stockar "
        "finns inte i rapporten.\n"
        f"- `lassrapport_{PERIOD}.csv`: inmätta lass. Kördag är dagen lasset kördes. Netto är fakturerad volym, "
        "brutto volym före avdrag. Sist står antalet lass.\n"
        "- `arbetsordrar.csv`: arbetsordrar i treedists format.\n"
    )


FIXED_LAYOUT = {
    "A": [("ao", 2, 13), ("planerad", 14, 23), ("grupp", 24, 53)],
    "S": [("ao", 2, 13), ("sortiment", 14, 23), ("diameter_cm", 24, 26), ("langd_cm", 27, 29),
          ("fallt", 30, 37), ("volym", 38, 46), ("stockar", 47, 51)],
    "L": [("lass", 2, 13), ("ao", 14, 25), ("sortiment", 26, 35), ("mottagare", 36, 45), ("kordag", 46, 53),
          ("netto", 54, 62), ("brutto", 63, 71), ("metod", 72, 83), ("enheter", 84, 88)],
}


def _fixed(m: Month, out: Path) -> str:
    """A mainframe file: one fixed-width file with a record type per line and implied decimals."""
    h, d, o = m.harvest, m.deliveries, m.orders
    implied = lambda v: f"{round(v * 1000):09d}"  # noqa: E731

    def record(kind: str, **values) -> str:
        line = [" "] * 88
        line[0] = kind
        for name, first, last in FIXED_LAYOUT[kind]:
            text = str(values[name])
            width = last - first + 1
            text = text.rjust(width, "0") if text.isdigit() else text.ljust(width)
            line[first - 1:last] = list(text[:width])
        return "".join(line).rstrip()

    lines = [f"H VIRKESEXPORT {PERIOD.replace('-', '')} SKAPAD 20260203"]
    for r in o.itertuples():
        lines.append(record("A", ao=r.arbetsorder, planerad=r.destination, grupp=r.grupp))
        for s in h[h["arbetsorder"] == r.arbetsorder].itertuples():
            lines.append(record("S", ao=s.arbetsorder, sortiment=s.handelssortiment, diameter_cm=s.diametergrupp,
                                langd_cm=s.langdgrupp, fallt=s.avverkningsdatum.replace("-", ""),
                                volym=implied(s.volym_m3fub), stockar=s.antal_stockar))
        for x in d[d["arbetsorder"] == r.arbetsorder].itertuples():
            lines.append(record("L", lass=x.leverans_id, ao=x.arbetsorder, sortiment=x.handelssortiment,
                                mottagare=x.mottagningsplats, kordag=x.leveransdatum.replace("-", ""),
                                netto=implied(x.volym_m3fub), brutto=implied(x.brutto_m3fub), metod=x.matmetod,
                                enheter=x.antal_matenheter))
    counts = {k: sum(line.startswith(k) for line in lines) for k in "ASL"}
    lines.append(f"T A{counts['A']:07d} S{counts['S']:07d} L{counts['L']:07d}")
    (out / f"VIRKE_{PERIOD.replace('-', '')}.DAT").write_text("\n".join(lines) + "\n", encoding="ascii")
    layout = "\n".join(
        f"| {kind} | {name} | {first}–{last} |" for kind, fields in FIXED_LAYOUT.items() for name, first, last in fields)
    return (
        f"En fil med fast postlängd från stordatorn, `VIRKE_{PERIOD.replace('-', '')}.DAT`, ASCII. Första tecknet "
        "är posttypen: H är filhuvud, A arbetsorder, S skördad volym, L inmätt lass och T avslutning med antalet "
        "poster av varje typ. Texter är vänsterställda och utfyllda med blanksteg, tal högerställda och utfyllda "
        "med nollor. Volymer har tre underförstådda decimaler, så 000045123 är 45,123 m3fub. Datum är ÅÅÅÅMMDD.\n\n"
        "| Post | Fält | Positioner |\n|---|---|---|\n" + layout + "\n\n"
        "planerad är planerad mottagare och grupp jämförbar grupp. I S-posten är diameter_cm och langd_cm "
        "klassernas nedre gränser och volym volym under bark. I L-posten är kordag dagen lasset kördes, netto "
        "fakturerad volym och brutto volym före avdrag.\n\n"
    )


VARIANTS = {"a_semikolon": (_semicolon, 23), "b_engelska": (_english, 26), "c_lass": (_join, 29), "d_koder": (_codes, 33)}
CONTROL = {"e_semikolon": (_semicolon, 34), "f_engelska": (_english, 35), "g_lass": (_join, 24), "h_koder": (_codes, 36)}
PLATFORMS = {"i_lager": (_warehouse, 42), "j_api": (_api, 49), "k_rapport": (_report, 52), "l_stordator": (_fixed, 40)}
PLATFORM_CONTROL = {"n_lager": (_warehouse, 47), "o_api": (_api, 58), "p_rapport": (_report, 45), "q_stordator": (_fixed, 50)}
# The second month of a warehouse that holds every month: late reports were felled the month before.
HISTORY = {"m_lagerhistorik": (_warehouse_history, 70)}
HISTORY_CONTROL = {"r_lagerhistorik": (_warehouse_history, 74)}


def make(bench: Path, variants: dict) -> None:
    for name, (writer, seed) in variants.items():
        months = _months(seed, getattr(writer, "months", 1))
        month = months[-1]
        task, answer = bench / "uppgifter" / name, bench / "facit" / name
        for folder in (task, answer):
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True)
        description = writer(months if len(months) > 1 else month, task)
        example_price_list().to_csv(task / "prislista.csv", index=False)
        periods = [m.period for m in months]
        for m in months:
            m.closed.to_csv(task / f"avslutade_{m.period}.csv", index=False)
        which = f"perioden {periods[0]}" if len(months) == 1 else f"perioderna {' och '.join(periods)}, i den ordningen"
        (task / "UPPGIFT.md").write_text(
            f"# Källa {name}\n\nSkriv en källbeskrivning för treedist i den här katalogen, `kalla.toml` eller vid "
            f"behov `kalla.py`, för {which}. Läs AGENTS.md först.\n\n"
            f"## Dataägarens beskrivning\n\n{description}"
            "- `prislista.csv`: prislistan, redan i treedists format.\n"
            "- `avslutade_ÅÅÅÅ-MM.csv`: arbetsordrar som avslutades under månaden.\n",
            encoding="utf-8",
        )
        (answer / "period.txt").write_text("\n".join(periods))
        for m in months:
            folder = answer if len(months) == 1 else answer / m.period
            folder.mkdir(exist_ok=True)
            m.harvest.to_csv(folder / "skordning.csv", index=False)
            m.deliveries.to_csv(folder / "leverans.csv", index=False)
            m.orders.to_csv(folder / "arbetsordrar.csv", index=False)
            m.closed.to_csv(folder / "avslutade_ao.csv", index=False)
            example_price_list().to_csv(folder / "prislista.csv", index=False)
        print(f"Skrev {task}")


def _entry(task: Path) -> Path | None:
    """The source description a task ends in: a .py adapter may read a .toml beside it."""
    return next((task / n for n in ("kalla.py", "kalla.toml") if (task / n).exists()), None)


def _invoice(inputs, period: str) -> pd.DataFrame:
    return run_month(
        Ledger.empty(), inputs.harvest, inputs.deliveries, inputs.prices, period, inputs.closed_aos, CFG,
        inputs.work_orders,
    ).invoice


def grade_task(task: Path, answer: Path) -> str | None:
    """None if the task's source description gives exactly the answer in every period, else what differs."""
    periods = (answer / "period.txt").read_text().split() if (answer / "period.txt").exists() else [PERIOD]
    for period in periods:
        failure = _grade_period(task, answer if len(periods) == 1 else answer / period, period)
        if failure:
            return f"{period} {failure}" if len(periods) > 1 else failure
    return None


def _grade_period(task: Path, answer: Path, period: str) -> str | None:
    files = {key: answer / f"{key}.csv" for key in ("skordning", "leverans", "prislista", "arbetsordrar", "avslutade_ao")}
    source = _entry(task)
    if source is None:
        return "ingen källbeskrivning"
    try:
        truth, got = load(period, CFG, files=files), load(period, CFG, source=source)
        for name in ("harvest", "deliveries"):
            expected = getattr(truth, name).sort_values(list(getattr(truth, name).columns)).reset_index(drop=True)
            actual = getattr(got, name)
            actual = actual[expected.columns].sort_values(list(expected.columns)).reset_index(drop=True)
            pd.testing.assert_frame_equal(actual, expected, check_dtype=False, rtol=1e-6)
        assert got.work_orders == truth.work_orders, "arbetsordrarna skiljer"
        assert got.closed_aos == truth.closed_aos, "avslutade arbetsordrar skiljer"
        pd.testing.assert_frame_equal(_invoice(got, period), _invoice(truth, period), check_dtype=False)
    except Exception as error:  # noqa: BLE001  any failure is a failed task
        first = str(error).strip().splitlines()
        return f"({source.name}) {' '.join(first[:3])[:300]}"
    return None


def grade(bench: Path) -> int:
    passed = 0
    tasks = sorted(p for p in (bench / "uppgifter").iterdir() if p.is_dir())
    for task in tasks:
        failure = grade_task(task, bench / "facit" / task.name)
        if failure:
            print(f"UNDERKÄND {task.name}: {failure}")
            continue
        passed += 1
        print(f"GODKÄND  {task.name} ({_entry(task).name})")
    print(f"\n{passed} av {len(tasks)} godkända")
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("felkatalog")
    catalog.add_argument("--dir", type=Path, help="Också falsklarm på uppgifternas godkända källbeskrivningar")
    catalog.add_argument("--kontroll", action="store_true", help="Kontrollkatalogen, som inget beslut använt")
    for name in ("skapa", "rätta"):
        command = commands.add_parser(name)
        command.add_argument("--dir", type=Path, required=True)
        command.add_argument("--kontroll", action="store_true")
        command.add_argument("--plattform", action="store_true", help="Datalager, API, rapport och stordator")
        command.add_argument("--historik", action="store_true", help="Andra månaden ur ett datalager med alla månader")
    args = parser.parse_args()
    if args.command == "felkatalog":
        mistakes(CONTROL_MISTAKES if args.kontroll else MISTAKES)
        false_alarms(args.dir)
    elif args.command == "skapa":
        if args.historik:
            variants = HISTORY_CONTROL if args.kontroll else HISTORY
        elif args.plattform:
            variants = PLATFORM_CONTROL if args.kontroll else PLATFORMS
        else:
            variants = CONTROL if args.kontroll else VARIANTS
        make(args.dir, variants)
    else:
        grade(args.dir)


if __name__ == "__main__":
    sys.exit(main())
