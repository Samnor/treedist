"""How well does treedist move to new data? Two measures for the portability climb.

    uv run python scripts/portability_bench.py felkatalog
        Plants common mapping mistakes in examples/kalla and counts how many
        `treedist check` notices. Deterministic.

    uv run python scripts/portability_bench.py skapa --dir BENCH [--kontroll] [--plattform | --historik | --svara]
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
from treedist.dev.simulate import SimParams, simulate

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "kalla"
PERIOD = "2026-01"
CFG = Config()


# --- Mistakes a mapping can make: (name, text in kalla.toml, replacement). ---

MISTAKES = [
    ("diameter i mm som cm", "diameter_grupp_placeholder", ""),
    ("redovisningsdatum som leveransdatum", 'leveransdatum = "TransportDatum"', 'leveransdatum = "RedovisningDatum"'),
    ("brutto och netto bytta", 'volym_m3fub = "NettoFub"\nbrutto_m3fub = "BruttoFub"',
     'volym_m3fub = "BruttoFub"\nbrutto_m3fub = "NettoFub"'),
    ("brutto samma kolumn som netto", 'brutto_m3fub = "BruttoFub"', 'brutto_m3fub = "NettoFub"'),
    ("längd i dm", "[produktion.enheter]\n", "[produktion.enheter]\nlangdklass = 0.1\n"),
    ("inmätt volym i dm3", "[matning.filter]", "[matning.enheter]\nvolym_m3fub = 1000\nbrutto_m3fub = 1000\n\n[matning.filter]"),
    ("skördad volym i dm3", "[produktion.enheter]\n", "[produktion.enheter]\nvolym_m3fub = 1000\n"),
    ("lassnummer som avtalsobjekt", 'leveransnummer = "Lassnr"\navtalsobjekt = "AO_Nr"', 'leveransnummer = "Lassnr"\navtalsobjekt = "Lassnr"'),
    ("leveransdatum saknas", 'leveransdatum = "TransportDatum"   # dagen lasset kördes, inte RedovisningDatum\n', ""),
    ("makulerade lass med", '[matning.filter]\nStatus = "Godkänd"\n', ""),
    ("diameter som klassmitt", "diameterklass = 0.1   # mm -> cm", "diameterklass = 0.1   # mm -> cm\n# MITT"),
    ("antal stockar från fel kolumn", 'antal_stockar = "AntalStockar"', 'antal_stockar = "DiamKlassMM"'),
    # From the first round's control.
    # The sortiment matched against the production; an inmätt sortiment that is wrong is not noticed by check.
    ("mottagare som sortiment", 'producerat_handelssortiment = "KapatSortiment"',
     'producerat_handelssortiment = "Mottagare"'),
    ("avtalsobjekt som mottagningsplats", 'mottagningsplats = "Mottagare"', 'mottagningsplats = "AO_Nr"'),
    ("antal stockar som skördad volym", 'volym_m3fub = "VolymFub"', 'volym_m3fub = "AntalStockar"'),
    ("dag och månad bytta i leveransdatum", 'separator = ";"\ndatumformat = "%Y%m%d"\n\n[matning.kolumner]',
     'separator = ";"\ndatumformat = "%Y%d%m"\n\n[matning.kolumner]'),
    ("avtalsobjekt som lassnummer", 'leveransnummer = "Lassnr"', 'leveransnummer = "AO_Nr"'),
]


# Control: written before the second round's decisions and used once, to see whether the checks generalise.
# The first round's control mistakes moved into MISTAKES once decisions used them.
CONTROL_MISTAKES = [
    ("diameter och längd bytta", 'diameterklass = "DiamKlassMM"\nlangdklass = "LangdKlassCM"',
     'diameterklass = "LangdKlassCM"\nlangdklass = "DiamKlassMM"'),
    ("transportstatus som avtalsobjekt i avtalsobjekt", 'avtalsobjekt = "AO"\ntransport_avslutad = "TransportKlar"',
     'avtalsobjekt = "TransportKlar"\ntransport_avslutad = "TransportKlar"'),
    ("ett sortiment som konstant i inmätningen", [('handelssortiment = "InmattSortiment"             # det inmätta, som faktureras\n', ""),
     ("[matning.filter]", '[matning.konstanter]\nhandelssortiment = "TALL_SAG"\n\n[matning.filter]')]),
    ("antal enheter som bruttovolym", 'brutto_m3fub = "BruttoFub"', 'brutto_m3fub = "AntalEnheter"'),
    ("dag och månad bytta i fällningsdatum", '[produktion]\nfil = "export/produktion_{period}.csv"\nseparator = ";"\ndatumformat = "%Y%m%d"',
     '[produktion]\nfil = "export/produktion_{period}.csv"\nseparator = ";"\ndatumformat = "%Y%d%m"'),
]


def _mistake_source(tmp: Path, edits: list[tuple[str, str]]) -> Path:
    text = (EXAMPLE / "kalla.toml").read_text(encoding="utf-8")
    export = EXAMPLE / "export"
    for old, new in edits:
        if old == "diameter_grupp_placeholder":
            old, new = "diameterklass = 0.1   # mm -> cm", ""
        if new.endswith("# MITT"):
            # Class midpoints: export the class bottom plus half a 1 cm class.
            export = tmp / "export"
            shutil.copytree(EXAMPLE / "export", export, dirs_exist_ok=True)
            harvest = pd.read_csv(export / f"produktion_{PERIOD}.csv", sep=";", dtype=str)
            harvest["DiamKlassMM"] = (harvest["DiamKlassMM"].astype(int) + 5).astype(str)
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
    # Every avtalsobjekt so far, with transport_avslutad "true" or "false" at the month's end: the answer's table.
    orders: pd.DataFrame
    # The day the transport from each finished avtalsobjekt ended, for sources that keep a date instead of a flag.
    finished: dict[str, str]
    period: str = PERIOD


def _months(seed: int, count: int = 1) -> list[Month]:
    months, finished = [], {}
    for month in simulate(SimParams(months=count, seed=seed, work_orders_per_month=10)):
        d = month.deliveries
        last_day = pd.Period(month.period, "M").end_time.strftime("%Y-%m-%d")
        for ao in sorted(month.transport_done):
            days = d.loc[d["avtalsobjekt"] == ao, "leveransdatum"]
            finished[ao] = days.max() if len(days) else last_day
        orders = pd.DataFrame({"avtalsobjekt": sorted(set(month.destinations) | set(finished))})
        orders["transport_avslutad"] = orders["avtalsobjekt"].isin(set(finished)).map({True: "true", False: "false"})
        months.append(Month(month.harvest, month.deliveries, orders, dict(finished), month.period))
    return months


def _month(seed: int) -> Month:
    return _months(seed)[0]


def _comma(values: pd.Series) -> pd.Series:
    return values.map(lambda v: f"{v:g}".replace(".", ","))


def _flag(m: Month, yes: str, no: str) -> pd.Series:
    """The month's finished transport in the source's own words."""
    return m.orders["transport_avslutad"].map({"true": yes, "false": no})


def _semicolon(m: Month, out: Path) -> str:
    """Like the example, but with its own names."""
    h, d = m.harvest, m.deliveries
    pd.DataFrame({
        "Arbetsorder": h["avtalsobjekt"], "Sort": h["producerat_handelssortiment"],
        "Avsedd": h["producerat_for_mottagningsplats"], "Diam_mm": h["diameterklass"].astype(int) * 10,
        "Langd_cm": h["langdklass"], "Fub": _comma(h["volym_m3fub"]), "Stammar": h["antal_stockar"],
        "Avverkad": h["avverkningsdatum"].str.replace("-", ""),
    }).to_csv(out / f"skord_{PERIOD}.csv", sep=";", index=False)
    pd.DataFrame({
        "Lass": d["leveransnummer"], "Arbetsorder": d["avtalsobjekt"], "Sort": d["handelssortiment"],
        "SkordadSort": d["producerat_handelssortiment"], "Mottagare": d["mottagningsplats"],
        "Avsedd": d["producerat_for_mottagningsplats"], "Kordatum": d["leveransdatum"].str.replace("-", ""),
        "Matdatum": d["matdatum"].str.replace("-", ""), "Bokford": f"{PERIOD.replace('-', '')}28",
        "NettoFub": _comma(d["volym_m3fub"]), "BruttoFub": _comma(d["brutto_m3fub"]), "Metod": d["matmetod"],
        "Enheter": d["antal_matenheter"],
    }).to_csv(out / f"mat_{PERIOD}.csv", sep=";", index=False)
    pd.DataFrame({"Arbetsorder": m.orders["avtalsobjekt"], "Avslutad": _flag(m, "J", "N")}).to_csv(
        out / "ao.csv", sep=";", index=False)
    return (
        "Exporterna är semikolonseparerade med decimalkomma.\n\n"
        f"- `skord_{PERIOD}.csv`: skördarens produktion per arbetsorder. Sort är sortimentet skördaren kapade och "
        "Avsedd mottagaren det kapades för. Diam_mm är diameterklassens nedre gräns i millimeter, "
        "Langd_cm längdklassens nedre gräns i centimeter, Fub volym under bark i m3, Stammar antal stockar, "
        "Avverkad fällningsdag som ÅÅÅÅMMDD.\n"
        f"- `mat_{PERIOD}.csv`: inmätning vid industri per lass. Sort är sortimentet industrin mätte in och "
        "fakturerar, SkordadSort det skördaren kapade. Mottagare är industrin där lasset mättes in, Avsedd "
        "mottagaren virket kapades för. Kordatum är när lasset kördes, Matdatum när det mättes in och Bokford när "
        "det bokfördes. NettoFub är fakturerad volym, BruttoFub volym före avdrag. Metod är mätmetoden.\n"
        "- `ao.csv`: arbetsordrar vid månadens slut. Avslutad är J när inga fler lass ska köras från arbetsordern, "
        "annars N.\n"
    )


def _english(m: Month, out: Path) -> str:
    """Tab separated latin-1 with English names, lengths in dm and delivered volume in dm3."""
    h, d = m.harvest, m.deliveries
    day = lambda s: pd.to_datetime(s).dt.strftime("%d.%m.%Y")  # noqa: E731
    pd.DataFrame({
        "WorkOrder": h["avtalsobjekt"], "Assortment": h["producerat_handelssortiment"],
        "CutForMill": h["producerat_for_mottagningsplats"], "DiaClassCm": h["diameterklass"],
        "LenClassDm": (h["langdklass"].astype(int) // 10), "VolUB_m3": h["volym_m3fub"], "Logs": h["antal_stockar"],
        "FellingDate": day(h["avverkningsdatum"]),
    }).to_csv(out / f"harvest_{PERIOD}.txt", sep="\t", index=False, encoding="latin-1")
    pd.DataFrame({
        "TruckLoad": d["leveransnummer"], "WorkOrder": d["avtalsobjekt"], "Assortment": d["handelssortiment"],
        "HarvestedAssortment": d["producerat_handelssortiment"], "Mill": d["mottagningsplats"],
        "CutForMill": d["producerat_for_mottagningsplats"], "HaulDate": day(d["leveransdatum"]),
        "ScaleDate": day(d["matdatum"]),
        "NetUB_dm3": (d["volym_m3fub"] * 1000).round(0).astype(int), "GrossUB_dm3": (d["brutto_m3fub"] * 1000).round(0).astype(int),
        "Method": d["matmetod"], "Units": d["antal_matenheter"], "Säsong": "vinter",
    }).to_csv(out / f"scaling_{PERIOD}.txt", sep="\t", index=False, encoding="latin-1")
    pd.DataFrame({"WorkOrder": m.orders["avtalsobjekt"], "HaulingDone": _flag(m, "Yes", "No")}).to_csv(
        out / "workorders.txt", sep="\t", index=False, encoding="latin-1")
    return (
        "Tabbseparerade textfiler i latin-1.\n\n"
        f"- `harvest_{PERIOD}.txt`: skördarens produktion per arbetsorder (WorkOrder). Assortment är sortimentet "
        "skördaren kapade och CutForMill sågverket det kapades för. DiaClassCm är diameterklassens nedre gräns i cm, "
        "LenClassDm längdklassens nedre gräns i decimeter, VolUB_m3 volym under bark, Logs antal stockar, "
        "FellingDate fällningsdag som DD.MM.ÅÅÅÅ.\n"
        f"- `scaling_{PERIOD}.txt`: inmätning per lass. Assortment är det inmätta sortimentet, som faktureras, och "
        "HarvestedAssortment det skördaren kapade. Mill är sågverket där lasset mättes in, CutForMill det virket "
        "kapades för. HaulDate är transportdagen och ScaleDate mätdagen. NetUB_dm3 är fakturerad "
        "volym och GrossUB_dm3 volym före avdrag, båda i kubikdecimeter under bark.\n"
        "- `workorders.txt`: arbetsordrar vid månadens slut. HaulingDone är Yes när transporten från arbetsordern "
        "är avslutad, annars No.\n"
    )


def _join(m: Month, out: Path) -> str:
    """The deliveries name only the truck; which work order it came from is in another file."""
    h, d = m.harvest, m.deliveries
    h.to_csv(out / f"produktion_{PERIOD}.csv", index=False)
    d.drop(columns=["avtalsobjekt"]).rename(columns={"leveransnummer": "lass"}).to_csv(
        out / f"inmatning_{PERIOD}.csv", index=False)
    d[["leveransnummer", "avtalsobjekt"]].rename(columns={"leveransnummer": "lass", "avtalsobjekt": "ao"}).to_csv(
        out / f"lass_ao_{PERIOD}.csv", index=False)
    m.orders.assign(transport_avslutad=_flag(m, "1", "0")).to_csv(out / f"avtalsobjekt_{PERIOD}.csv", index=False)
    return (
        "Kommaseparerade filer med punkt som decimaltecken.\n\n"
        f"- `produktion_{PERIOD}.csv`: skördarens produktion, redan i treedists kolumnnamn.\n"
        f"- `inmatning_{PERIOD}.csv`: inmätning per lass, i treedists kolumnnamn men utan arbetsorder. "
        "Kolumnen lass är lassnumret.\n"
        f"- `lass_ao_{PERIOD}.csv`: vilken arbetsorder (ao) varje lass kom från.\n"
        f"- `avtalsobjekt_{PERIOD}.csv`: arbetsordrarna vid månadens slut, i treedists kolumnnamn, men "
        "transport_avslutad är 1 när transporten är avslutad och 0 annars.\n"
    )


def _codes(m: Month, out: Path) -> str:
    """Assortments as codes, work orders without their prefix in the delivery system."""
    h, d = m.harvest, m.deliveries
    codes = {"TALL_SAG": "110", "GRAN_SAG": "210"}
    h.assign(producerat_handelssortiment=h["producerat_handelssortiment"].map(codes)).to_csv(
        out / f"skord_{PERIOD}.csv", index=False)
    d.assign(
        avtalsobjekt=d["avtalsobjekt"].str.replace("AO", "", regex=False),
        handelssortiment=d["handelssortiment"].map(codes),
        producerat_handelssortiment=d["producerat_handelssortiment"].map(codes),
    ).to_csv(out / f"inmatning_{PERIOD}.csv", index=False)
    m.orders.assign(transport_avslutad=_flag(m, "Ja", "Nej")).to_csv(out / "arbetsordrar.csv", index=False)
    pd.DataFrame({"kod": list(codes.values()), "namn": list(codes)}).to_csv(out / "sortimentskoder.csv", index=False)
    return (
        "Kommaseparerade filer i treedists kolumnnamn, men med tre skillnader mot treedist:\n\n"
        "- Sortiment anges som koder i både skördardata och inmätning. `sortimentskoder.csv` ger namnet "
        "för varje kod.\n"
        "- Inmätningssystemet tar bort prefixet AO från arbetsordernumret: AO00012 i skördardatan heter 00012 "
        "i inmätningen.\n"
        "- `arbetsordrar.csv` är arbetsordrarna vid månadens slut, och där är transport_avslutad Ja när "
        "transporten är avslutad och Nej annars.\n"
    )


# --- Other kinds of platform than a file export: none of these can be read by a TOML mapping alone. ---


def _decimal(values: pd.Series, comma: bool = True) -> pd.Series:
    text = values.map(lambda v: f"{v:.3f}".rstrip("0").rstrip("."))
    return text.str.replace(".", ",", regex=False) if comma else text


def _warehouse(m: Month, out: Path) -> str:
    """A data warehouse: surrogate keys, dimension tables, volumes in dm3 and superseded versions of loads."""
    _star(out, m.harvest, m.deliveries, m.orders, m.finished, {})
    return WAREHOUSE_TEXT


def _warehouse_history(months: list[Month], out: Path) -> str:
    """The same warehouse with every month so far: the month's harvest is what was reported in it."""
    report_month = [m.harvest["avverkningsdatum"].map(lambda _, p=m.period: int(p.replace("-", ""))) for m in months]
    harvest = pd.concat([m.harvest for m in months], ignore_index=True)
    _star(out, harvest, pd.concat([m.deliveries for m in months], ignore_index=True), months[-1].orders,
          months[-1].finished, {"rapport_manad": pd.concat(report_month, ignore_index=True)})
    return WAREHOUSE_TEXT + (
        "\nLagret har alla månader hittills. I `fakta_skord` är rapport_manad månaden skördaren rapporterade "
        "raden, som ÅÅÅÅMM. I `dim_ao` står bara dagens läge: en arbetsorder var avslutad vid en månads slut om "
        "transport_klar_datum_key är den månadens sista dag eller tidigare.\n"
    )


