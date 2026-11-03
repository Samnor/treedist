"""Write the demo's first month as a source system with its own format, for examples/kalla.

The export differs from the contract the way real ones do: other column names,
semicolons and decimal commas, diameters in millimetres, compact dates, an
accounting date beside the transport date, and voided rows to filter out.
examples/kalla/kalla.toml maps it back, and a test checks that the result is
the same invoice as from the canonical files.

    uv run python scripts/make_source_example.py
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo"
TARGET = ROOT / "examples" / "kalla" / "export"
PERIOD = "2026-01"


def _comma(values: pd.Series) -> pd.Series:
    return values.map(lambda v: f"{v:g}".replace(".", ","))


def _compact(dates: pd.Series) -> pd.Series:
    return dates.str.replace("-", "", regex=False)


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    harvest = pd.read_csv(DEMO / f"skordning_{PERIOD}.csv")
    pd.DataFrame(
        {
            "AO_Nr": harvest["arbetsorder"],
            "Sortiment": harvest["handelssortiment"],
            "DiamKlassMM": harvest["diametergrupp"] * 10,
            "LangdKlassCM": harvest["langdgrupp"],
            "VolymFub": _comma(harvest["volym_m3fub"]),
            "AntalStockar": harvest["antal_stockar"],
            "FallDatum": _compact(harvest["avverkningsdatum"]),
        }
    ).to_csv(TARGET / f"produktion_{PERIOD}.csv", sep=";", index=False)

    deliveries = pd.read_csv(DEMO / f"leverans_{PERIOD}.csv")
    export = pd.DataFrame(
        {
            "Lassnr": deliveries["leverans_id"],
            "AO_Nr": deliveries["arbetsorder"],
            "InmattSortiment": deliveries["handelssortiment"],
            "Mottagare": deliveries["mottagningsplats"],
            "TransportDatum": _compact(deliveries["leveransdatum"]),
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

    orders = pd.read_csv(DEMO / "arbetsordrar.csv")
    orders.rename(columns={"arbetsorder": "AO", "destination": "PlaneradMottagare", "grupp": "Jamforgrupp"}).to_csv(
        TARGET / "arbetsordrar.csv", sep=";", index=False
    )
    print(f"Skrev {TARGET}")


if __name__ == "__main__":
    main()
