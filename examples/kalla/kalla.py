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
    produktion = pd.DataFrame({
        "avtalsobjekt": harvest["AO_Nr"],  # källans arbetsorder är VIOL 3:s avtalsobjekt
        "producerat_handelssortiment": harvest["Sortiment"],
        "producerat_for_mottagningsplats": harvest["KapadFor"],  # mottagningsplatsen virket kapades för
        "diameterklass": harvest["DiamKlassMM"].astype(int) // 10,  # mm -> cm, klassens nedre gräns
        "langdklass": harvest["LangdKlassCM"],
        "volym_m3fub": harvest["VolymFub"],  # decimalkomma läses av treedist
        "antal_stockar": harvest["AntalStockar"],
        "avverkningsdatum": _date(harvest["FallDatum"]),
    })

    loads = _csv(f"export/inmatning_{period}.csv")
    loads = loads[loads["Status"] == "Godkänd"]  # makulerade lass räknas inte
    matning = pd.DataFrame({
        "leveransnummer": loads["Lassnr"],
        "avtalsobjekt": loads["AO_Nr"],
        "handelssortiment": loads["InmattSortiment"],  # det inmätta sortimentet, som faktureras
        "producerat_handelssortiment": loads["KapatSortiment"],  # det skördaren kapade
        "mottagningsplats": loads["Mottagare"],  # där leveransen mättes in
        "producerat_for_mottagningsplats": loads["KapadFor"],  # den virket kapades för: lagret lasset hämtades ur
        "leveransdatum": _date(loads["TransportDatum"]),  # dagen lasset kördes, inte redovisningsdagen
        "matdatum": _date(loads["MatDatum"]),  # dagen leveransen mättes in
        "volym_m3fub": loads["NettoFub"],
        "brutto_m3fub": loads["BruttoFub"],
        "matmetod": loads["Matmetod"],
        "antal_matenheter": loads["AntalEnheter"],
    })

    orders = _csv(f"export/arbetsordrar_{period}.csv")
    avtalsobjekt = pd.DataFrame({
        "avtalsobjekt": orders["AO"],
        "transport_avslutad": orders["TransportKlar"].map({"J": "true", "N": "false"}),  # källans J/N
    })

    return {"produktion": produktion, "matning": matning, "avtalsobjekt": avtalsobjekt}
