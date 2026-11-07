"""The Sankey page: how much of the month's volume has a distribution of its own, and how much is approximated."""

import re

import pytest
from conftest import harvest_frame
from test_appendix import demo_run
from test_reversals import HARVEST, loads

from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.sankey import sankey_html, tier_volumes


@pytest.fixture
def mixed(cfg):
    """A work order that ships more than its stock (S1, S2), one with no harvester data (S3), an assortment with none (S4)."""
    deliveries = loads("2026-01", [("L1", "A", "TALL", 120.0, 120.0), ("L2", "B", "TALL", 30.0, 30.0),
                                   ("L3", "C", "GRAN", 20.0, 20.0)], cfg)
    return run_month(Ledger.empty(), harvest_frame("2026-01", HARVEST), deliveries, None, "2026-01", set(), cfg)


def test_every_class_gets_its_volume_and_the_classes_add_up_to_the_month(mixed):
    volumes = tier_volumes(mixed)
    assert volumes.sum().to_dict() == pytest.approx({"S1": 100.0, "S2": 20.0, "S3": 30.0, "S4": 20.0})
    assert volumes.to_numpy().sum() == pytest.approx(mixed.step.allocation["volym_m3fub"].sum())


def test_the_page_draws_each_flow_and_says_how_much_is_settled(mixed):
    page = sankey_html(mixed)
    assert "<svg" in page and "Av 170,0 m3fub levererat under 2026-01 har 59 %" in page
    for name in ("Bestämd (S1)", "Approximerad (S2, S3)", "Ingen fördelning (S4)", "S2 Arbetsorderns skörd hittills",
                 "S3 Lånad från liknande arbetsordrar"):
        assert name in page
    # One band per mill and class into the middle, and one per approximated kind out of it.
    assert len(re.findall(r"<path ", page)) == 4 + 2
    # Nothing is fetched from the internet, so the page works on a locked-down machine.
    assert "http" not in page.replace('xmlns="http://www.w3.org/2000/svg"', "")


def test_a_run_writes_the_page_for_the_month(tmp_path):
    out = demo_run(tmp_path, "sankey", False)
    page = (out / "sakerhet.html").read_text(encoding="utf-8")
    assert "Hur volymen fördelades på klasser" in page and "<svg" in page


def test_every_part_of_the_page_is_explained_for_the_reader_who_wants_it(mixed):
    page = sankey_html(mixed)
    guide = page.split("Så läser du sidan", 1)[1]
    for part in ("Sågverken, till vänster", "Bestämd (S1)", "Approximerad (S2, S3)", "S2 Arbetsorderns skörd hittills",
                 "S3 Lånad från liknande arbetsordrar", "Ingen fördelning (S4)", "Siffrorna vid en nod", "Färgerna",
                 "Tabellen"):
        assert f"<dt>{part}" in guide
