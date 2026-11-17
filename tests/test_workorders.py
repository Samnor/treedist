"""The work orders behind the month's matrices: which, how much each brought and how far along each is."""

import pandas as pd
import pytest
from conftest import harvest_frame
from test_allocate import reclassified
from test_appendix import demo_run
from test_sankey import mixed  # noqa: F401  the fixture

from treedist.bilaga_html import mill_appendix_html
from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.schema import AO, DEST, DIA, PRODUCED, SORT, VINTAGE, VOL
from treedist.workorders import drift, work_orders


def test_each_mill_lists_its_work_orders_and_they_add_up_to_its_volume(mixed):  # noqa: F811
    table = work_orders(mixed)
    allocation = mixed.step.allocation
    assert set(table[AO]) == set(allocation.loc[allocation[VOL] > 0, AO])
    per_mill = table.groupby(DEST)[VOL].sum()
    assert per_mill.to_dict() == pytest.approx(allocation.groupby(DEST)[VOL].sum().to_dict())
    assert table.groupby(DEST)["andel_av_sagverket"].sum().to_list() == pytest.approx([1.0] * len(per_mill))


def test_a_work_order_that_ships_more_than_it_harvested_shows_it(mixed):  # noqa: F811
    row = work_orders(mixed).set_index(AO).loc["A"]
    assert row["S1"] == pytest.approx(100.0) and row["S2"] == pytest.approx(20.0)
    assert row["levererat_i_manaden_m3fub"] > row["skordat_hittills_m3fub"]


def test_drift_compares_the_first_and_second_half_of_the_harvest_in_felling_order():
    history = pd.DataFrame({AO: "X", PRODUCED: "TALL", DIA: ["20", "22", "30", "32"], "langdklass": "400",
                            VINTAGE: ["2026-01-01", "2026-01-02", "2026-02-01", "2026-02-02"], VOL: 1.0})
    row = drift(history).loc[("X", "TALL")]
    assert row["forsta_avverkningsdag"] == "2026-01-01" and row["sista_avverkningsdag"] == "2026-02-02"
    assert row["medeldiameter_forsta_halvan_cm"] == pytest.approx(21.0)
    assert row["medeldiameter_andra_halvan_cm"] == pytest.approx(31.0)


def page_of(output):
    return mill_appendix_html(output, output.invoice[DEST].iloc[0])


def test_a_run_writes_the_work_orders_as_csv(tmp_path):
    out = demo_run(tmp_path, "avtalsobjekt")
    table = pd.read_csv(out / "avtalsobjekt.csv", dtype=str)
    assert len(table) and {AO, DEST, VOL, "skordat_hittills_m3fub"} <= set(table.columns)


def test_shipping_more_than_harvested_is_marked(mixed):  # noqa: F811
    page = page_of(mixed)
    assert '<td class="flag">120 %</td>' in page


def test_nearly_all_is_not_shown_as_all():
    from treedist.bilaga import percent as _percent
    assert _percent(99.7, 100.0) == ">99 %" and _percent(100.0, 100.0) == "100 %" and _percent(0.2, 100.0) == "<1 %"


def test_the_appendix_has_one_matrix_for_all_assortments(mixed):  # noqa: F811
    from treedist.appendix import appendix_markdown

    destination = mixed.invoice[DEST].iloc[0]
    page = mill_appendix_html(mixed, destination)
    assert page.count("Levererad volym per längd- och diameterklass") == 1
    assert "alla handelssortiment" in page and "GRAN 20,000" in page and "TALL 150,000" in page
    text = appendix_markdown(mixed, destination)
    assert [line for line in text.splitlines() if line.startswith("## ")] == ["## Alla handelssortiment"]


def test_a_small_volume_is_not_shown_as_zero():
    from treedist.bilaga import volume_text as _volume
    assert _volume(0.0) == "–" and _volume(0.02) == "<0,1" and _volume(19.1) == "19,1"


def test_the_month_against_the_whole_harvest_and_both_halves_of_it():
    from treedist.workorders import differs

    history = pd.DataFrame({AO: "X", PRODUCED: "TALL", DIA: ["20", "30"], "langdklass": ["400", "460"],
                            VINTAGE: ["2026-01-01", "2026-02-01"], VOL: 1.0})
    row = drift(history).loc[("X", "TALL")]
    assert row["medellangd_forsta_halvan_cm"] == pytest.approx(400) and row["medellangd_andra_halvan_cm"] == pytest.approx(460)
    # The month brought only the thin logs: half the harvest's volume lies in another class.
    month = pd.DataFrame({DEST: "M", SORT: "TALL", AO: "X", DIA: ["20"], "langdklass": ["400"], VOL: [5.0]})
    produced = month.assign(**{PRODUCED: "TALL"}).groupby([DEST, SORT, AO, PRODUCED])[VOL].sum()
    assert differs(month, history, produced).loc[("M", "TALL", "X")] == pytest.approx(0.5)


