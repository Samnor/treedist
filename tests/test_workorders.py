"""The work orders behind the month's matrices: which, how much each brought, how far along, and where S3 came from."""

import pandas as pd
import pytest
from test_appendix import demo_run
from test_sankey import mixed  # noqa: F401  the fixture

from treedist.sankey import mill_appendix_html
from treedist.schema import AO, DEST, DIA, SORT, VINTAGE, VOL
from treedist.workorders import donors, drift, work_orders


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


def test_borrowed_wood_names_the_work_orders_it_was_borrowed_from(mixed):  # noqa: F811
    lent = donors(mixed)
    assert set(lent[AO]) == {"B"}
    assert set(lent["givare"]) == set(mixed.step.ledger.history.loc[lambda h: h[SORT] == "TALL", AO])
    assert lent["vikt"].sum() == pytest.approx(1.0)


def test_drift_compares_the_first_and_second_half_of_the_harvest_in_felling_order():
    history = pd.DataFrame({AO: "X", SORT: "TALL", DIA: ["20", "22", "30", "32"], "langdgrupp": "400",
                            VINTAGE: ["2026-01-01", "2026-01-02", "2026-02-01", "2026-02-02"], VOL: 1.0})
    row = drift(history).loc[("X", "TALL")]
    assert row["forsta_avverkningsdag"] == "2026-01-01" and row["sista_avverkningsdag"] == "2026-02-02"
    assert row["medeldiameter_forsta_halvan_cm"] == pytest.approx(21.0)
    assert row["medeldiameter_andra_halvan_cm"] == pytest.approx(31.0)


def page_of(output):
    return mill_appendix_html(output, output.invoice[DEST].iloc[0])


def test_the_page_counts_the_work_orders_and_shows_no_map_without_positions(mixed):  # noqa: F811
    page = page_of(mixed)
    assert "Arbetsordrarna bakom matrisen" in page and "Matrisen bygger på virke från 3 arbetsordrar" in page
    assert "Lånad fördelning (S3): varifrån den kom" in page
    assert 'class="map"' not in page and "Åtgärder och medelstam</h3>" not in page


def test_a_run_writes_the_work_orders_as_csv(tmp_path):
    out = demo_run(tmp_path, "arbetsordrar", False)
    table = pd.read_csv(out / "arbetsordrar.csv", dtype=str)
    assert len(table) and {AO, DEST, VOL, "skordat_hittills_m3fub"} <= set(table.columns)


def test_each_work_order_shows_the_mean_diameter_it_brought_to_the_matrix(mixed):  # noqa: F811
    table = work_orders(mixed).set_index(AO)
    lines = mixed.step.allocation[mixed.step.allocation[AO] == "A"]
    cm = pd.to_numeric(lines[DIA], errors="coerce")
    expected = float((cm * lines[VOL]).sum() / lines.loc[cm.notna(), VOL].sum())
    assert table.loc["A", "medeldiameter_cm"] == pytest.approx(expected)
    assert pd.isna(table.loc["C", "medeldiameter_cm"])  # S4 has no diameter class


def test_shipping_more_than_harvested_is_marked(mixed):  # noqa: F811
    page = page_of(mixed)
    assert '<td class="flag">120 %</td>' in page


def test_nearly_all_is_not_shown_as_all():
    from treedist.sankey import _percent
    assert _percent(99.7, 100.0) == ">99 %" and _percent(100.0, 100.0) == "100 %" and _percent(0.2, 100.0) == "<1 %"


def test_the_appendix_has_one_matrix_for_all_assortments(mixed):  # noqa: F811
    from treedist.appendix import appendix_markdown

    destination = mixed.invoice[DEST].iloc[0]
    page = mill_appendix_html(mixed, destination)
    assert page.count("Stockarnas längd per dm och diameter per cm") == 1
    assert "alla handelssortiment" in page and "GRAN 20,000" in page and "TALL 150,000" in page
    text = appendix_markdown(mixed, destination)
    assert [line for line in text.splitlines() if line.startswith("## ")] == ["## Alla handelssortiment"]


def test_the_appendix_has_the_matrix_first_then_how_it_was_found(mixed):  # noqa: F811
    page = mill_appendix_html(mixed, mixed.invoice[DEST].iloc[0])
    order = [page.index(part) for part in ("Stockarnas längd per dm", "Hur matrisen togs fram", "<svg",
                                           "Arbetsordrarna bakom matrisen", "Så läser du sidan")]
    assert order == sorted(order)
    # The left of the diagram is the mill's assortments, not the mills.
    assert "Handelssortimenten, till vänster" in page and "Sågverken, till vänster" not in page


def test_a_small_volume_is_not_shown_as_zero():
    from treedist.sankey import _volume
    assert _volume(0.0) == "–" and _volume(0.02) == "<0,1" and _volume(19.1) == "19,1"
