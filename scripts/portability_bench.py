"""How well does treedist move to new data? Two measures for the portability climb.

    uv run python scripts/portability_bench.py felkatalog
        Plants common mapping mistakes in examples/kalla and counts how many
        `treedist check` notices. Deterministic.

    uv run python scripts/portability_bench.py skapa --dir BENCH [--kontroll]
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
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

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
]


# Written after the climb's decisions and used once, to see whether the checks generalise.
CONTROL_MISTAKES = [
    ("mottagare som sortiment", 'handelssortiment = "InmattSortiment"', 'handelssortiment = "Mottagare"'),
    ("arbetsorder som mottagningsplats", 'mottagningsplats = "Mottagare"', 'mottagningsplats = "AO_Nr"'),
    ("antal stockar som skördad volym", 'volym_m3fub = "VolymFub"', 'volym_m3fub = "AntalStockar"'),
    ("dag och månad bytta i leveransdatum", 'separator = ";"\ndatumformat = "%Y%m%d"\n\n[leverans.kolumner]',
     'separator = ";"\ndatumformat = "%Y%d%m"\n\n[leverans.kolumner]'),
    ("grupp som planerad destination", 'destination = "PlaneradMottagare"', 'destination = "Jamforgrupp"'),
    ("arbetsorder som lassnummer", 'leverans_id = "Lassnr"', 'leverans_id = "AO_Nr"'),
]


def _mistake_source(tmp: Path, old: str, new: str) -> Path:
    text = (EXAMPLE / "kalla.toml").read_text(encoding="utf-8")
    text = text.replace('"export/', f'"{EXAMPLE}/export/').replace('"../demo/', f'"{EXAMPLE.parent}/demo/')
    if old == "diameter_grupp_placeholder":
        old, new = "diametergrupp = 0.1   # mm -> cm", ""
    if new.endswith("# MITT"):
        # Class midpoints: export the class bottom plus half a 2 cm class.
        export = tmp / "export"
        shutil.copytree(EXAMPLE / "export", export, dirs_exist_ok=True)
        harvest = pd.read_csv(export / f"produktion_{PERIOD}.csv", sep=";", dtype=str)
        harvest["DiamKlassMM"] = (harvest["DiamKlassMM"].astype(int) + 10).astype(str)
        harvest.to_csv(export / f"produktion_{PERIOD}.csv", sep=";", index=False)
        text = text.replace(f'"{EXAMPLE}/export/produktion', f'"{export}/produktion')
        new = new.replace("\n# MITT", "")
    if old not in text:
        raise SystemExit(f"Felkatalogen passar inte längre kalla.toml: {old!r}")
    path = tmp / "kalla.toml"
    path.write_text(text.replace(old, new), encoding="utf-8")
    return path


def mistakes(catalog=MISTAKES) -> int:
    import tempfile

    baseline = {(f.level, f.message) for f in check(PERIOD, CFG, source=EXAMPLE / "kalla.toml") if f.level != OK}
    found = 0
    for name, old, new in catalog:
        with tempfile.TemporaryDirectory() as tmp:
            source = _mistake_source(Path(tmp), old, new)
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


def _month(seed: int) -> Month:
    month = simulate(SimParams(months=1, seed=seed, work_orders_per_month=10))[0]
    orders = pd.DataFrame({"destination": month.work_orders.destinations, "grupp": month.work_orders.groups})
    return Month(
        month.harvest,
        month.deliveries,
        orders.rename_axis("arbetsorder").reset_index(),
        pd.DataFrame({"arbetsorder": sorted(month.closed_aos)}),
    )


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


VARIANTS = {"a_semikolon": (_semicolon, 23), "b_engelska": (_english, 26), "c_lass": (_join, 29), "d_koder": (_codes, 33)}
CONTROL = {"e_semikolon": (_semicolon, 34), "f_engelska": (_english, 35), "g_lass": (_join, 24), "h_koder": (_codes, 36)}


def make(bench: Path, control: bool) -> None:
    for name, (writer, seed) in (CONTROL if control else VARIANTS).items():
        month = _month(seed)
        task, answer = bench / "uppgifter" / name, bench / "facit" / name
        for folder in (task, answer):
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True)
        description = writer(month, task)
        example_price_list().to_csv(task / "prislista.csv", index=False)
        month.closed.to_csv(task / f"avslutade_{PERIOD}.csv", index=False)
        (task / "UPPGIFT.md").write_text(
            f"# Källa {name}\n\nSkriv en källbeskrivning för treedist i den här katalogen, `kalla.toml` eller vid "
            f"behov `kalla.py`, för perioden {PERIOD}. Läs AGENTS.md i treedist-repot först.\n\n"
            f"## Dataägarens beskrivning\n\n{description}"
            "- `prislista.csv`: prislistan, redan i treedists format.\n"
            f"- `avslutade_{PERIOD}.csv`: arbetsordrar som avslutades under månaden.\n",
            encoding="utf-8",
        )
        month.harvest.to_csv(answer / "skordning.csv", index=False)
        month.deliveries.to_csv(answer / "leverans.csv", index=False)
        month.orders.to_csv(answer / "arbetsordrar.csv", index=False)
        month.closed.to_csv(answer / "avslutade_ao.csv", index=False)
        example_price_list().to_csv(answer / "prislista.csv", index=False)
        print(f"Skrev {task}")


def _entry(task: Path) -> Path | None:
    """The source description a task ends in: a .py adapter may read a .toml beside it."""
    return next((task / n for n in ("kalla.py", "kalla.toml") if (task / n).exists()), None)


def _invoice(inputs) -> pd.DataFrame:
    return run_month(
        Ledger.empty(), inputs.harvest, inputs.deliveries, inputs.prices, PERIOD, inputs.closed_aos, CFG,
        inputs.work_orders,
    ).invoice


def grade(bench: Path) -> int:
    passed = 0
    tasks = sorted(p for p in (bench / "uppgifter").iterdir() if p.is_dir())
    for task in tasks:
        answer = bench / "facit" / task.name
        files = {key: answer / f"{key}.csv" for key in ("skordning", "leverans", "prislista", "arbetsordrar", "avslutade_ao")}
        source = _entry(task)
        if source is None:
            print(f"UNDERKÄND {task.name}: ingen källbeskrivning")
            continue
        try:
            truth, got = load(PERIOD, CFG, files=files), load(PERIOD, CFG, source=source)
            for name in ("harvest", "deliveries"):
                expected = getattr(truth, name).sort_values(list(getattr(truth, name).columns)).reset_index(drop=True)
                actual = getattr(got, name)
                actual = actual[expected.columns].sort_values(list(expected.columns)).reset_index(drop=True)
                pd.testing.assert_frame_equal(actual, expected, check_dtype=False, rtol=1e-6)
            assert got.work_orders == truth.work_orders, "arbetsordrarna skiljer"
            assert got.closed_aos == truth.closed_aos, "avslutade arbetsordrar skiljer"
            pd.testing.assert_frame_equal(_invoice(got), _invoice(truth), check_dtype=False)
        except Exception as error:  # noqa: BLE001  any failure is a failed task
            first = str(error).strip().splitlines()
            print(f"UNDERKÄND {task.name} ({source.name}): {' '.join(first[:3])[:300]}")
            continue
        passed += 1
        print(f"GODKÄND  {task.name} ({source.name})")
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
    args = parser.parse_args()
    if args.command == "felkatalog":
        mistakes(CONTROL_MISTAKES if args.kontroll else MISTAKES)
        false_alarms(args.dir)
    elif args.command == "skapa":
        make(args.dir, args.kontroll)
    else:
        grade(args.dir)


if __name__ == "__main__":
    sys.exit(main())