_warehouse_history.months = 2


def _star(out: Path, h: pd.DataFrame, d: pd.DataFrame, o: pd.DataFrame, finished: dict[str, str],
          extra_harvest: dict) -> None:
    rng = np.random.default_rng(len(d))
    ao_key = {ao: 1000 + 7 * i for i, ao in enumerate(o["avtalsobjekt"])}
    sort_key = {"TALL_SAG": 11, "GRAN_SAG": 12}
    mills = sorted(set(d["mottagningsplats"]) | set(d["producerat_for_mottagningsplats"])
                   | set(h["producerat_for_mottagningsplats"]))
    mill_key = {name: 501 + i for i, name in enumerate(mills)}
    day_key = lambda s: s.str.replace("-", "").astype(int)  # noqa: E731
    dm3 = lambda v: (v * 1000).round(0).astype(int)  # noqa: E731

    loads = pd.DataFrame({
        "lass_id": d["leveransnummer"], "version": 1, "giltig": 1, "ao_key": d["avtalsobjekt"].map(ao_key),
        "sortiment_key": d["handelssortiment"].map(sort_key),
        "skordat_sortiment_key": d["producerat_handelssortiment"].map(sort_key),
        "mottagare_key": d["mottagningsplats"].map(mill_key),
        "kapad_for_mottagare_key": d["producerat_for_mottagningsplats"].map(mill_key),
        "kord_datum_key": day_key(d["leveransdatum"]), "mat_datum_key": day_key(d["matdatum"]),
        "netto_dm3": dm3(d["volym_m3fub"]), "brutto_dm3": dm3(d["brutto_m3fub"]), "matmetod": d["matmetod"],
        "matenheter": d["antal_matenheter"],
    })
    # A remeasurement writes a new version of the load and keeps the old one as invalid.
    remeasured = rng.random(len(loads)) < 0.15
    old = loads[remeasured].assign(giltig=0, netto_dm3=lambda t: (t["netto_dm3"] * 0.94).round(0).astype(int))
    loads.loc[remeasured, "version"] = 2
    loads = pd.concat([old, loads]).sample(frac=1, random_state=1)

    with sqlite3.connect(out / "lager.sqlite") as db:
        pd.DataFrame({
            "ao_key": o["avtalsobjekt"].map(ao_key), "ao_nr": o["avtalsobjekt"],
            "transport_klar_datum_key": o["avtalsobjekt"].map(
                lambda ao: int(finished[ao].replace("-", "")) if ao in finished else None).astype("Int64"),
        }).to_sql("dim_ao", db, index=False)
        pd.DataFrame({"mottagare_key": list(mill_key.values()), "namn": list(mill_key)}).to_sql("dim_mottagare", db, index=False)
        pd.DataFrame({"sortiment_key": list(sort_key.values()), "namn": list(sort_key)}).to_sql("dim_sortiment", db, index=False)
        pd.DataFrame({
            "ao_key": h["avtalsobjekt"].map(ao_key), "sortiment_key": h["producerat_handelssortiment"].map(sort_key),
            "kapad_for_mottagare_key": h["producerat_for_mottagningsplats"].map(mill_key),
            "diameter_mm": h["diameterklass"].astype(int) * 10, "langd_cm": h["langdklass"].astype(int),
            "fallt_datum_key": day_key(h["avverkningsdatum"]), "volym_dm3": dm3(h["volym_m3fub"]),
            "antal_stockar": h["antal_stockar"], **extra_harvest,
        }).to_sql("fakta_skord", db, index=False)
        loads.to_sql("fakta_lass", db, index=False)


