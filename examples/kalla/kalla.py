"""Samma källa som kalla.toml, skriven som .py-adapter. Kopiera den när en mappning inte räcker.

Kör: treedist check --period 2026-01 --kalla examples/kalla/kalla.py

treedist anropar read(period) och väntar sig en DataFrame per tabell, med kontraktets kolumnnamn
(`treedist kontrakt`). Värdena får vara text eller tal; treedist validerar och tolkar dem själv.
Datum ges som ÅÅÅÅ-MM-DD. Läs filer relativt adapterns egen katalog, inte arbetskatalogen.
"""

from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent


def _csv(name: str) -> pd.DataFrame:
    # dtype=str: inget tolkas om, så inledande nollor och decimalkomma finns kvar till treedist.
    return pd.read_csv(HERE / name, sep=";", dtype=str)


def _date(values: pd.Series) -> pd.Series:
    # Ange alltid formatet; errors="raise" stoppar i stället för att gissa.
    return pd.to_datetime(values, format="%Y%m%d", errors="raise").dt.strftime("%Y-%m-%d")


def read(period: str) -> dict[str, pd.DataFrame]:
    harvest = _csv(f"export/produktion_{period}.csv")
    skordning = pd.DataFrame({
        "arbetsorder": harvest["AO_Nr"],
        "handelssortiment": harvest["Sortiment"],
        "diametergrupp": harvest["DiamKlassMM"].astype(int) // 10,  # mm -> cm, klassens nedre gräns
        "langdgrupp": harvest["LangdKlassCM"],
        "volym_m3fub": harvest["VolymFub"],  # decimalkomma läses av treedist
        "antal_stockar": harvest["AntalStockar"],
        "avverkningsdatum": _date(harvest["FallDatum"]),
    })

    loads = _csv(f"export/inmatning_{period}.csv")
    loads = loads[loads["Status"] == "Godkänd"]  # makulerade lass räknas inte
    leverans = pd.DataFrame({
        "leverans_id": loads["Lassnr"],
        "arbetsorder": loads["AO_Nr"],
        "handelssortiment": loads["InmattSortiment"],  # det inmätta sortimentet, som faktureras
        "mottagningsplats": loads["Mottagare"],  # den faktiska mottagaren
        "leveransdatum": _date(loads["TransportDatum"]),  # dagen lasset kördes, inte redovisningsdagen
        "volym_m3fub": loads["NettoFub"],
        "brutto_m3fub": loads["BruttoFub"],
        "matmetod": loads["Matmetod"],
        "antal_matenheter": loads["AntalEnheter"],
    })

    orders = _csv("export/arbetsordrar.csv")
    arbetsordrar = pd.DataFrame({
        "arbetsorder": orders["AO"],
        "destination": orders["PlaneradMottagare"],  # den planerade mottagaren
        "grupp": orders["Jamforgrupp"],
    })

    return {
        "skordning": skordning,
        "leverans": leverans,
        "arbetsordrar": arbetsordrar,
        "prislista": pd.read_csv(HERE / "../demo/prislista.csv", dtype=str),
        "avslutade_ao": pd.read_csv(HERE / f"../demo/avslutade_ao_{period}.csv", dtype=str),
    }
