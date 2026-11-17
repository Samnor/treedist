"""Where the mill's wood comes from: the appendix's diagram and table per anskaffningsform.

A source that has anskaffningsform gets a part of the appendix that shows all wood measured at the mill, per
anskaffningsform, and what became of it: distributed from the stock, distributed as the whole harvest, or outside the
matrix. Without the column the appendix is what it was.
"""

import re

import pandas as pd
import pytest
from conftest import viol3_deliveries, viol3_harvest
from openpyxl import load_workbook
from test_sent import demo, run
from test_utan_avverkning import MILL, bought

from treedist.adapters import validate

PAGE = ("out", "2026-01", "bilagor", "sag_klen.html")


def with_origin(period):
    """The month with bought wood, and an anskaffningsform on every avtalsobjekt."""
    measured = bought(period)
    own = measured["utan_avverkning"] == "false"
    first = sorted(measured.loc[own, "avtalsobjekt"].unique())[0]
    kind = measured["avtalsobjekt"].map(lambda ao: "Virkesköp" if ao == first else "Egen skog")
    return measured.assign(anskaffningsform=kind.where(own, "Centrala köp"))


def numbers(text):
    return [float(n.replace("\xa0", "").replace(" ", "").replace(",", ".")) for n in text]


def test_the_appendix_shows_where_the_wood_comes_from_and_it_adds_up_to_what_was_measured(tmp_path):
    measured = with_origin("2026-01")
    assert run(tmp_path, "2026-01", None, measured) == 0
    page = tmp_path.joinpath(*PAGE).read_text(encoding="utf-8")
    part = page.split("<h2>Varifrån virket kommer</h2>", 1)[1].split("</section>", 1)[0]

    at_mill = measured[measured["mottagningsplats"] == MILL]
    volume = pd.to_numeric(at_mill["volym_m3fub"])
    per_kind = volume.groupby(at_mill["anskaffningsform"]).sum()
    rows = dict(re.findall(r"<tr><th>([^<]+)</th>(.*?)</tr>", part.split("<tbody>", 1)[1]))
    assert set(rows) == set(per_kind.index)
    for kind, total in per_kind.items():
        cells = re.findall(r"<td>([^<]*)</td>", rows[kind])
        assert numbers([cells[-2]])[0] == pytest.approx(total, abs=0.06)
    # The bought wood stands outside the matrix, and nowhere else.
    assert "Utanför matrisen" in part and "Resten, 40,0 m3fub, har ingen avverkning i underlaget" in part
    bought_cells = re.findall(r"<td>([^<]*)</td>", rows["Centrala köp"])
    assert bought_cells[:-2] == ["–", "40,0"] or bought_cells[:-2] == ["–", "–", "40,0"]
    # The diagram has a node for every anskaffningsform and for the wood outside the matrix.
    for name in (*per_kind.index, "Utanför matrisen"):
        assert f'class="name">{name}<' in part
    # The part comes before how the matrix was found, and the guide explains it.
    assert page.index("Varifrån virket kommer</h2>") < page.index("Hur matrisen togs fram</h2>")
    assert "<dt>Varifrån virket kommer</dt>" in page


def test_the_workbook_has_the_same_table(tmp_path):
    measured = with_origin("2026-01")
    assert run(tmp_path, "2026-01", None, measured) == 0
    book = load_workbook(tmp_path / "out" / "2026-01" / "bilagor" / "sag_klen.xlsx")
    sheet = book["Anskaffningsform"]
    assert [c.value for c in sheet[4]][:1] == ["Anskaffningsform"]
    kinds = {row[0].value: row for row in sheet.iter_rows(min_row=5) if row[0].value}
    assert {"Egen skog", "Centrala köp", "Summa"} <= set(kinds)
    outside = [c.value for c in sheet[4]].index("Utanför matrisen, m3fub")
    assert kinds["Centrala köp"][outside].value == pytest.approx(40.0)
    assert str(kinds["Summa"][outside].value).startswith("=SUM(")
    assert any("Anskaffningsform:" in str(row[0].value) for row in book["Läs först"].iter_rows())
    assert book.sheetnames.index("Anskaffningsform") < book.sheetnames.index("Källor")


def test_without_anskaffningsform_the_appendix_has_no_such_part(tmp_path):
    assert run(tmp_path, "2026-01", None, bought("2026-01")) == 0
    page = tmp_path.joinpath(*PAGE).read_text(encoding="utf-8")
    assert "Varifrån virket kommer" not in page and "varifrån virket kommer" not in page
    assert "Anskaffningsform" not in load_workbook(tmp_path / "out" / "2026-01" / "bilagor" / "sag_klen.xlsx").sheetnames


def test_all_wood_from_harvesting_says_so(tmp_path):
    measured = with_origin("2026-01")
    assert run(tmp_path, "2026-01", None, measured[measured["utan_avverkning"] == "false"]) == 0
    page = tmp_path.joinpath(*PAGE).read_text(encoding="utf-8")
    part = page.split("<h2>Varifrån virket kommer</h2>", 1)[1].split("</section>", 1)[0]
    assert "All volym kommer från avverkning med skördardata och ingår i matrisen." in part
    assert "Utanför matrisen" not in part


def test_an_avtalsobjekt_has_one_anskaffningsform():
    harvest = pd.DataFrame({"avtalsobjekt": ["A"], "producerat_handelssortiment": ["TALL"], "diameterklass": ["20"],
                            "langdklass": ["400"], "volym_m3fub": ["100"]})
    loads = pd.DataFrame({"avtalsobjekt": ["A", "A"], "handelssortiment": "TALL", "volym_m3fub": ["30", "10"],
                          "anskaffningsform": ["Egen skog", "Virkesköp"]})
    with pytest.raises(ValueError, match="1 avtalsobjekt har flera olika anskaffningsform: A"):
        validate({"produktion": viol3_harvest(harvest, "2026-01"), "matning": viol3_deliveries(loads, "2026-01")}, "2026-01")


def test_the_demo_without_the_column_is_unchanged(tmp_path):
    assert run(tmp_path / "a", "2026-01") == 0
    assert run(tmp_path / "b", "2026-01", None, demo("2026-01")["matning"].assign(utan_avverkning="false")) == 0
    pages = [(tmp_path / which).joinpath(*PAGE).read_text(encoding="utf-8") for which in "ab"]
    assert pages[0] == pages[1]