WAREHOUSE_TEXT = (
    "Allt ligger i datalagret `lager.sqlite` (SQLite), som en stjärnmodell med surrogatnycklar.\n\n"
    "- `dim_ao`: arbetsordrar. ao_nr är arbetsordernumret. transport_klar_datum_key är dagen transporten från "
    "arbetsordern avslutades, som heltal ÅÅÅÅMMDD, och tom så länge lass återstår.\n"
    "- `dim_mottagare` och `dim_sortiment`: namnen bakom nycklarna.\n"
    "- `fakta_skord`: skördarens produktion. sortiment_key är sortimentet skördaren kapade och "
    "kapad_for_mottagare_key mottagaren det kapades för. diameter_mm är diameterklassens nedre gräns i millimeter, "
    "langd_cm längdklassens nedre gräns, fallt_datum_key fällningsdagen som heltal ÅÅÅÅMMDD, volym_dm3 volym under "
    "bark i kubikdecimeter.\n"
    "- `fakta_lass`: inmätning per lass. sortiment_key är det inmätta sortimentet, som faktureras, och "
    "skordat_sortiment_key det skördaren kapade. mottagare_key är mottagaren där lasset mättes in och "
    "kapad_for_mottagare_key den virket kapades för. kord_datum_key är dagen lasset kördes och mat_datum_key "
    "dagen det mättes in. netto_dm3 är fakturerad volym och brutto_dm3 volym före avdrag, i kubikdecimeter under "
    "bark. En ommätning skriver en ny version av lasset; bara raden med giltig = 1 gäller.\n"
)


