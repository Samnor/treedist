"""The workbook carries each formula's value, so that a preview that does not compute shows the numbers."""

import math
import re

import pytest
from openpyxl import Workbook, load_workbook
from test_appendix import demo_run

from treedist.appendix import wrapped_lines
from treedist.excel_values import ExcelError, computed, save


def test_the_formulas_the_appendix_uses_are_computed_as_excel_does(tmp_path):
    book = Workbook()
    rows = book.active
    rows.title = "Rader"
    rows.append(["typ", "klass", "volym", "kod"])
    for line in [["LEVERANS", 340, 1.5, "S1"], ["LEVERANS", "370", 2.0, "s1"], ["KREDITERING", 400, 4.0, "S2"],
                 ["LEVERANS", 430, None, "S1"]]:
        rows.append(line)
    sheet = book.create_sheet("Matris")
    span = lambda c: f"'Rader'!${c}$2:${c}$5"  # noqa: E731
    sheet["A1"] = 0
    sheet["A2"] = None
    formulas = {
        "B1": f'=SUMIFS({span("C")},{span("A")},"LEVERANS")',
        "B2": f'=SUMIFS({span("C")},{span("B")},">=370",{span("B")},"<430")',  # text "370" is not a number to >=
        "B3": f'=SUMIFS({span("C")},{span("B")},370)',  # but equals 370
        "B4": f'=SUMIFS({span("C")},{span("D")},"S1")',  # without regard to case
        "B5": "=IF(A1=0,0,B1/A1)",  # the branch not taken is not computed
        "B6": "=B1/A1",
        "B7": '=IF(OR(A2="",A1=0),"",1)',
        "B8": "=SUM(B1:B4)-B1*2+-1",
        "B9": '=IF(B3=2,"ja","nej")&"!"',
    }
    for coordinate, text in formulas.items():
        sheet[coordinate] = text
    values = computed(book)["Matris"]
    assert values["B1"] == 3.5 and values["B2"] == 4.0 and values["B3"] == 2.0 and values["B4"] == 3.5
    assert values["B5"] == 0 and isinstance(values["B6"], ExcelError) and values["B7"] == ""
    assert values["B8"] == pytest.approx(3.5 + 4.0 + 2.0 + 3.5 - 7.0 - 1.0)
    assert values["B9"] == "ja!"

    path = tmp_path / "bok.xlsx"
    save(book, path)
    shown = load_workbook(path, data_only=True)["Matris"]
    assert shown["B1"].value == 3.5 and shown["B6"].value == "#DIV/0!" and shown["B9"].value == "ja!"
    assert load_workbook(path)["Matris"]["B1"].value.startswith("=SUMIFS(")


def test_every_formula_in_the_appendix_workbook_carries_the_value_excel_computes(tmp_path):
    assert_cached_values(demo_run(tmp_path, "varden"))


def assert_cached_values(out):
    """Every formula in the month's workbooks carries the value Excel computes for it."""
    formulas = pytest.importorskip("formulas")
    for path in (out / "bilagor").glob("*.xlsx"):
        expected = {}
        for key, cell in formulas.ExcelModel().loads(str(path)).finish().calculate().items():
            match = re.match(r"'?\[.*?\](.+?)'?!([A-Z]+\d+)$", key)
            if match and hasattr(cell, "value"):
                expected[(match.group(1).upper(), match.group(2))] = cell.value[0, 0]
        written, shown = load_workbook(path), load_workbook(path, data_only=True)
        counted = 0
        for sheet in written.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                        continue
                    counted += 1
                    mine, theirs = shown[sheet.title][cell.coordinate].value, expected[(sheet.title.upper(), cell.coordinate)]
                    if isinstance(theirs, (int, float)) and not isinstance(theirs, bool):
                        assert isinstance(mine, (int, float)), (sheet.title, cell.coordinate, mine)
                        assert math.isclose(mine, theirs, rel_tol=1e-9, abs_tol=1e-9), (sheet.title, cell.coordinate)
                    else:
                        assert (mine or "") == (theirs or ""), (sheet.title, cell.coordinate, mine, theirs)
        assert counted > 100


def test_the_workbook_explains_only_what_it_has_and_prints_on_the_page(tmp_path):
    out = demo_run(tmp_path, "las")
    path = next((out / "bilagor").glob("*.xlsx"))
    book = load_workbook(path)
    guide = book["Förklaring"]
    terms = [guide.cell(r, 1).value for r in range(5, guide.max_row + 1) if guide.cell(r, 1).value]
    # The first row explains the matrix sheet, under the name the sheet has.
    assert terms[0] == book.sheetnames[1] and "Osäkerheten" not in terms and "Kartan" not in terms
    assert not any("till höger" in t or "i mitten" in t or "diagrammet" in t.lower() for t in terms)
    assert book["Källor"]["A2"].value.startswith("Tabellen visar hur matrisens")
    for sheet in book.worksheets:
        assert sheet.page_setup.orientation == "landscape" and sheet.page_setup.fitToWidth == 1
        assert sheet.sheet_properties.pageSetUpPr.fitToPage
    orders = book["Avtalsobjekt"]
    for cell in orders[4]:
        if cell.value:
            width = orders.column_dimensions[cell.column_letter].width
            assert max(len(w) for w in cell.value.split()) * 1.15 + 2 <= width + 1e-9, cell.value


def test_wrapped_lines_counts_lines_at_whole_words():
    assert wrapped_lines("", 10) == 1
    assert wrapped_lines("ett två tre", 11) == 1
    assert wrapped_lines("ett två tre", 7) == 2
    assert wrapped_lines("avverkningsdag", 5) == 3
