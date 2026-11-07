"""The Sankey page: how much of the month's volume has a distribution of its own, and how much is approximated."""

import re

import pytest
from conftest import harvest_frame
from test_appendix import demo_run
from test_reversals import HARVEST, loads

from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.sankey import mill_appendix_html, tier_volumes
from treedist.schema import DEST


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


def appendix(output, quality=None):
    return mill_appendix_html(output, output.invoice[DEST].iloc[0], quality)


def test_the_page_draws_each_flow_and_says_how_much_is_settled(mixed):
    page = appendix(mixed)
    assert "<svg" in page and "Av matrisens 170,0 m3fub har 59 %" in page
    for name in ("Bestämd (S1)", "Approximerad (S2, S3)", "Ingen fördelning (S4)", "S2 Arbetsorderns skörd hittills",
                 "S3 Lånad från liknande arbetsordrar"):
        assert name in page
    # One band per assortment and class into the middle, and one per approximated kind out of it.
    assert len(re.findall(r"<path ", page)) == 4 + 2
    # Nothing is fetched from the internet, so the page works on a locked-down machine.
    assert "http" not in page.replace('xmlns="http://www.w3.org/2000/svg"', "")


def test_a_run_writes_how_the_matrix_was_found_into_each_appendix(tmp_path):
    out = demo_run(tmp_path, "sankey", False)
    assert not (out / "sakerhet.html").exists()
    for page in (out / "bilagor").glob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert "Hur matrisen togs fram" in text and "<svg" in text


def test_every_part_of_the_page_is_explained_for_the_reader_who_wants_it(mixed):
    page = appendix(mixed)
    guide = page.split("Så läser du sidan", 1)[1]
    for part in ("Ordningen", "Matrisen", "Diagrammet", "Handelssortimenten, till vänster", "Bestämd (S1)",
                 "Approximerad (S2, S3)", "S2 Arbetsorderns skörd hittills", "S3 Lånad från liknande arbetsordrar",
                 "Ingen fördelning (S4)", "Arbetsordrarna bakom matrisen", "Arbetsorderns skörd",
                 "Fälld och medeldiameter", "Lånad fördelning (S3)", "Tabellen under diagrammet"):
        assert f"<dt>{part}" in guide
    # The node figures and the colours are explained with the diagram.
    assert "Vid varje nod står dess volym" in guide and "Färgerna är grupperna" in guide