def _api(m: Month, out: Path) -> str:
    """JSON from a REST API: nested harvest, loads in pages with UTC timestamps, work orders keyed by number."""
    h, d = m.harvest, m.deliveries
    rng = np.random.default_rng(len(d))
    harvest = [
        {"arbetsorder": ao, "sortiment": sort, "kapad_for": mill, "klasser": [
            {"d_cm": int(r.diameterklass), "l_cm": int(r.langdklass), "fallt": r.avverkningsdatum,
             "m3fub": float(r.volym_m3fub), "stockar": int(r.antal_stockar)} for r in group.itertuples()]}
        for (ao, sort, mill), group in h.groupby(
            ["avtalsobjekt", "producerat_handelssortiment", "producerat_for_mottagningsplats"])
    ]
    (out / f"skord_{PERIOD}.json").write_text(json.dumps({"antal": len(harvest), "data": harvest}, ensure_ascii=False))

    # Night loads: a load driven just after midnight in Sweden is the day before in UTC.
    minutes = np.where(rng.random(len(d)) < 0.25, rng.integers(0, 60, len(d)), rng.integers(60, 24 * 60, len(d)))
    utc = lambda days: (pd.to_datetime(days) + pd.to_timedelta(minutes, unit="min")).dt.tz_localize(  # noqa: E731
        "Europe/Stockholm").dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    loads = [
        {"lass": r.leveransnummer, "arbetsorder": r.avtalsobjekt,
         "sortiment": {"inmatt": r.handelssortiment, "skordat": r.producerat_handelssortiment},
         "mottagare": {"kod": r.mottagningsplats}, "kapad_for": {"kod": r.producerat_for_mottagningsplats},
         "kord_utc": driven,
         "matning": {"matt_utc": measured, "metod": r.matmetod, "enheter": int(r.antal_matenheter),
                     "netto_m3fub": float(r.volym_m3fub), "brutto_m3fub": float(r.brutto_m3fub)}}
        for r, driven, measured in zip(d.itertuples(), utc(d["leveransdatum"]), utc(d["matdatum"]))
    ]
    for page, start in enumerate(range(0, len(loads), 20), start=1):
        lines = [json.dumps(load, ensure_ascii=False) for load in loads[start:start + 20]]
        (out / f"lass_{PERIOD}_sida{page}.jsonl").write_text("\n".join(lines) + "\n")
    status = _flag(m, "transport avslutad", "pågår")
    orders = {ao: {"status": s} for ao, s in zip(m.orders["avtalsobjekt"], status)}
    (out / "arbetsordrar.json").write_text(json.dumps(orders, ensure_ascii=False, indent=2))
    return (
        "JSON hämtat från leverantörens REST-API.\n\n"
        f"- `skord_{PERIOD}.json`: skördarens produktion per arbetsorder, sortiment och mottagare det kapades för "
        "(kapad_for), med en lista av klasser. d_cm och l_cm är klassernas nedre gränser i cm, fallt "
        "fällningsdagen, m3fub volym under bark, stockar antal stockar.\n"
        f"- `lass_{PERIOD}_sida1.jsonl`, `sida2` och så vidare: inmätning per lass, ett JSON-objekt per rad, "
        "hämtat i sidor om 20 lass. sortiment.inmatt är det inmätta sortimentet, som faktureras, och "
        "sortiment.skordat det skördaren kapade. mottagare är där lasset mättes in och kapad_for mottagaren "
        "virket kapades för. kord_utc är när lasset kördes och matning.matt_utc när det mättes in, i UTC; dagarna "
        "räknas i svensk tid. netto_m3fub är fakturerad volym, brutto_m3fub volym före avdrag.\n"
        "- `arbetsordrar.json`: arbetsordrarna vid månadens slut, med arbetsordernumret som nyckel. status är "
        "\"transport avslutad\" när inga fler lass ska köras, annars \"pågår\".\n"
    )


