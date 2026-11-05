"""The first deliverable: one matrix per assortment for each mill and month, as an appendix to its invoice.

The price list is optional. Without it a run gives the same matrices and appendices, and no invoice basis.
"""

from pathlib import Path

import pandas as pd
import pytest
from conftest import harvest_frame
from test_reversals import HARVEST, loads

from treedist import adapters, contract
from treedist.check import FEL, INFO, check
from treedist.cli import main
from treedist.config import Config
from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.report import write_month
from treedist.schema import SORT, VOL

DEMO = "examples/demo"
# The demo gives the actual mill per load.
MILL = "mottagningsplats"
PERIOD = "2026-01"


def demo_run(tmp_path, name, priced, *extra):
    files = {
        "--skordning": f"{DEMO}/skordning_{PERIOD}.csv",
        "--leverans": f"{DEMO}/leverans_{PERIOD}.csv",
        "--arbetsordrar": f"{DEMO}/arbetsordrar.csv",
        "--avslutade-ao": f"{DEMO}/avslutade_ao_{PERIOD}.csv",
    }
    if priced:
        files["--prislista"] = f"{DEMO}/prislista.csv"
    out = tmp_path / name / "out"
    argv = ["run", "--period", PERIOD, "--state", str(tmp_path / name / "state"), "--out", str(out)]
    assert main(argv + [x for pair in files.items() for x in pair] + list(extra)) == 0
    return out


def appendix_rows(out):
    frames = [pd.read_csv(f).assign(mill=f.stem) for f in sorted((out / "bilagor").glob("*.csv"))]
    return pd.concat(frames, ignore_index=True)


def test_a_month_runs_without_a_price_list_and_gives_one_appendix_per_mill(tmp_path):
    out = demo_run(tmp_path, "utan", priced=False)
    mills = set(pd.read_csv(f"{DEMO}/leverans_{PERIOD}.csv")[MILL])
    assert {f.stem for f in (out / "bilagor").glob("*.md")} == mills
    assert not (out / "fakturor").exists()
    assert not list((out / "matriser").rglob("pris.csv"))
    text = (out / "bilagor" / f"{sorted(mills)[0]}.md").read_text(encoding="utf-8")
    assert text.startswith(f"# Bilaga till faktura {PERIOD}")
    assert "| diameter, cm |" in text and "Summa" in text


def test_prices_do_not_change_the_matrices_or_the_appendices(tmp_path):
    priced, unpriced = demo_run(tmp_path, "med", True), demo_run(tmp_path, "utan", False)
    with_prices = pd.read_csv(priced / "matriser_lang.csv").drop(columns=["pris_kr_m3fub", "varde_kr"])
    pd.testing.assert_frame_equal(with_prices, pd.read_csv(unpriced / "matriser_lang.csv"))
    for appendix in (unpriced / "bilagor").iterdir():
        if appendix.suffix != ".xlsx":  # A workbook carries the time it was written.
            assert appendix.read_bytes() == (priced / "bilagor" / appendix.name).read_bytes()
    assert (priced / "fakturor").exists()


def test_each_appendix_adds_up_to_the_measured_volume_per_assortment(tmp_path):
    out = demo_run(tmp_path, "utan", priced=False)
    measured = pd.read_csv(f"{DEMO}/leverans_{PERIOD}.csv").groupby([MILL, SORT])[VOL].sum()
    rows = appendix_rows(out)
    billed = rows[rows["radtyp"].isin(["LEVERANS", "KREDITERING"])].groupby(["mill", SORT])[VOL].sum()
    assert billed.to_numpy() == pytest.approx(measured.to_numpy(), abs=1e-9)


def test_an_appendix_shows_a_reversed_load_from_an_earlier_month(cfg, tmp_path):
    first = run_month(Ledger.empty(), harvest_frame("2026-01", HARVEST), loads("2026-01", [("L1", "A", "TALL", 50.0, 50.0)], cfg),
                      None, "2026-01", set(), cfg)
    second = run_month(first.step.ledger, harvest_frame("2026-02", []), loads("2026-02", [("L1", "A", "TALL", -50.0, -50.0)], cfg),
                       None, "2026-02", set(), cfg)
    write_month(second, tmp_path, cfg, {})
    rows = appendix_rows(tmp_path)
    assert rows.loc[rows["radtyp"] == "KREDITERING", VOL].sum() == pytest.approx(-50.0)
    text = next((tmp_path / "bilagor").glob("*.md")).read_text(encoding="utf-8")
    assert "Ändringar av tidigare månaders leveranser" in text and "netto -50.000 m3fub" in text


def test_check_without_a_price_list_has_no_error():
    files: dict[str, Path | None] = {"skordning": Path(f"{DEMO}/skordning_{PERIOD}.csv"), "leverans": Path(f"{DEMO}/leverans_{PERIOD}.csv")}
    findings = check(PERIOD, Config(), files=files)
    assert not [f for f in findings if f.level == FEL]
    assert any(f.level == INFO and f.table == "prislista" for f in findings)


