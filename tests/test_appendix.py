"""The first deliverable: one matrix for all assortments for each mill and month, as an appendix to its invoice.

The price list is optional. Without it a run gives the same matrices and appendices, and no invoice basis.
"""

import re
from pathlib import Path

import pandas as pd
import pytest
from conftest import harvest_frame
from openpyxl.utils import get_column_letter
from test_reversals import HARVEST, loads

from treedist import adapters, contract
from treedist.check import FEL, check
from treedist.cli import main
from treedist.config import Config
from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.report import DEVELOPER_DIR, write_month
from treedist.schema import SORT, VOL

DEMO = "examples/demo"
# The demo gives the actual mill per load.
MILL = "mottagningsplats"
PERIOD = "2026-01"


def demo_run(tmp_path, name, *extra):
    files = {
        "--produktion": f"{DEMO}/produktion_{PERIOD}.csv",
        "--matning": f"{DEMO}/matning_{PERIOD}.csv",
        "--avtalsobjekt": f"{DEMO}/avtalsobjekt_{PERIOD}.csv",
    }
    out = tmp_path / name / "out"
    # The appendix as text and as rows is developer output; these tests read the matrices from it.
    argv = ["run", "--period", PERIOD, "--state", str(tmp_path / name / "state"), "--out", str(out), "--utvecklare"]
    assert main(argv + [x for pair in files.items() for x in pair] + list(extra)) == 0
    return out


def as_text(out):
    return out / DEVELOPER_DIR / "bilagor"


def appendix_rows(out):
    frames = [pd.read_csv(f).assign(mill=f.stem) for f in sorted(as_text(out).glob("*.csv"))]
    return pd.concat(frames, ignore_index=True)


def test_a_month_gives_one_appendix_per_mill_and_no_prices(tmp_path):
    out = demo_run(tmp_path, "utan")
    mills = set(pd.read_csv(f"{DEMO}/matning_{PERIOD}.csv")[MILL])
    assert {f.stem for f in as_text(out).glob("*.md")} == mills
    assert not (out / "fakturor").exists()
    assert not list(out.rglob("pris.csv"))
    lines = pd.read_csv(out / "faktura_rader.csv")
    assert not [c for c in lines.columns if "pris" in c or "belopp" in c]
    text = (as_text(out) / f"{sorted(mills)[0]}.md").read_text(encoding="utf-8")
    assert text.startswith(f"# Bilaga till faktura {PERIOD}")
    assert "| längd, dm |" in text and "Summa" in text


def test_each_appendix_adds_up_to_the_measured_volume_per_assortment(tmp_path):
    out = demo_run(tmp_path, "utan")
    measured = pd.read_csv(f"{DEMO}/matning_{PERIOD}.csv").groupby([MILL, SORT])[VOL].sum()
    rows = appendix_rows(out)
    billed = rows[rows["radtyp"].isin(["LEVERANS", "KREDITERING"])].groupby(["mill", SORT])[VOL].sum()
    assert billed.to_numpy() == pytest.approx(measured.to_numpy(), abs=1e-9)


def test_an_appendix_shows_a_reversed_load_from_an_earlier_month(cfg, tmp_path):
    first = run_month(Ledger.empty(), harvest_frame("2026-01", HARVEST), loads("2026-01", [("L1", "A", "TALL", 50.0, 50.0)], cfg),
                      "2026-01", set(), cfg)
    second = run_month(first.step.ledger, harvest_frame("2026-02", []), loads("2026-02", [("L1", "A", "TALL", -50.0, -50.0)], cfg),
                       "2026-02", set(), cfg)
    write_month(second, tmp_path, cfg, {}, developer=True)
    rows = appendix_rows(tmp_path)
    assert rows.loc[rows["radtyp"] == "KREDITERING", VOL].sum() == pytest.approx(-50.0)
    text = next(as_text(tmp_path).glob("*.md")).read_text(encoding="utf-8")
    assert "Krediterade lass från tidigare månader" in text and "netto -50.000 m3fub" in text


def test_check_needs_only_the_harvest_and_the_deliveries():
    files: dict[str, Path | None] = {"produktion": Path(f"{DEMO}/produktion_{PERIOD}.csv"), "matning": Path(f"{DEMO}/matning_{PERIOD}.csv")}
    findings = check(PERIOD, Config(), files=files)
    assert not [f for f in findings if f.level == FEL]