def _report(m: Month, out: Path) -> str:
    """A BI report saved as CSV: a preamble, harvest pivoted wide by diameter, subtotals and a footer."""
    h, d = m.harvest, m.deliveries
    m.harvest = h.drop(columns=["antal_stockar"])  # the report has no log counts, so neither does the answer
    preamble = lambda title: [title, "Utskriven 2026-02-03 07:12 av rapportservern", f"Period: {PERIOD}", ""]  # noqa: E731

    keys = ["avtalsobjekt", "producerat_handelssortiment", "producerat_for_mottagningsplats", "langdklass",
            "avverkningsdatum"]
    wide = h.assign(d=h["diameterklass"].astype(int)).pivot_table(
        index=keys, columns="d", values="volym_m3fub", aggfunc="sum")
    labels = {c: f"{c}–{c + 1},9 cm" for c in wide.columns}
    blank = [""] * (len(keys) - 1)
    rows = []
    for ao, block in wide.groupby(level="avtalsobjekt"):
        for index, values in block.iterrows():
            rows.append(list(index) + [_decimal(pd.Series([v]))[0] if pd.notna(v) else "" for v in values])
        rows.append([f"Summa {ao}"] + blank + [_decimal(pd.Series([v]))[0] for v in block.sum().round(3)])
    rows.append(["Totalt"] + blank + [_decimal(pd.Series([v]))[0] for v in wide.sum().round(3)])
    header = ["Arbetsorder", "Sortiment", "Kapad för", "Längd (cm)", "Fällningsdag"] + [labels[c] for c in wide.columns]
    lines = preamble("Rapport: Skördad volym per diameterklass, m3fub") + [";".join(header)]
    lines += [";".join(str(x) for x in row) for row in rows]
    (out / f"skordrapport_{PERIOD}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    table = pd.DataFrame({
        "Lass nr": d["leveransnummer"], "Arbetsorder": d["avtalsobjekt"], "Sortiment": d["handelssortiment"],
        "Skördat sortiment": d["producerat_handelssortiment"], "Mottagare": d["mottagningsplats"],
        "Kapad för": d["producerat_for_mottagningsplats"], "Kördag": d["leveransdatum"], "Mätdag": d["matdatum"],
        "Netto m3fub": _decimal(d["volym_m3fub"]), "Brutto m3fub": _decimal(d["brutto_m3fub"]),
        "Mätmetod": d["matmetod"], "Mätenheter": d["antal_matenheter"],
    })
    lines = preamble("Rapport: Inmätta lass") + [table.to_csv(sep=";", index=False).rstrip("\n"), "", f"Antal lass: {len(d)}"]
    (out / f"lassrapport_{PERIOD}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    orders = pd.DataFrame({"Arbetsorder": m.orders["avtalsobjekt"], "Transport": _flag(m, "Avslutad", "Pågående")})
    lines = preamble("Rapport: Arbetsordrar") + [orders.to_csv(sep=";", index=False).rstrip("\n"), "",
                                                 f"Antal arbetsordrar: {len(orders)}"]
    (out / f"aorapport_{PERIOD}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return (
        "Tre rapporter sparade som CSV ur rapportverktyget, semikolon och decimalkomma, med några rader text "
        "överst.\n\n"
        f"- `skordrapport_{PERIOD}.csv`: skördad volym under bark, m3fub, en kolumn per diameterklass med klassens "
        "gränser i rubriken. En rad per arbetsorder, sortiment skördaren kapade, mottagare det kapades för (Kapad "
        "för), längdklass (nedre gräns i cm) och fällningsdag. "
        "Tom cell betyder ingen volym. Rapporten har delsummor per arbetsorder och en totalrad. Antal stockar "
        "finns inte i rapporten.\n"
        f"- `lassrapport_{PERIOD}.csv`: inmätta lass. Sortiment är det inmätta, som faktureras, och Skördat "
        "sortiment det skördaren kapade. Mottagare är där lasset mättes in och Kapad för mottagaren virket kapades "
        "för. Kördag är dagen lasset kördes och Mätdag dagen det mättes in. Netto är fakturerad volym, "
        "brutto volym före avdrag. Sist står antalet lass.\n"
        f"- `aorapport_{PERIOD}.csv`: arbetsordrarna vid månadens slut. Transport är Avslutad när inga fler lass "
        "ska köras, annars Pågående. Sist står antalet arbetsordrar.\n"
    )


FIXED_LAYOUT = {
    "A": [("ao", 2, 13), ("klar", 14, 14)],
    "S": [("ao", 2, 13), ("sortiment", 14, 23), ("kapad_for", 24, 33), ("diameter_cm", 34, 36),
          ("langd_cm", 37, 39), ("fallt", 40, 47), ("volym", 48, 56), ("stockar", 57, 61)],
    "L": [("lass", 2, 13), ("ao", 14, 25), ("sortiment", 26, 35), ("skordat", 36, 45), ("mottagare", 46, 55),
          ("kapad_for", 56, 65), ("kordag", 66, 73), ("matdag", 74, 81), ("netto", 82, 90), ("brutto", 91, 99),
          ("metod", 100, 111), ("enheter", 112, 116)],
}


def _fixed(m: Month, out: Path) -> str:
    """A mainframe file: one fixed-width file with a record type per line and implied decimals."""
    h, d = m.harvest, m.deliveries
    implied = lambda v: f"{round(v * 1000):09d}"  # noqa: E731
    width = max(last for fields in FIXED_LAYOUT.values() for _, _, last in fields)

    def record(kind: str, **values) -> str:
        line = [" "] * width
        line[0] = kind
        for name, first, last in FIXED_LAYOUT[kind]:
            text = str(values[name])
            size = last - first + 1
            text = text.rjust(size, "0") if text.isdigit() else text.ljust(size)
            line[first - 1:last] = list(text[:size])
        return "".join(line).rstrip()

    lines = [f"H VIRKESEXPORT {PERIOD.replace('-', '')} SKAPAD 20260203"]
    for ao, klar in zip(m.orders["avtalsobjekt"], _flag(m, "J", "N")):
        lines.append(record("A", ao=ao, klar=klar))
        for s in h[h["avtalsobjekt"] == ao].itertuples():
            lines.append(record("S", ao=s.avtalsobjekt, sortiment=s.producerat_handelssortiment,
                                kapad_for=s.producerat_for_mottagningsplats, diameter_cm=s.diameterklass,
                                langd_cm=s.langdklass, fallt=s.avverkningsdatum.replace("-", ""),
                                volym=implied(s.volym_m3fub), stockar=s.antal_stockar))
        for x in d[d["avtalsobjekt"] == ao].itertuples():
            lines.append(record("L", lass=x.leveransnummer, ao=x.avtalsobjekt, sortiment=x.handelssortiment,
                                skordat=x.producerat_handelssortiment, mottagare=x.mottagningsplats,
                                kapad_for=x.producerat_for_mottagningsplats, kordag=x.leveransdatum.replace("-", ""),
                                matdag=x.matdatum.replace("-", ""), netto=implied(x.volym_m3fub),
                                brutto=implied(x.brutto_m3fub), metod=x.matmetod, enheter=x.antal_matenheter))
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
        "I A-posten är klar J när transporten från arbetsordern är avslutad vid månadens slut, annars N. I S-posten "
        "är sortiment det skördaren kapade, kapad_for mottagaren det kapades för, diameter_cm och langd_cm "
        "klassernas nedre gränser och volym volym under bark. I L-posten är sortiment det inmätta sortimentet, som "
        "faktureras, skordat det skördaren kapade, mottagare där lasset mättes in och kapad_for mottagaren virket "
        "kapades för. kordag är dagen lasset kördes, matdag dagen det mättes in, netto fakturerad volym och brutto "
        "volym före avdrag.\n\n"
    )