def test_the_contract_marks_which_tables_may_be_left_out():
    assert contract.REQUIRED_TABLES == ["skordning", "leverans"]
    assert "## Prislista (`prislista`)\n\nValfri tabell." in contract.markdown()
    with pytest.raises(ValueError, match="skordning"):
        adapters.validate({"leverans": pd.read_csv(f"{DEMO}/leverans_{PERIOD}.csv")}, PERIOD, Config())


def first_table(text):
    block = next(b for b in text.split("\n\n") if b.startswith("|"))
    rows = [line.strip("|").split("|") for line in block.splitlines() if "---|" not in line]
    head, *body = rows
    return pd.DataFrame([[c.strip() for c in row] for row in body], columns=[c.strip() for c in head])


def test_a_share_appendix_has_columns_of_100_and_the_same_sums(tmp_path):
    volume, shares = demo_run(tmp_path, "volym", False), demo_run(tmp_path, "andel", False, "--bilaga", "andel")
    for appendix in (shares / "bilagor").glob("*.md"):
        by_share = first_table(appendix.read_text(encoding="utf-8"))
        by_volume = first_table((volume / "bilagor" / appendix.name).read_text(encoding="utf-8"))
        pd.testing.assert_frame_equal(by_share.iloc[-1:], by_volume.iloc[-1:])
        assert by_share["Summa"].tolist() == by_volume["Summa"].tolist()
        cells = by_share.iloc[:-1, 1:-1].replace("", "0").astype(float)
        assert cells.sum().to_numpy() == pytest.approx(100, abs=0.05 * len(cells))


def test_every_appendix_has_a_printable_page(tmp_path):
    out = demo_run(tmp_path, "utan", priced=False)
    for appendix in (out / "bilagor").glob("*.md"):
        page = appendix.with_suffix(".html").read_text(encoding="utf-8")
        assert "@page { size: A4 landscape" in page and "<thead>" in page
        assert page.count("<table") == appendix.read_text(encoding="utf-8").count("| diameter, cm |")


def test_a_run_says_when_the_source_description_changed_since_last_month(tmp_path, capsys):
    adapter = tmp_path / "kalla.py"
    adapter.write_text(
        "import pandas as pd\n"
        f"DEMO = {str(Path(DEMO).resolve())!r}\n"
        "def read(period):\n"
        "    return {'skordning': pd.read_csv(f'{DEMO}/skordning_{period}.csv'),\n"
        "            'leverans': pd.read_csv(f'{DEMO}/leverans_{period}.csv')}\n",
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
    plain = demo_run(tmp_path, "klasser", False)
    banded = demo_run(tmp_path, "band", False, "--bilaga-langd", "370,430,490", "--bilaga-diameter", "14,20,26")
    for appendix in (banded / "bilagor").glob("*.md"):
        by_band = first_table(appendix.read_text(encoding="utf-8"))
        by_class = first_table((plain / "bilagor" / appendix.name).read_text(encoding="utf-8"))
        assert list(by_band.columns) == ["diameter, cm", "<370", "370–430", "430–490", "490+", "Summa"]
        assert by_band["diameter, cm"].tolist() == ["<14", "14–20", "20–26", "26+", "Summa"]
        assert by_band.iloc[-1, -1] == by_class.iloc[-1, -1]


def test_bands_must_rise():
    assert main(["run", "--period", PERIOD, "--skordning", f"{DEMO}/skordning_{PERIOD}.csv", "--leverans",
                 f"{DEMO}/leverans_{PERIOD}.csv", "--state", "unused", "--out", "unused",
                 "--bilaga-langd", "400,370"]) == 1


def test_the_workbook_computes_the_appendix_from_its_own_rows(tmp_path):
    """Excel's own formulas, evaluated here, give the appendix's matrices and a zero check per assortment."""
    formulas = pytest.importorskip("formulas")
    out = demo_run(tmp_path, "excel", False, "--bilaga-langd", "370,430,490")
    book = next((out / "bilagor").glob("*.xlsx"))
    values = {key.upper().split("]")[-1]: cell.value[0][0]
              for key, cell in formulas.ExcelModel().loads(str(book)).finish().calculate().items() if hasattr(cell, "value")}
    text = book.with_suffix(".md").read_text(encoding="utf-8")
    sortiment = next(line[3:] for line in text.splitlines() if line.startswith("## "))
    expected = first_table(text)
    sheet = f"{sortiment.upper()}'!"
    total_cell = f"{sheet}{chr(ord('A') + len(expected.columns) - 1)}{4 + len(expected)}"
    assert values[total_cell] == pytest.approx(float(expected.iloc[-1, -1]), abs=1e-9)
    checks = [v for k, v in values.items() if k.startswith("LÄS FÖRST'!D") and isinstance(v, float)]
    assert checks and all(abs(v) < 1e-9 for v in checks)
    rounding = [v for k, v in values.items() if k.startswith("BILAGANS RADER'!K") and isinstance(v, float)]
    assert rounding and max(abs(v) for v in rounding) <= 0.0011
