"""The distribution always comes from the work order's own harvester data, and what is estimated stands as estimated.

Volume within the stock is measured by the harvester (S1); volume beyond it is distributed as the work order's whole
harvest (S2), an estimate. A load without harvester data of its own stops the month, and no later month changes an
appendix that was sent.
"""

from pathlib import Path

import pandas as pd
import pytest
from conftest import harvest_frame
from openpyxl import load_workbook
from test_appendix import demo_run
from test_excel_values import assert_cached_values
from test_reversals import HARVEST, loads
from test_sankey import appendix, mixed  # noqa: F401  (mixed is a fixture)

from treedist import exempel
from treedist.cli import main
from treedist.config import Config, load_config
from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.dev.simulate import SimParams, simulate
from treedist.report import write_month
from treedist.schema import AO, VOL

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"

# Words that would promise a later change of a sent appendix.
LATER = ("rättas", "rättelse", "preliminär", "slutlig", "korriger", "justeras")


def check(period, *extra):
    return main(["check", "--period", period, "--produktion", str(DEMO / f"produktion_{period}.csv"),
                 "--matning", str(DEMO / f"matning_{period}.csv"), "--avtalsobjekt", str(DEMO / f"avtalsobjekt_{period}.csv"),
                 *extra])


def run(period, state, out):
    return main(["run", "--period", period, "--produktion", str(DEMO / f"produktion_{period}.csv"),
                 "--matning", str(DEMO / f"matning_{period}.csv"), "--avtalsobjekt", str(DEMO / f"avtalsobjekt_{period}.csv"), "--state", str(state), "--out", str(out)])


def test_a_month_started_without_the_earlier_harvest_stops_and_says_what_a_new_ledger_needs(tmp_path, capsys):
    # February's loads come from wood felled in January: a ledger that starts in February has no harvester data for them.
    assert run("2026-02", tmp_path / "state", tmp_path / "out") == 1
    stopped = capsys.readouterr().err
    assert "saknar egen skördardata" in stopped and "Liggaren är ny" in stopped and "Månaden körs inte" in stopped
    assert not (tmp_path / "out").exists() and not (tmp_path / "state" / "2026-02").exists()


def test_check_stops_on_the_same_month_against_the_ledger_and_only_warns_without_one(tmp_path, capsys):
    state = tmp_path / "state"
    assert check("2026-02", "--state", str(state)) == 1
    new = capsys.readouterr().out
    assert [line for line in new.splitlines() if line.startswith("FEL")][0].split()[1] == "provkörning"
    assert "Liggaren är ny" in new
    # Without a ledger the check cannot know what earlier months reported, so it warns and says how to find out.
    assert check("2026-02") == 0
    alone = capsys.readouterr().out
    assert "FEL" not in alone and "saknar egen skördardata" in alone and "Kör med --state" in alone
    # With January in the ledger the same month passes.
    assert run("2026-01", state, tmp_path / "out") == 0
    capsys.readouterr()
    assert check("2026-02", "--state", str(state)) == 0
    assert "levererad volym per säkerhetsklass: S1" in capsys.readouterr().out


