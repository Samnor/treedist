"""How good the approximations were, measured on the corrections that settle them when harvester data comes."""

import pandas as pd
import pytest
from conftest import harvest_frame
from test_reversals import loads

from treedist import quality
from treedist.cli import main
from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.sankey import mill_appendix_html
from treedist.schema import DEST

# A: 60 % class 14 and 40 % class 24, ships 20 more than its stock (S2 with A's own shares).
# B: no harvester data, borrows A's shares (S3). C: no harvester data in GRAN at all (S4).
JANUARY = [("A", "TALL", "14", "340", 60.0), ("A", "TALL", "24", "340", 40.0)]
# The data that settles them: A's next stems are all class 14, B is 30/70, C is one class.
FEBRUARY = [("A", "TALL", "14", "340", 50.0), ("B", "TALL", "14", "340", 9.0), ("B", "TALL", "24", "340", 21.0),
            ("C", "GRAN", "30", "400", 40.0)]


def months(cfg, closed=frozenset()):
    deliveries = loads("2026-01", [("L1", "A", "TALL", 120.0, 120.0), ("L2", "B", "TALL", 30.0, 30.0),
                                   ("L3", "C", "GRAN", 20.0, 20.0)], cfg)
    first = run_month(Ledger.empty(), harvest_frame("2026-01", JANUARY), deliveries, None, "2026-01", set(), cfg)
    record = quality.update(Ledger.empty(), first, None)
    second = run_month(first.step.ledger, harvest_frame("2026-02", FEBRUARY), loads("2026-02", [], cfg), None,
                       "2026-02", set(closed), cfg)
    return first, record, second, quality.update(first.step.ledger, second, (record.open, record.totals, record.since))


def test_the_share_that_changed_class_is_how_far_the_provisional_shares_were_from_the_harvested(cfg):
    _, before, _, after = months(cfg)
    assert before.by_tier()["avraknat_m3fub"].sum() == 0
    assert before.by_tier()["oppet_m3fub"].to_dict() == pytest.approx({"S2": 20.0, "S3": 30.0, "S4": 20.0})
    measured = after.by_tier()
    # A's 60/40 against all 14: 40 % moved. B's borrowed 60/40 against 30/70: 30 %. OKÄND against anything: 100 %.
    assert measured["andel_flyttad"].to_dict() == pytest.approx({"S2": 0.4, "S3": 0.3, "S4": 1.0})
    assert measured["avraknat_m3fub"]["S2"] == pytest.approx(20.0)
    assert after.since == "2026-01"


def test_a_closed_work_order_is_written_off_not_counted_as_corrected(cfg):
    *_, after = months(cfg, closed={"B"})
    measured = after.by_tier()
    # B's harvester data still settles what it owes before the order closes; nothing of B stays open.
    assert not (after.open[quality.AO] == "B").any()
    assert measured.loc["S3", "oppet_m3fub"] == 0


def test_the_page_tells_how_much_changed_class(cfg):
    *_, second, after = months(cfg)
    page = "".join(mill_appendix_html(second, mill, after) for mill in sorted(set(second.invoice[DEST])))
    assert "40 % av 20,0 m3fub" in page and "100 % av 20,0 m3fub" in page
    assert "Bytte klass vid rättelse, alla sågverk sedan 2026-01" in page
    assert "Rättas inte" in page


def test_the_record_follows_the_ledger_month_by_month(tmp_path):
    demo = "examples/demo"
    for period in ("2026-01", "2026-02", "2026-03"):
        assert main(["run", "--period", period, "--skordning", f"{demo}/skordning_{period}.csv",
                     "--leverans", f"{demo}/leverans_{period}.csv", "--state", str(tmp_path / "state"),
                     "--out", str(tmp_path / period)]) == 0
        assert (tmp_path / "state" / period / "preliminart.csv").exists()
    kept = pd.read_csv(tmp_path / "2026-03" / "rattelser.csv", dtype=str)
    assert set(kept["sedan"]) == {"2026-01"} and list(kept["sakerhetsklass"]) == ["S2", "S3", "S4"]
