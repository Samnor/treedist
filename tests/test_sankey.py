"""The Sankey page: how much of the month's volume comes from the work orders' own stock, and how much is estimated."""

import re

import pytest
from conftest import harvest_frame
from test_appendix import demo_run
from test_reversals import HARVEST, loads

from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.bilaga import tier_volumes
from treedist.bilaga_html import mill_appendix_html
from treedist.schema import DEST

MIXED = HARVEST + [("B", "TALL", "20", "400", 50.0), ("C", "GRAN", "18", "400", 40.0)]


@pytest.fixture
def mixed(cfg):
    """A ships 20 more than its stock (S1 and S2); B and C ship from their stock (S1), C in another assortment."""
    deliveries = loads("2026-01", [("L1", "A", "TALL", 120.0, 120.0), ("L2", "B", "TALL", 30.0, 30.0),
                                   ("L3", "C", "GRAN", 20.0, 20.0)], cfg)
    return run_month(Ledger.empty(), harvest_frame("2026-01", MIXED), deliveries, "2026-01", set(), cfg)


def test_every_source_gets_its_volume_and_the_sources_add_up_to_the_month(mixed):
    volumes = tier_volumes(mixed)
    assert volumes.sum().to_dict() == pytest.approx({"S1": 150.0, "S2": 20.0})
    assert volumes.to_numpy().sum() == pytest.approx(mixed.step.allocation["volym_m3fub"].sum())


def appendix(output):
    return mill_appendix_html(output, output.invoice[DEST].iloc[0])


def diagram(page):
    return page.split("Hur matrisen togs fram", 1)[1].split("</svg>", 1)[0]


def test_the_page_draws_each_flow_and_says_how_much_is_estimated(mixed):
    page = appendix(mixed)
    assert "<svg" in page and "Diagrammet visar matrisens 170,0 m3fub per handelssortiment" in page
    assert "88 % ryms i avtalsobjektens eget lager och är fördelad så som skördaren mätte stockarna" in page
    assert "Resten, 12 %, levererades utöver lagret och är fördelad som avtalsobjektets hela skörd (egen skörd i snitt). " \
           "Det är en uppskattning, inte en mätning." in page
    # The reader sees names, not codes, and only the two sources there are.
    assert not any(f">{code}<" in page or f"({code})" in page for code in ("S1", "S2", "S3", "S4"))
    for name in ("Eget lager", "Egen skörd i snitt", "Mätt av skördaren", "Uppskattad"):
        assert name in page
    for gone in ("Liknande avtalsobjekt", "Okänd", "Approximerad", "lånad"):
        assert gone not in page, gone
    # One band per assortment and source: GRAN to its stock, TALL to its stock and to the estimate.
    assert len(re.findall(r"<path ", diagram(page))) == 3
    # Nothing is fetched from the internet, so the page works on a locked-down machine.
    assert "http" not in page.replace('xmlns="http://www.w3.org/2000/svg"', "")


def test_a_month_within_the_stock_says_that_nothing_is_estimated(cfg):
    deliveries = loads("2026-01", [("L1", "A", "TALL", 80.0, 80.0)], cfg)
    page = appendix(run_month(Ledger.empty(), harvest_frame("2026-01", HARVEST), deliveries, "2026-01", set(), cfg))
    assert "All volym ryms i avtalsobjektens eget lager" in page and "så som skördaren mätte stockarna" in page
    assert "ryms all volym till SAG i avtalsobjektens eget lager, så inget är fördelat som egen skörd i snitt" in page
    assert len(re.findall(r"<path ", diagram(page))) == 1


def test_a_run_writes_how_the_matrix_was_found_into_each_appendix(tmp_path):
    out = demo_run(tmp_path, "sankey")
    assert not (out / "sakerhet.html").exists()
    for page in (out / "bilagor").glob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert "Hur matrisen togs fram" in text and "<svg" in text


def test_every_part_of_the_page_is_explained_for_the_reader_who_wants_it(mixed):
    page = appendix(mixed)
    guide = page.split("Så läser du bilagan", 1)[1]
    parts = ["Matrisen", "Diagrammet", "Handelssortimenten, till vänster", "Eget lager, till höger",
             "Egen skörd i snitt, till höger", "Tabellen under diagrammet", "Exemplet", "Avtalsobjekten bakom matrisen",
             "Medeldiameter och Annan klass än hela skörden", "Hela avtalsobjektet", "Avverkad och skördens halvor",
             "Avverkningsformer och medelstam", "Vad bilagan inte säger"]
    assert re.findall(r"<dt>([^<]*)", guide) == parts
    # The figures at the bars and the colours are explained with the diagram.
    assert "Vid varje stapel står volymen i m3fub" in guide and "Blått är eget lager, orange egen skörd i snitt" in guide


def test_the_page_and_the_workbook_explain_their_parts_with_the_same_words():
    """The guide holds each part's words once; a format chooses the parts it shows, never what they say."""
    from treedist import bilaga

    words = bilaga._words()
    page, sheet = bilaga.PAGE_GUIDE, bilaga.FILE_GUIDE
    assert {k for _, k in page + sheet} <= words.keys()
    shared = {k for _, k in page} & {k for _, k in sheet}
    assert {"S1", "S2", "mean", "progress", "measures"} <= shared
    # The workbook has no diagram, so it never explains it.
    assert not {"diagram", "sources", "assortments"} & {k for _, k in bilaga.FILE_GUIDE}