# --- Traps from AGENTS.md that a plausible description gets wrong without any error. ---


def _reclassified(m: Month, out: Path) -> str:
    """The mill booked some loads as the other assortment, measured some days later and booked them later still."""
    d = m.deliveries.copy()
    rng = np.random.default_rng(len(d))
    other = {"TALL_SAG": "GRAN_SAG", "GRAN_SAG": "TALL_SAG"}
    moved = rng.random(len(d)) < 0.2
    d.loc[moved, "handelssortiment"] = d.loc[moved, "producerat_handelssortiment"].map(other)
    driven = pd.to_datetime(d["leveransdatum"])
    # Measured up to two days after the load was driven, within the month; booked up to five days after that.
    last_day = pd.Period(m.period, "M").end_time.normalize()
    measured = (driven + pd.to_timedelta(rng.integers(0, 3, len(d)), unit="D")).clip(upper=last_day)
    d["matdatum"] = measured.dt.strftime("%Y-%m-%d")
    m.deliveries = d
    booked = (measured + pd.to_timedelta(rng.integers(0, 6, len(d)), unit="D")).dt.strftime("%Y-%m-%d")
    pd.DataFrame({
        "Lass": d["leveransnummer"], "AO": d["avtalsobjekt"], "SkordatSortiment": d["producerat_handelssortiment"],
        "InmattSortiment": d["handelssortiment"], "Mottagare": d["mottagningsplats"],
        "KapadFor": d["producerat_for_mottagningsplats"], "Kord": d["leveransdatum"], "Matt": d["matdatum"],
        "Bokford": booked, "Netto": _decimal(d["volym_m3fub"], comma=False), "Brutto": _decimal(d["brutto_m3fub"], comma=False),
        "Metod": d["matmetod"], "Enheter": d["antal_matenheter"],
    }).to_csv(out / f"inmatning_{PERIOD}.csv", index=False)
    m.harvest.to_csv(out / f"skord_{PERIOD}.csv", index=False)
    pd.DataFrame({"AO": m.orders["avtalsobjekt"], "Status": _flag(m, "Klar", "Ej klar")}).to_csv(
        out / "arbetsordrar.csv", index=False)
    return (
        "Kommaseparerade filer, punkt som decimaltecken, datum som ÅÅÅÅ-MM-DD.\n\n"
        f"- `skord_{PERIOD}.csv`: skördarens produktion, i treedists kolumnnamn.\n"
        f"- `inmatning_{PERIOD}.csv`: alla lass som mättes in under månaden. AO är arbetsordern. SkordatSortiment "
        "är sortimentet skördaren angav, InmattSortiment det industrin mätte in och fakturerar; de skiljer när "
        "industrin klassat om. Mottagare är industrin där lasset mättes in och KapadFor den virket kapades för. Kord "
        "är dagen lasset kördes, Matt dagen det mättes in och Bokford dagen det bokfördes, ibland i månaden efter. "
        "Netto är fakturerad volym, Brutto volym före avdrag, båda i m3fub.\n"
        "- `arbetsordrar.csv`: arbetsordrarna vid månadens slut. Status är Klar när inga fler lass ska köras från "
        "arbetsordern, annars Ej klar.\n"
    )