def test_delivered_beyond_the_planned_volume_is_marked(mixed):  # noqa: F811
    from treedist.contract import MEASURE
    from treedist.workorders import Facts, measures

    planned = measures(pd.DataFrame({AO: ["A"], MEASURE: ["slutavverkning"], VOL: ["100"]}))
    page = mill_appendix_html(mixed, mixed.invoice[DEST].iloc[0], facts=Facts(measures=planned))
    assert "Levererat hittills, andel av planerad volym" in page and '120 % av 100</td>' in page and 'class="flag">120 % av 100' in page


def test_the_matrix_has_no_row_of_uncertainty(mixed):  # noqa: F811
    page = page_of(mixed)
    assert "Osäkerhet, ±" not in page and "<dt>Osäkerheten" not in page and "dragning" not in page


def test_the_page_counts_the_work_orders_and_names_no_other_source(mixed):  # noqa: F811
    page = page_of(mixed)
    assert "Avtalsobjekten bakom matrisen" in page and "Matrisen bygger på virke från 3 avtalsobjekt" in page
    assert "Liknande avtalsobjekt" not in page and "lånades" not in page
    assert 'class="map"' not in page and "Avverkningsformer och medelstam</h3>" not in page


def test_each_work_order_shows_the_mean_diameter_it_brought_to_the_matrix(mixed):  # noqa: F811
    table = work_orders(mixed).set_index(AO)
    lines = mixed.step.allocation[mixed.step.allocation[AO] == "A"]
    cm = pd.to_numeric(lines[DIA], errors="coerce")
    expected = float((cm * lines[VOL]).sum() / lines.loc[cm.notna(), VOL].sum())
    assert table.loc["A", "medeldiameter_cm"] == pytest.approx(expected)
    assert table.loc["B", "medeldiameter_cm"] == pytest.approx(20.0)


def test_the_appendix_has_the_matrix_first_then_how_it_was_found(mixed):  # noqa: F811
    page = mill_appendix_html(mixed, mixed.invoice[DEST].iloc[0])
    order = [page.index(part) for part in ("Levererad volym per längd- och diameterklass", "Hur matrisen togs fram", "<svg",
                                           "Egen skörd i snitt: så fördelas volym utöver lagret",
                                           "Avtalsobjekten bakom matrisen", "Så läser du bilagan")]
    assert order == sorted(order)
    # The left of the diagram is the mill's assortments, not the mills.
    assert "Handelssortimenten, till vänster" in page and "Sågverken, till vänster" not in page


def test_wood_measured_in_as_another_assortment_shows_the_harvest_it_was_produced_as(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 75.0), ("A", "TALL", "20", "340", 25.0)])
    deliveries = reclassified("2026-01", [("A", "TALL", "TALL", 20.0), ("A", "MASSA", "TALL", 20.0)], cfg)
    table = work_orders(run_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)).set_index(SORT)
    # Both rows are wood the harvester produced as TALL: 100 harvested, 40 delivered to all mills, 60 left.
    for measured in ("TALL", "MASSA"):
        row = table.loc[measured]
        assert row[VOL] == pytest.approx(20.0)
        assert row["skordat_hittills_m3fub"] == pytest.approx(100.0)
        assert row["levererat_i_manaden_m3fub"] == pytest.approx(40.0)
        assert row["kvar_i_lager_m3fub"] == pytest.approx(60.0)
        assert row["forsta_avverkningsdag"] == "2026-01-01" and row["sista_avverkningsdag"] == "2026-01-01"
        assert row["annan_klass_an_hela_skorden"] == pytest.approx(0.0)


def test_a_row_of_wood_produced_as_two_assortments_is_compared_with_both_harvests_by_what_each_brought():
    from treedist.workorders import differs

    history = pd.DataFrame({AO: "X", PRODUCED: ["TALL", "MASSA"], DIA: ["30", "10"], "langdklass": "400",
                            VINTAGE: "2026-01-01", VOL: [30.0, 10.0]})
    month = pd.DataFrame({DEST: "M", SORT: "MASSA", AO: "X", DIA: ["30", "10"], "langdklass": "400", VOL: [5.0, 5.0]})
    produced = pd.Series([5.0, 5.0], index=pd.MultiIndex.from_tuples(
        [("M", "MASSA", "X", "TALL"), ("M", "MASSA", "X", "MASSA")], names=[DEST, SORT, AO, PRODUCED]))
    # Half the row was produced as each assortment, so half of each harvest is what the whole harvest would give.
    assert differs(month, history, produced).loc[("M", "MASSA", "X")] == pytest.approx(0.0)


def test_a_month_that_also_reverses_loads_is_still_compared_with_the_harvest(cfg):
    from conftest import delivery_frame

    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0)])
    first = run_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 40.0)], cfg), "2026-01", set(), cfg)
    empty = harvest_frame("2026-02", [])
    # The month reverses more than it delivers, so its net is negative, and still delivers 10 m3fub.
    rows = delivery_frame("2026-02", [("A", "TALL", -40.0), ("A", "TALL", 10.0)], cfg)
    rows = rows.assign(leveransnummer=["2026-01-0", "NY"], brutto_m3fub=[-40.0, 10.0])
    row = work_orders(run_month(first.step.ledger, empty, rows, "2026-02", set(), cfg)).iloc[0]
    assert row[VOL] == pytest.approx(10.0) and row["annan_klass_an_hela_skorden"] == pytest.approx(0.0)
