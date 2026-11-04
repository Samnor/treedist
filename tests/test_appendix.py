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


def demo_run(tmp_path, name, priced):
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
    assert main(argv + [x for pair in files.items() for x in pair]) == 0
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