def _credit(m: Month, out: Path) -> str:
    """Remeasured loads: credited in full and booked again. Volumes are unsigned; a column says debit or credit."""
    d = m.deliveries.copy()
    rng = np.random.default_rng(len(d))
    redo = d[rng.random(len(d)) < 0.2]
    again = redo.assign(volym_m3fub=(redo["volym_m3fub"] * 0.97).round(3), brutto_m3fub=(redo["brutto_m3fub"] * 0.97).round(3))
    first = redo.assign(volym_m3fub=(redo["volym_m3fub"] * 1.05).round(3), brutto_m3fub=(redo["brutto_m3fub"] * 1.05).round(3))
    credit = first.assign(volym_m3fub=-first["volym_m3fub"], brutto_m3fub=-first["brutto_m3fub"])
    rows = pd.concat([d.drop(redo.index), first, credit, again]).sort_values(["leveransnummer", "volym_m3fub"], ascending=[True, False])
    m.deliveries = rows.reset_index(drop=True)
    kind = np.where(rows["volym_m3fub"] < 0, "K", "D")
    pd.DataFrame({
        "LassId": rows["leveransnummer"], "Arbetsorder": rows["avtalsobjekt"], "Sortiment": rows["handelssortiment"],
        "SkordatSortiment": rows["producerat_handelssortiment"], "Mottagare": rows["mottagningsplats"],
        "KapadFor": rows["producerat_for_mottagningsplats"], "Datum": rows["leveransdatum"].str.replace("-", ""),
        "MatDatum": rows["matdatum"].str.replace("-", ""),
        "DK": kind, "NettoFub": _decimal(rows["volym_m3fub"].abs()), "BruttoFub": _decimal(rows["brutto_m3fub"].abs()),
        "Metod": rows["matmetod"], "Enheter": rows["antal_matenheter"],
    }).to_csv(out / f"inmatning_{PERIOD}.csv", sep=";", index=False)
    m.harvest.to_csv(out / f"skord_{PERIOD}.csv", index=False)
    m.orders.to_csv(out / f"avtalsobjekt_{PERIOD}.csv", index=False)
    return (
        f"- `skord_{PERIOD}.csv` och `avtalsobjekt_{PERIOD}.csv`: kommaseparerade, i treedists format.\n"
        f"- `inmatning_{PERIOD}.csv`: inmätning per lass ur ekonomisystemet, semikolon och decimalkomma. Sortiment "
        "är det inmätta sortimentet, som faktureras, och SkordatSortiment det skördaren kapade. Mottagare är där "
        "lasset mättes in och KapadFor mottagaren virket kapades för. Datum är dagen lasset kördes och MatDatum "
        "dagen det mättes in, båda som ÅÅÅÅMMDD. NettoFub är fakturerad volym och BruttoFub volym före avdrag, i "
        "m3fub och alltid utan tecken: DK säger om raden är debet (D) eller kredit (K). Ett lass som mätts om "
        "krediteras i sin helhet och debiteras igen under samma LassId.\n"
    )


def _per_mill(m: Month, out: Path) -> str:
    """One file per mill: the actual mill is only in the file name, and each row also names the one it was cut for."""
    d = m.deliveries
    for mill, rows in d.groupby("mottagningsplats"):
        pd.DataFrame({
            "lass": rows["leveransnummer"], "ao": rows["avtalsobjekt"], "sortiment": rows["handelssortiment"],
            "skordat_sortiment": rows["producerat_handelssortiment"], "kapad_for": rows["producerat_for_mottagningsplats"],
            "kordag": rows["leveransdatum"], "matdag": rows["matdatum"], "netto_m3fub": rows["volym_m3fub"],
            "brutto_m3fub": rows["brutto_m3fub"], "matmetod": rows["matmetod"], "matenheter": rows["antal_matenheter"],
        }).to_csv(out / f"inmatning_{mill}_{PERIOD}.csv", index=False)
    m.harvest.to_csv(out / f"skord_{PERIOD}.csv", index=False)
    m.orders.to_csv(out / f"avtalsobjekt_{PERIOD}.csv", index=False)
    return (
        "Kommaseparerade filer med punkt som decimaltecken.\n\n"
        f"- `skord_{PERIOD}.csv` och `avtalsobjekt_{PERIOD}.csv`: i treedists format.\n"
        f"- `inmatning_<MOTTAGARE>_{PERIOD}.csv`: en fil per mottagande sågverk, med sågverket i filnamnet. ao är "
        "arbetsordern. sortiment är det inmätta sortimentet, som faktureras, och skordat_sortiment det skördaren "
        "kapade. kapad_for är det sågverk skördaren kapade virket för. kordag är dagen lasset kördes, matdag dagen "
        "det mättes in, netto_m3fub fakturerad volym och brutto_m3fub volym före avdrag.\n"
    )


def _spreadsheet(m: Month, out: Path) -> str:
    """Saved from a spreadsheet: serial dates, spaces as thousands separators, a totals row."""
    h, d = m.harvest, m.deliveries
    serial = lambda s: (pd.to_datetime(s) - pd.Timestamp("1899-12-30")).dt.days  # noqa: E731
    thousands = lambda v: v.map(lambda x: f"{x:,.3f}".replace(",", " ").replace(".", ",").rstrip("0").rstrip(","))  # noqa: E731
    harvest = pd.DataFrame({
        "Arbetsorder": h["avtalsobjekt"], "Sortiment": h["producerat_handelssortiment"],
        "KapadFor": h["producerat_for_mottagningsplats"], "Diameterklass": h["diameterklass"],
        "Langdklass": h["langdklass"], "Fallningsdag": serial(h["avverkningsdatum"]), "Volym": thousands(h["volym_m3fub"]),
        "Stockar": h["antal_stockar"],
    })
    total = {"Arbetsorder": "Totalsumma", "Volym": thousands(pd.Series([h["volym_m3fub"].sum()])).iloc[0],
             "Stockar": int(h["antal_stockar"].sum())}
    pd.concat([harvest.astype(str), pd.DataFrame([total])]).to_csv(out / f"skord_{PERIOD}.csv", sep=";", index=False)
    loads = pd.DataFrame({
        "Lass": d["leveransnummer"], "Arbetsorder": d["avtalsobjekt"], "Sortiment": d["handelssortiment"],
        "SkordatSortiment": d["producerat_handelssortiment"], "Mottagare": d["mottagningsplats"],
        "KapadFor": d["producerat_for_mottagningsplats"], "Kordag": serial(d["leveransdatum"]),
        "Matdag": serial(d["matdatum"]), "Netto": thousands(d["volym_m3fub"]),
        "Brutto": thousands(d["brutto_m3fub"]), "Metod": d["matmetod"], "Enheter": d["antal_matenheter"],
    })
    total = {"Lass": "Totalsumma", "Netto": thousands(pd.Series([d["volym_m3fub"].sum()])).iloc[0],
             "Brutto": thousands(pd.Series([d["brutto_m3fub"].sum()])).iloc[0]}
    pd.concat([loads.astype(str), pd.DataFrame([total])]).to_csv(out / f"lass_{PERIOD}.csv", sep=";", index=False)
    pd.DataFrame({"Arbetsorder": m.orders["avtalsobjekt"], "TransportAvslutad": _flag(m, "SANT", "FALSKT")}).to_csv(
        out / f"arbetsordrar_{PERIOD}.csv", sep=";", index=False)
    return (
        "Sparat som CSV ur ett kalkylblad: semikolon, decimalkomma och mellanslag mellan tusental. Datum är "
        "kalkylbladets serienummer, dagar sedan 1899-12-30. Sista raden i skörd- och lassfilen är en totalsumma.\n\n"
        f"- `skord_{PERIOD}.csv`: skördarens produktion per arbetsorder. Sortiment är det skördaren kapade och "
        "KapadFor mottagaren det kapades för. Diameterklass och Langdklass är klassernas nedre gränser i "
        "cm, Volym m3fub under bark, Stockar antal stockar.\n"
        f"- `lass_{PERIOD}.csv`: inmätning per lass. Sortiment är det inmätta sortimentet, som faktureras, och "
        "SkordatSortiment det skördaren kapade. Mottagare är där lasset mättes in och KapadFor mottagaren virket "
        "kapades för. Kordag är dagen lasset kördes, Matdag dagen det mättes in, Netto fakturerad volym och "
        "Brutto volym före avdrag, i m3fub.\n"
        f"- `arbetsordrar_{PERIOD}.csv`: arbetsordrarna vid månadens slut. TransportAvslutad är SANT när inga fler "
        "lass ska köras från arbetsordern, annars FALSKT.\n"
    )


