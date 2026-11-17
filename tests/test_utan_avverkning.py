"""Wood that comes from no harvest in the source, such as bought wood, import and wood from a terminal.

The method has nothing to distribute it by. The source marks it `utan_avverkning`, by the avtalsobjekt's kind; it is
then left out of every matrix, and the appendix says how much of the mill's measured wood the matrix stands for.
"""

import pandas as pd
import pytest
from conftest import viol3_deliveries, viol3_harvest
from openpyxl import load_workbook
from test_sent import demo, run

from treedist.adapters import validate

MILL = "SAG_KLEN"


def bought(period, volume="40.000"):
    """One load of bought wood to MILL, on an avtalsobjekt of its own."""
    row = demo(period)["matning"].head(1).assign(leveransnummer="KOP1", avtalsobjekt="KOP00001", mottagningsplats=MILL,
                                                 producerat_for_mottagningsplats=MILL, volym_m3fub=volume,
                                                 brutto_m3fub=volume, utan_avverkning="true")
    return pd.concat([demo(period)["matning"].assign(utan_avverkning="false"), row], ignore_index=True)


def test_wood_from_no_harvest_is_left_out_of_the_matrix_and_the_appendix_says_how_much(tmp_path, capsys):
    assert run(tmp_path / "med", "2026-01", None, bought("2026-01")) == 0
    said = capsys.readouterr().out
    assert "40.0 m3fub" in said and "märkt utan_avverkning" in said and "fördelas inte" in said
    assert run(tmp_path / "utan", "2026-01") == 0

    # Nothing of what is distributed changes.
    lines = [pd.read_csv(tmp_path / which / "out" / "2026-01" / "faktura_rader.csv", dtype=str) for which in ("med", "utan")]
    assert lines[0].equals(lines[1])

    measured = pd.to_numeric(demo("2026-01")["matning"].query("mottagningsplats == @MILL")["volym_m3fub"]).sum()
    page = (tmp_path / "med" / "out" / "2026-01" / "bilagor" / "sag_klen.html").read_text(encoding="utf-8")
    covered = f"{measured:,.1f}".replace(",", " ").replace(".", ",")
    whole = f"{measured + 40:,.1f}".replace(",", " ").replace(".", ",")
    assert f"Matrisen gäller virke från avverkning med skördardata: {covered} av de {whole} m3fub" in page
    sortiment = demo("2026-01")["matning"]["handelssortiment"].iloc[0]
    assert f"Resten, 40,0 m3fub ({sortiment}), är virke utan avverkning i underlaget" in page
    assert "Mätningen anger dess handelssortiment men inga diameter- och längdklasser, så det ingår inte i matrisen" in page
    assert "All volym som levererats till sågverket" not in page

    first = load_workbook(tmp_path / "med" / "out" / "2026-01" / "bilagor" / "sag_klen.xlsx")["Läs först"]
    assert any("Resten, 40,0 m3fub" in str(row[0].value) for row in first.iter_rows())

    # The other mill received none of it, and its appendix says what it always said.
    other = (tmp_path / "med" / "out" / "2026-01" / "bilagor" / "sag_mix.html").read_text(encoding="utf-8")
    assert "All volym som levererats till sågverket" in other and "utan avverkning" not in other


def test_without_the_mark_the_appendix_is_what_it_was(tmp_path):
    assert run(tmp_path / "a", "2026-01") == 0
    assert run(tmp_path / "b", "2026-01", None, demo("2026-01")["matning"].assign(utan_avverkning="false")) == 0
    pages = [(tmp_path / which / "out" / "2026-01" / "bilagor" / "sag_klen.html").read_text(encoding="utf-8") for which in "ab"]
    assert pages[0] == pages[1] and "All volym som levererats till sågverket" in pages[0]


def tables(deliveries, harvest, period="2026-01"):
    return {"produktion": viol3_harvest(harvest, period), "matning": viol3_deliveries(deliveries, period)}


HARVEST = pd.DataFrame({"avtalsobjekt": ["A"], "producerat_handelssortiment": ["TALL"], "diameterklass": ["20"],
                        "langdklass": ["400"], "volym_m3fub": ["100"]})


def loads(rows):
    """rows: (avtalsobjekt, volume, utan_avverkning)"""
    return pd.DataFrame(rows, columns=["avtalsobjekt", "volym_m3fub", "utan_avverkning"]).assign(handelssortiment="TALL")


def test_the_marked_rows_are_kept_apart_from_the_ones_the_method_reads():
    inputs = validate(tables(loads([("A", "30", "false"), ("KOP", "12", "true"), ("KOP", "8", "true")]), HARVEST), "2026-01")
    assert set(inputs.deliveries["avtalsobjekt"]) == {"A"}
    assert inputs.facts.outside["volym_m3fub"].sum() == pytest.approx(20.0)
    assert inputs.facts.outside_at("SAG").to_dict() == pytest.approx({"TALL": 20.0})
    assert inputs.facts.outside_at("ANNAN").sum() == 0.0


def test_a_contract_object_is_marked_wholly_or_not_at_all():
    with pytest.raises(ValueError, match="har också leveranser som inte är märkta utan_avverkning: KOP"):
        validate(tables(loads([("A", "30", "false"), ("KOP", "12", "true"), ("KOP", "8", "false")]), HARVEST), "2026-01")


def test_a_marked_contract_object_with_harvester_data_stops():
    # The mark is no way past the stop for a load without harvester data: it is the kind of the avtalsobjekt.
    with pytest.raises(ValueError, match="har skördardata i månadens produktion: A"):
        validate(tables(loads([("A", "30", "true")]), HARVEST), "2026-01")


def test_the_mark_is_true_or_false():
    with pytest.raises(ValueError, match="utan_avverkning ska vara true eller false, inte 'ja'"):
        validate(tables(loads([("A", "30", "false"), ("KOP", "12", "ja")]), HARVEST), "2026-01")


def test_a_contract_object_distributed_an_earlier_month_cannot_be_marked_later(tmp_path, capsys):
    assert run(tmp_path, "2026-01") == 0
    ao = demo("2026-01")["matning"]["avtalsobjekt"].iloc[0]
    february = demo("2026-02")
    harvest = february["produktion"].query("avtalsobjekt != @ao")
    rest = february["matning"].query("avtalsobjekt != @ao").assign(utan_avverkning="false")
    marked = february["matning"].head(1).assign(leveransnummer="NY1", avtalsobjekt=ao, utan_avverkning="true")
    assert run(tmp_path, "2026-02", harvest, pd.concat([rest, marked], ignore_index=True)) == 1
    stopped = capsys.readouterr().err
    assert f"märkta utan_avverkning men har leveranser som fördelats en tidigare månad: {ao}" in stopped
    assert not (tmp_path / "state" / "2026-02").exists()


def test_the_appendix_names_the_assortments_of_the_wood_outside_the_matrix(tmp_path):
    # The measurement gives the assortment of bought wood too, only not its classes.
    measured = bought("2026-01")
    other = measured.tail(1).assign(leveransnummer="KOP2", handelssortiment="TALL_KLEN", volym_m3fub="12.500",
                                    brutto_m3fub="12.500")
    assert run(tmp_path, "2026-01", None, pd.concat([measured, other], ignore_index=True)) == 0
    page = (tmp_path / "out" / "2026-01" / "bilagor" / "sag_klen.html").read_text(encoding="utf-8")
    sortiment = demo("2026-01")["matning"]["handelssortiment"].iloc[0]
    assert f"Resten, 52,5 m3fub ({sortiment} 40,0, TALL_KLEN 12,5), är virke utan avverkning" in page