def test_the_contract_marks_which_tables_may_be_left_out():
    assert contract.REQUIRED_TABLES == ["produktion", "matning"]
    assert "prislista" not in contract.TABLES
    assert "## Avtalsobjekt (`avtalsobjekt`)\n\nValfri tabell." in contract.markdown()
    with pytest.raises(ValueError, match="produktion"):
        adapters.validate({"matning": pd.read_csv(f"{DEMO}/matning_{PERIOD}.csv")}, PERIOD)


def first_table(text):
    block = next(b for b in text.split("\n\n") if b.startswith("|"))
    rows = [line.strip("|").split("|") for line in block.splitlines() if "---|" not in line]
    head, *body = rows
    return pd.DataFrame([[c.strip() for c in row] for row in body], columns=[c.strip() for c in head])


def test_a_share_appendix_has_columns_of_100_and_the_same_sums(tmp_path):
    volume, shares = demo_run(tmp_path, "volym"), demo_run(tmp_path, "andel", "--bilaga", "andel")
    for appendix in as_text(shares).glob("*.md"):
        by_share = first_table(appendix.read_text(encoding="utf-8"))
        by_volume = first_table((as_text(volume) / appendix.name).read_text(encoding="utf-8"))
        pd.testing.assert_frame_equal(by_share.iloc[-1:], by_volume.iloc[-1:])
        assert by_share["Summa"].tolist() == by_volume["Summa"].tolist()
        cells = by_share.iloc[:-1, 1:-1].replace("", "0").astype(float)
        assert cells.sum().to_numpy() == pytest.approx(100, abs=0.05 * len(cells))


def test_every_appendix_has_a_printable_page(tmp_path):
    out = demo_run(tmp_path, "utan")
    for appendix in as_text(out).glob("*.md"):
        page = (out / "bilagor" / f"{appendix.stem}.html").read_text(encoding="utf-8")
        assert "@page { size: A4 landscape" in page and "<thead>" in page
        # One matrix on the page for every matrix in the text; the page also explains how it was found.
        assert page.count('class="corner"') == appendix.read_text(encoding="utf-8").count("| längd, dm |")


def test_a_run_says_when_the_source_description_changed_since_last_month(tmp_path, capsys):
    adapter = tmp_path / "kalla.py"
    adapter.write_text(
        "import pandas as pd\n"
        f"DEMO = {str(Path(DEMO).resolve())!r}\n"
        "def read(period):\n"
        "    return {'produktion': pd.read_csv(f'{DEMO}/produktion_{period}.csv'),\n"
        "            'matning': pd.read_csv(f'{DEMO}/matning_{period}.csv')}\n",
        encoding="utf-8")
    common = ["--kalla", str(adapter), "--state", str(tmp_path / "state")]
    assert main(["run", "--period", "2026-01", *common, "--out", str(tmp_path / "out1")]) == 0
    assert main(["run", "--period", "2026-02", *common, "--out", str(tmp_path / "out2")]) == 0
    assert "har ändrats" not in capsys.readouterr().out
    adapter.write_text(adapter.read_text(encoding="utf-8") + "# ändrad\n", encoding="utf-8")
    assert main(["run", "--period", "2026-03", *common, "--out", str(tmp_path / "out3")]) == 0
    assert "kalla.py har ändrats sedan 2026-02" in capsys.readouterr().out