def test_settings_for_borrowing_and_for_later_corrections_are_refused(tmp_path):
    path = tmp_path / "egen.toml"
    path.write_text("donor_group_weight = 2.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="som inte finns längre"):
        load_config(path)
    # What the two switches used to turn on is now always so; a file that still says it is read as before.
    path.write_text("own_harvest_only = true\ncorrection_on_invoice = false\n", encoding="utf-8")
    assert load_config(path) == Config()
    for line in ("own_harvest_only = false", "correction_on_invoice = true"):
        path.write_text(line + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="som inte går att välja längre"):
            load_config(path)


def test_the_example_adds_up():
    assert sum(exempel.HARVESTED) == 100 and sum(exempel.STOCK) + exempel.BEYOND == exempel.LOAD
    # The volume beyond the stock gets the classes of the whole harvest: 10 m3fub as 30, 50 and 20 %.
    assert exempel.ESTIMATE == tuple(h * exempel.BEYOND // 100 for h in exempel.HARVESTED) == (3, 5, 2)
    assert exempel.MONTH == tuple(s + e for s, e in zip(exempel.STOCK, exempel.ESTIMATE)) == (13, 25, 12)
    assert sum(exempel.MONTH) == exempel.LOAD
    # The last step splits the harvest on diameter and length classes: each cell gets its share of the volume beyond
    # the stock.
    assert tuple(sum(column) for column in zip(*exempel.HARVESTED_CELLS)) == exempel.HARVESTED
    assert exempel.ESTIMATE_CELLS == ((2.0, 2.0, 0.5), (1.0, 3.0, 1.5))
    assert tuple(sum(column) for column in zip(*exempel.ESTIMATE_CELLS)) == exempel.ESTIMATE


def test_the_page_explains_the_estimate_with_an_example_in_three_steps(mixed):  # noqa: F811
    page = appendix(mixed)
    section = page.split(exempel.TITLE, 1)[1]
    titles = [step.title for step in exempel.steps()]
    assert titles == ["1 Skörden hittills: 100 m3fub", "2 Lasset: 10 m3fub utöver lagret",
                      "3 De 10 får skördens andelar per diameter och längd"]
    positions = [section.index(title) for title in titles]
    assert positions == sorted(positions)
    # Each step has its figure, and the example's own numbers are in the text.
    assert section.count("<svg") >= 3
    # The last step says that the estimate is made per cell of the matrix, and shows one cell worked out.
    assert "en cell i matrisen" in section and "20 % av de 10: 2,0 m3fub" in section
    # The rule is said once, set apart: the shares come from the work order's whole harvest so far.
    assert f"<strong>{exempel.RULE}</strong>" in section and "hela skörd hittills" in exempel.RULE
    assert "samma andelar" in section
    assert "står 13, 25 och 12 i bilagan" in section
    # The classes are diameters in cm, as in the matrix, so that none reads as an assortment; the assortment is the
    # one measured in, and the page says that it is never estimated.
    assert exempel.CLASSES == ("18 cm", "24 cm", "30 cm") and "30 i 18 cm, 50 i 24 cm och 20 i 30 cm" in section
    assert "Handelssortimentet uppskattas aldrig" in section and "klent" not in section.lower()
    assert "Den här månaden levererades 20,0 m3fub utöver lagret" in section
    assert "uppskattning" in section


def test_the_workbook_explains_the_estimate_in_words_without_colours(mixed, tmp_path, cfg):  # noqa: F811
    write_month(mixed, tmp_path, cfg, {})
    book = load_workbook(next((tmp_path / "bilagor").glob("*.xlsx")))
    told = {row[0].value: row[1].value for row in book["Förklaring"].iter_rows() if row[0].value}
    for term, text in exempel.example_rows():
        assert told[term] == text
        assert "blått" not in text and "orange" not in text


def test_nothing_in_an_appendix_says_that_it_changes_later(mixed, tmp_path, cfg):  # noqa: F811
    write_month(mixed, tmp_path / "mixed", cfg, {})
    folders = [tmp_path / "mixed" / "bilagor", demo_run(tmp_path, "demo") / "bilagor"]
    for folder in folders:
        for page in folder.glob("*.html"):
            text = page.read_text(encoding="utf-8").lower()
            assert not [word for word in LATER if word in text], page.name
        for path in folder.glob("*.xlsx"):
            for sheet in load_workbook(path).worksheets:
                for row in sheet.iter_rows():
                    for cell in row:
                        if isinstance(cell.value, str):
                            assert not [word for word in LATER if word in cell.value.lower()], (sheet.title, cell.value)
    # The estimate is named as one.
    assert "uppskattning" in next(folders[0].glob("*.html")).read_text(encoding="utf-8")


def late_harvest(cfg):
    """January: A ships 20 beyond its stock. February: the harvester reports 50 more, in another class, and A ships 10."""
    january = run_month(Ledger.empty(), harvest_frame("2026-01", HARVEST),
                        loads("2026-01", [("L1", "A", "TALL", 120.0, 120.0)], cfg), "2026-01", set(), cfg)
    february = run_month(january.step.ledger, harvest_frame("2026-02", [("A", "TALL", "30", "400", 50.0)]),
                         loads("2026-02", [("L2", "A", "TALL", 10.0, 10.0)], cfg), "2026-02", set(), cfg)
    return january, february


def test_harvester_data_that_comes_later_changes_no_invoice(cfg, tmp_path):
    january, february = late_harvest(cfg)
    assert january.step.allocation.groupby("sakerhetsklass")[VOL].sum().to_dict() == pytest.approx({"S1": 100.0, "S2": 20.0})
    # February bills February's load and nothing about January.
    assert set(february.invoice["radtyp"]) == {"LEVERANS"}
    assert february.invoice[VOL].sum() == pytest.approx(10.0)
    # The 20 that left beyond the stock is taken from the new harvest, so it cannot be delivered twice.
    assert february.step.ledger.stock[VOL].sum() == pytest.approx(50.0 - 20.0 - 10.0)

    write_month(february, tmp_path / "standard", cfg, {})
    names = {p.name for p in (tmp_path / "standard").rglob("*") if p.is_file()}
    assert not [name for name in names if "korrigering" in name or "uppskattning" in name or "kvalitet" in name]
    # A developer can see how the estimate compares with what the harvester then reported; it sums to no volume.
    write_month(february, tmp_path / "utvecklare", cfg, {}, developer=True)
    compared = pd.read_csv(tmp_path / "utvecklare" / "utveckling" / "uppskattning_mot_skordardata.csv")
    assert len(compared) and compared[VOL].sum() == pytest.approx(0.0, abs=1e-6)
    assert compared[VOL].abs().sum() > 0


def test_the_workbook_has_two_sources_and_its_formulas_hold(tmp_path):
    folder = tmp_path / "in"
    folder.mkdir()
    flow = list(simulate(SimParams(months=2, seed=3)))
    for month in flow:
        month.harvest.to_csv(folder / f"produktion_{month.period}.csv", index=False)
        month.deliveries.to_csv(folder / f"matning_{month.period}.csv", index=False)
    # A file from before the two switches were removed still works.
    (folder / "policy.toml").write_text("own_harvest_only = true\ncorrection_on_invoice = false\n", encoding="utf-8")
    for month in flow:
        argv = ["run", "--period", month.period, "--produktion", str(folder / f"produktion_{month.period}.csv"),
                "--matning", str(folder / f"matning_{month.period}.csv"), "--state", str(tmp_path / "state"),
                "--out", str(tmp_path / month.period), "--config", str(folder / "policy.toml")]
        assert main(argv) == 0
    out = tmp_path / flow[-1].period
    assert_cached_values(out)
    for path in (out / "bilagor").glob("*.xlsx"):
        book = load_workbook(path)
        header = [c.value for c in book["Avtalsobjekt"][4]]
        assert "Eget lager, andel" in header and "Egen skörd i snitt, andel" in header
        assert not any(isinstance(h, str) and ("Liknande" in h or "Okänd" in h) for h in header)
        assert [c.value for c in book["Källor"]["A"][4:7]] == ["Eget lager", "Egen skörd i snitt", "Summa"]
        assert "Givare" not in book.sheetnames and "Ändringar" not in book.sheetnames
    shown = pd.read_csv(out / "avtalsobjekt.csv", dtype={AO: str})
    assert len(shown) and {"S1", "S2"} <= set(shown.columns) and not {"S3", "S4"} & set(shown.columns)
