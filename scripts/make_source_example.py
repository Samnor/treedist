"""Write the demo's first month as source systems with their own formats: examples/kalla, kalla_lass and kalla_koder.

The export differs from the contract the way real ones do: other column names,
semicolons and decimal commas, diameters in millimetres, compact dates, an
accounting date beside the transport and measuring dates, voided rows to filter out, and the company's own terms:
its arbetsorder is VIOL 3's avtalsobjekt, and J/N says whether transport is finished.
examples/kalla/kalla.toml maps it back, and a test checks that the result is
the same invoice as from the canonical files.

Two more are prototypes for what a mapping most often lacked. In kalla_lass the delivery names only the truck, and
which avtalsobjekt it came from is in another file (`koppla`). In kalla_koder the assortments are codes and the
delivery system drops the avtalsobjekt's prefix (`koder`, `format`).

    uv run python scripts/make_source_example.py
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo"
TARGET = ROOT / "examples" / "kalla" / "export"
LOADS = ROOT / "examples" / "kalla_lass" / "export"
CODED = ROOT / "examples" / "kalla_koder" / "export"
CODES = {"TALL_SAG": "110", "GRAN_SAG": "210"}
PERIOD = "2026-01"


def _comma(values: pd.Series) -> pd.Series:
    return values.map(lambda v: f"{v:g}".replace(".", ","))


def _compact(dates: pd.Series) -> pd.Series:
    return dates.str.replace("-", "", regex=False)


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    harvest = pd.read_csv(DEMO / f"produktion_{PERIOD}.csv")
    pd.DataFrame(
        {
            "AO_Nr": harvest["avtalsobjekt"],
            "Sortiment": harvest["producerat_handelssortiment"],
            "KapadFor": harvest["producerat_for_mottagningsplats"],
            "DiamKlassMM": harvest["diameterklass"] * 10,
            "LangdKlassCM": harvest["langdklass"],
            "VolymFub": _comma(harvest["volym_m3fub"]),
            "AntalStockar": harvest["antal_stockar"],
            "FallDatum": _compact(harvest["avverkningsdatum"]),
        }
    ).to_csv(TARGET / f"produktion_{PERIOD}.csv", sep=";", index=False)

    deliveries = pd.read_csv(DEMO / f"matning_{PERIOD}.csv")
    export = pd.DataFrame(
        {
            "Lassnr": deliveries["leveransnummer"],
            "AO_Nr": deliveries["avtalsobjekt"],
            "InmattSortiment": deliveries["handelssortiment"],
            "KapatSortiment": deliveries["producerat_handelssortiment"],
            "Mottagare": deliveries["mottagningsplats"],
            "KapadFor": deliveries["producerat_for_mottagningsplats"],
            "TransportDatum": _compact(deliveries["leveransdatum"]),
            "MatDatum": _compact(deliveries["leveransdatum"]),
            "RedovisningDatum": f"{PERIOD.replace('-', '')}28",
            "NettoFub": _comma(deliveries["volym_m3fub"]),
            "BruttoFub": _comma(deliveries["brutto_m3fub"]),
            "Matmetod": deliveries["matmetod"],
            "AntalEnheter": deliveries["antal_matenheter"],
            "Status": "Godkänd",
        }
    )
    voided = export.head(3).assign(Lassnr=lambda df: df["Lassnr"] + "X", Status="Makulerad")
    pd.concat([export, voided]).to_csv(TARGET / f"inmatning_{PERIOD}.csv", sep=";", index=False)

    # The company's own table and terms: an arbetsorder per avtalsobjekt, and J or N for finished transport.
    orders = pd.read_csv(DEMO / f"avtalsobjekt_{PERIOD}.csv", dtype=str)
    pd.DataFrame({
        "AO": orders["avtalsobjekt"],
        "TransportKlar": orders["transport_avslutad"].map({"true": "J", "false": "N"}),
    }).to_csv(TARGET / f"arbetsordrar_{PERIOD}.csv", sep=";", index=False)
    print(f"Skrev {TARGET}")
    loads(deliveries)
    coded(harvest, deliveries)


def loads(deliveries: pd.DataFrame) -> None:
    """The delivery without its avtalsobjekt, and a file saying which avtalsobjekt each truck came from."""
    LOADS.mkdir(parents=True, exist_ok=True)
    deliveries.drop(columns=["avtalsobjekt"]).rename(columns={"leveransnummer": "Lass"}).to_csv(
        LOADS / f"inmatning_{PERIOD}.csv", index=False)
    deliveries[["leveransnummer", "avtalsobjekt"]].rename(columns={"leveransnummer": "Lass", "avtalsobjekt": "AO"}).to_csv(
        LOADS / f"lass_ao_{PERIOD}.csv", index=False)
    print(f"Skrev {LOADS}")


def coded(harvest: pd.DataFrame, deliveries: pd.DataFrame) -> None:
    """Assortments as codes in both exports, and avtalsobjekt without their prefix in the delivery."""
    CODED.mkdir(parents=True, exist_ok=True)
    harvest.assign(producerat_handelssortiment=harvest["producerat_handelssortiment"].map(CODES)).to_csv(
        CODED / f"produktion_{PERIOD}.csv", index=False)
    deliveries.assign(
        avtalsobjekt=deliveries["avtalsobjekt"].str.replace("AO", "", regex=False),
        handelssortiment=deliveries["handelssortiment"].map(CODES),
        producerat_handelssortiment=deliveries["producerat_handelssortiment"].map(CODES),
    ).to_csv(CODED / f"inmatning_{PERIOD}.csv", index=False)
    pd.DataFrame({"kod": list(CODES.values()), "namn": list(CODES)}).to_csv(CODED / "sortimentskoder.csv", index=False)
    print(f"Skrev {CODED}")


if __name__ == "__main__":
    main()