def test_treedist_runs_as_a_module_where_the_exe_is_blocked():
    import subprocess
    import sys

    result = subprocess.run([sys.executable, "-m", "treedist", "--version"], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.startswith("treedist ")


def test_bands_group_the_classes_without_changing_any_sum(tmp_path):
    plain = demo_run(tmp_path, "klasser")
    banded = demo_run(tmp_path, "band", "--bilaga-langd", "370,430,490", "--bilaga-diameter", "14,20,26")
    for appendix in as_text(banded).glob("*.md"):
        by_band = first_table(appendix.read_text(encoding="utf-8"))
        by_class = first_table((as_text(plain) / appendix.name).read_text(encoding="utf-8"))
        assert list(by_band.columns) == ["längd, dm", "<14", "14–20", "20–26", "26+", "Summa"]
        assert by_band["längd, dm"].tolist() == ["<37", "37–43", "43–49", "49+", "Summa"]
        assert by_band.iloc[-1, -1] == by_class.iloc[-1, -1]


def test_the_matrix_has_a_column_per_cm_with_everything_under_13_and_from_50_gathered(tmp_path):
    from treedist.appendix import DIAMETER_FLOORS, AppendixLayout, _band, _label

    assert AppendixLayout().diameter == DIAMETER_FLOORS == tuple(range(13, 51))
    shown = [_label(_band(str(cm), DIAMETER_FLOORS), 1) for cm in (4, 12, 13, 14, 31, 49, 50, 51, 78)]
    assert shown == ["<13", "<13", "13", "14", "31", "49", "50+", "50+", "50+"]
    # The demo has classes of 1 cm from 10: the three below 13 share a column, the others keep their own.
    plain = demo_run(tmp_path, "klasser", "--bilaga-diameter", "klasser")
    gathered = demo_run(tmp_path, "forval")
    for appendix in as_text(gathered).glob("*.md"):
        by_cm = first_table(appendix.read_text(encoding="utf-8"))
        by_class = first_table((as_text(plain) / appendix.name).read_text(encoding="utf-8"))
        classes = [c for c in by_class.columns[1:-1]]
        assert classes == sorted(classes, key=int) and {"10", "12"} & set(classes)
        assert list(by_cm.columns[1:-1]) == ["<13", *[c for c in classes if int(c) >= 13]]
        assert by_cm["Summa"].tolist() == by_class["Summa"].tolist()
        page = (gathered / "bilagor" / f"{appendix.stem}.html").read_text(encoding="utf-8")
        # The note names the open columns the matrix shows, and no other.
        assert "Kolumnen &lt;13 är allt under 13 cm." in page and "50+ är allt från" not in page
        assert "allt under 13 cm" not in (plain / "bilagor" / f"{appendix.stem}.html").read_text(encoding="utf-8")


def test_a_matrix_with_every_column_is_set_small_enough_for_the_page():
    from treedist.appendix import DENSE, DIAMETER_FLOORS, PAGE, AppendixLayout, _em, _matrix_html, grid
    from treedist.schema import DIA, LEN

    classes = [str(cm) for cm in range(11, 52)]
    lines = pd.DataFrame([{DIA: dia, LEN: str(length), VOL: 5.0 + i % 3}
                          for i, dia in enumerate(classes) for length in (340, 400, 460)])
    litres = grid(lines, AppendixLayout())
    assert list(litres.columns) == ["<13", *[f"{a}–{a + 1}" for a in DIAMETER_FLOORS[:-1]], "50+"]
    assert litres.to_numpy().sum() == pytest.approx(lines[VOL].sum() * 1000)
    html = _matrix_html(litres, True)
    assert len(litres.columns) > DENSE and '<table class="dense"' in html
    assert re.findall(r"<tr><th>&lt;13</th><th>13</th><th>14</th>.*<th>49</th><th>50\+</th></tr>", html)
    # Sums in the hundreds of m3fub are wider than the percentages above them; the type gives way so that the last
    # columns stay on the page.
    wide = _matrix_html(litres * 20, True)
    size = lambda table: float(re.search(r"font-size:([\d.]+)pt", table).group(1))  # noqa: E731
    assert 4 <= size(wide) < size(html) <= 6
    foot = re.findall(r"<td[^>]*>([^<]*)</td>", wide.split('<tr class="total">')[1])
    assert sum(_em(cell) * size(wide) + 3.5 for cell in foot) <= PAGE


def test_bands_must_rise():
    assert main(["run", "--period", PERIOD, "--produktion", f"{DEMO}/produktion_{PERIOD}.csv", "--matning",
                 f"{DEMO}/matning_{PERIOD}.csv", "--state", "unused", "--out", "unused",
                 "--bilaga-langd", "400,370"]) == 1


def test_the_workbook_computes_the_appendix_from_its_own_rows(tmp_path):
    """Excel's own formulas, evaluated here, give the appendix's matrices and a zero check per assortment."""
    formulas = pytest.importorskip("formulas")
    out = demo_run(tmp_path, "excel", "--bilaga-langd", "370,430,490")
    book = next((out / "bilagor").glob("*.xlsx"))
    values = {key.upper().split("]")[-1]: cell.value[0][0]
              for key, cell in formulas.ExcelModel().loads(str(book)).finish().calculate().items() if hasattr(cell, "value")}
    text = (as_text(out) / f"{book.stem}.md").read_text(encoding="utf-8")
    sortiment = next(line[3:] for line in text.splitlines() if line.startswith("## "))
    expected = first_table(text)
    sheet = f"{sortiment.upper()}'!"
    total_cell = f"{sheet}{get_column_letter(len(expected.columns))}{4 + len(expected)}"
    assert values[total_cell] == pytest.approx(float(expected.iloc[-1, -1]), abs=1e-9)
    checks = [v for k, v in values.items() if k.startswith("LÄS FÖRST'!D") and isinstance(v, float)]
    assert checks and all(abs(v) < 1e-9 for v in checks)
    rounding = [v for k, v in values.items() if k.startswith("BILAGANS RADER'!K") and isinstance(v, float)]
    assert rounding and max(abs(v) for v in rounding) <= 0.0011


def test_labels_show_length_in_dm_and_a_one_unit_band_as_its_class():
    from treedist.appendix import _label

    assert [_label(x, 10) for x in ["370", "<300", "510+", "370–380", "370–430", "375", "OKÄND"]] == [
        "37", "<30", "51+", "37", "37–43", "37,5", "OKÄND"]
    assert [_label(x, 1) for x in ["24", "12–13", "12–14"]] == ["24", "12", "12–14"]


def test_the_page_has_length_rows_and_whole_percent_of_each_diameter_column(tmp_path):
    import re

    out = demo_run(tmp_path, "sida")
    rows = appendix_rows(out)
    for page in (out / "bilagor").glob("*.html"):
        html = page.read_text(encoding="utf-8")
        delivered = rows[(rows["mill"] == page.stem) & (rows["radtyp"] == "LEVERANS")]
        together = delivered[SORT].nunique() > 1
        assert ("Levererad volym per längd- och diameterklass, alla handelssortiment" in html) == together
        table = html.split("<table", 2)[1]
        assert 'rowspan="2">Längd, dm</th><th class="axis"' in table and ">Diameter, cm</th>" in table
        body = re.findall(r"<tr><th>[^<]*</th>(.*?)</tr>", table)
        cells = [re.findall(r"<td[^>]*>([^<]*)</td>", row)[:-1] for row in body]
        for column in zip(*cells):
            assert all(c in ("–", "&lt;1") or c.isdigit() for c in column)
            whole = [int(c) for c in column if c.isdigit()]
            small = sum(c == "&lt;1" for c in column)
            assert sum(whole) - 0.5 * len(whole) <= 100 <= sum(whole) + 0.5 * len(whole) + small
        total = re.search(r'<tr class="total">.*?<td class="sum">([^<]*)</td>', table).group(1)
        volume = delivered[VOL].sum() if together else delivered.groupby(SORT)[VOL].sum().iloc[0]
        assert total == f"{volume:,.1f}".replace(",", " ").replace(".", ",")


def test_the_workbook_follows_the_appendix_and_its_formulas_give_the_appendixs_numbers(tmp_path):
    formulas = pytest.importorskip("formulas")
    from openpyxl import load_workbook

    out = demo_run(tmp_path, "bilaga_excel")
    book_path = next((out / "bilagor").glob("*.xlsx"))
    names = load_workbook(book_path).sheetnames
    assert names[0] == "Läs först" and names[2:6] == ["Källor", "Avtalsobjekt", "Avverkningsformer", "Förklaring"]
    assert names.index("Fördelning") > names.index("Förklaring")
    values = {key.upper().split("]")[-1]: cell.value[0][0]
              for key, cell in formulas.ExcelModel().loads(str(book_path)).finish().calculate().items()
              if hasattr(cell, "value")}
    rows = pd.read_csv(out / "avtalsobjekt.csv", dtype={"avtalsobjekt": str})
    rows = rows[rows["mottagningsplats"] == book_path.stem]
    cells = {k: v for k, v in values.items() if re.fullmatch(r"AVTALSOBJEKT'![CD]\d+", k) and isinstance(v, float)}
    summed = sum(v for k, v in cells.items() if "!C" in k)
    assert summed == pytest.approx(rows["volym_m3fub"].sum(), abs=1e-6)
    sources = [values[f"KÄLLOR'!A{r}"] for r in range(5, 8)]
    assert sources == ["Eget lager", "Egen skörd i snitt", "Summa"]
    shares = [v for k, v in cells.items() if "!D" in k]
    assert sum(shares) == pytest.approx(1.0)