VARIANTS = {"a_semikolon": (_semicolon, 23), "b_engelska": (_english, 26), "c_lass": (_join, 29), "d_koder": (_codes, 33)}
CONTROL = {"e_semikolon": (_semicolon, 34), "f_engelska": (_english, 35), "g_lass": (_join, 24), "h_koder": (_codes, 36)}
PLATFORMS = {"i_lager": (_warehouse, 42), "j_api": (_api, 49), "k_rapport": (_report, 52), "l_stordator": (_fixed, 40)}
PLATFORM_CONTROL = {"n_lager": (_warehouse, 47), "o_api": (_api, 58), "p_rapport": (_report, 45), "q_stordator": (_fixed, 50)}
# The second month of a warehouse that holds every month: late reports were felled the month before.
HISTORY = {"m_lagerhistorik": (_warehouse_history, 70)}
HISTORY_CONTROL = {"r_lagerhistorik": (_warehouse_history, 74)}
HARD = {"s_omklassat": (_reclassified, 78), "t_kredit": (_credit, 80), "u_per_bruk": (_per_mill, 105), "v_kalkylblad": (_spreadsheet, 79)}
HARD_CONTROL = {"w_omklassat": (_reclassified, 82), "x_kredit": (_credit, 104), "y_per_bruk": (_per_mill, 97), "z_kalkylblad": (_spreadsheet, 81)}


def make(bench: Path, variants: dict) -> None:
    for name, (writer, seed) in variants.items():
        months = _months(seed, getattr(writer, "months", 1))
        month = months[-1]
        task, answer = bench / "uppgifter" / name, bench / "facit" / name
        for folder in (task, answer):
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True)
        description = writer(months if len(months) > 1 else month, task)
        periods = [m.period for m in months]
        which = f"perioden {periods[0]}" if len(months) == 1 else f"perioderna {' och '.join(periods)}, i den ordningen"
        (task / "UPPGIFT.md").write_text(
            f"# Källa {name}\n\nSkriv en källbeskrivning för treedist i den här katalogen, `kalla.toml` eller vid "
            f"behov `kalla.py`, för {which}. Läs AGENTS.md först.\n\n"
            f"## Dataägarens beskrivning\n\n{description}",
            encoding="utf-8",
        )
        (answer / "period.txt").write_text("\n".join(periods))
        for m in months:
            folder = answer if len(months) == 1 else answer / m.period
            folder.mkdir(exist_ok=True)
            m.harvest.to_csv(folder / "produktion.csv", index=False)
            m.deliveries.to_csv(folder / "matning.csv", index=False)
            m.orders.to_csv(folder / "avtalsobjekt.csv", index=False)
        print(f"Skrev {task}")


def _entry(task: Path) -> Path | None:
    """The source description a task ends in: a .py adapter may read a .toml beside it."""
    return next((task / n for n in ("kalla.py", "kalla.toml") if (task / n).exists()), None)


def _close(inputs, period: str, ledger: Ledger):
    return run_month(ledger, inputs.harvest, inputs.deliveries, period, inputs.transport_done, CFG)


def grade_task(task: Path, answer: Path) -> str | None:
    """None if the task's source description gives exactly the answer in every period, else what differs.

    Periods run in order, each answer and each source with its own ledger carried from the month before, as
    `treedist run` with the same --state would.
    """
    periods = (answer / "period.txt").read_text().split() if (answer / "period.txt").exists() else [PERIOD]
    ledgers = (Ledger.empty(), Ledger.empty())
    for period in periods:
        failure, ledgers = _grade_period(task, answer if len(periods) == 1 else answer / period, period, ledgers)
        if failure:
            return f"{period} {failure}" if len(periods) > 1 else failure
    return None


def _grade_period(task: Path, answer: Path, period: str, ledgers: tuple[Ledger, Ledger]):
    files = {key: answer / f"{key}.csv" for key in ("produktion", "matning", "avtalsobjekt")}
    source = _entry(task)
    if source is None:
        return "ingen källbeskrivning", ledgers
    try:
        truth, got = load(period, files=files), load(period, source=source)
        for name in ("harvest", "deliveries"):
            expected = getattr(truth, name).sort_values(list(getattr(truth, name).columns)).reset_index(drop=True)
            actual = getattr(got, name)
            actual = actual[expected.columns].sort_values(list(expected.columns)).reset_index(drop=True)
            pd.testing.assert_frame_equal(actual, expected, check_dtype=False, rtol=1e-6)
        assert got.transport_done == truth.transport_done, "avtalsobjekt med avslutad transport skiljer"
        expected, actual = _close(truth, period, ledgers[0]), _close(got, period, ledgers[1])
        pd.testing.assert_frame_equal(actual.invoice, expected.invoice, check_dtype=False)
    except Exception as error:  # noqa: BLE001  any failure is a failed task
        first = str(error).strip().splitlines()
        return f"({source.name}) {' '.join(first[:3])[:300]}", ledgers
    return None, (expected.step.ledger, actual.step.ledger)


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
        command.add_argument("--svara", action="store_true", help="Fällor ur AGENTS.md: omklassning, kredit, per bruk, kalkylblad")
    args = parser.parse_args()
    if args.command == "felkatalog":
        mistakes(CONTROL_MISTAKES if args.kontroll else MISTAKES)
        false_alarms(args.dir)
    elif args.command == "skapa":
        if args.svara:
            variants = HARD_CONTROL if args.kontroll else HARD
        elif args.historik:
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
