"""Where the work orders are and what they hold: optional, read only for the appendix, never by the method."""

import pandas as pd
import pytest
from test_appendix import DEMO, PERIOD, demo_run
from test_sankey import mixed  # noqa: F401  the fixture

from treedist.check import _places
from treedist.contract import EAST, LAT, LON, MEASURE, NORTH, STEM
from treedist.sankey import mill_appendix_html
from treedist.schema import AO, DEST, VOL
from treedist.workorders import Facts, measures, sites, sweref99tm


def test_wgs84_becomes_sweref99tm_as_lantmateriet_computes_it():
    # Reference values from PROJ (EPSG:4326 to EPSG:3006).
    north, east = sweref99tm(59.3293, 18.0686)
    assert north == pytest.approx(6580743.008, abs=0.01) and east == pytest.approx(674571.866, abs=0.01)
    north, east = sweref99tm(60.0, 15.0)
    assert east == pytest.approx(500000.0, abs=0.01)


def test_positions_are_taken_as_given_or_converted_and_missing_ones_left_out():
    frame = pd.DataFrame({AO: ["A", "B", "C"], LAT: ["59,3293", None, None], LON: ["18.0686", None, None],
                          NORTH: [None, "7000000", None], EAST: [None, "600000", None]})
    placed = sites(frame).set_index(AO)
    assert list(placed.index) == ["A", "B"]
    assert placed.loc["A", NORTH] == pytest.approx(6580743.008, abs=0.01)
    assert placed.loc["B", EAST] == 600000


def facts():
    return Facts(
        sites(pd.DataFrame({AO: ["A", "B"], LAT: ["64.1", "64.4"], LON: ["19.5", "20.1"]})),
        measures(pd.DataFrame({AO: ["A", "A", "B"], MEASURE: ["slutavverkning", "gallring", "slutavverkning"],
                               STEM: ["0,45", "0.12", "0.5"], VOL: ["900", "300", None]})),
    )


def test_the_appendix_shows_where_the_work_orders_are(mixed):  # noqa: F811
    page = mill_appendix_html(mixed, mixed.invoice[DEST].iloc[0], facts=facts())
    assert page.count('stroke-width="1.2"><title>') == 2  # one point per located work order
    assert "Var de 2 arbetsordrar ligger" in page and "1 arbetsorder saknar läge i källan" in page
    assert "km</text>" in page and ">N</text>" in page


def test_a_work_order_with_measures_of_very_different_mean_stem_is_marked(mixed):  # noqa: F811
    page = mill_appendix_html(mixed, mixed.invoice[DEST].iloc[0], facts=facts())
    assert "Åtgärder och medelstam" in page and '<td class="flag">0,45</td>' in page and '<td class="flag">0,12</td>' in page
    assert "<td>0,50</td>" in page
    assert "1 av dem har flera åtgärder, och i 1 av dessa" in page


def test_a_run_reads_positions_and_measures_into_the_appendix(tmp_path):
    work_orders = pd.read_csv(f"{DEMO}/arbetsordrar.csv", dtype=str)
    work_orders[LAT] = [f"{63 + i * 0.01:.4f}" for i in range(len(work_orders))]
    work_orders[LON] = "18.5"
    places = tmp_path / "arbetsordrar.csv"
    work_orders.to_csv(places, index=False)
    held = tmp_path / "atgarder.csv"
    pd.DataFrame({AO: work_orders[AO], MEASURE: "gallring", STEM: "0.15"}).to_csv(held, index=False)
    out = demo_run(tmp_path, "lage", False, "--arbetsordrar", str(places), "--atgarder", str(held))
    pages = [p.read_text(encoding="utf-8") for p in (out / "bilagor").glob("*.html")]
    assert pages and all('class="map"' in page and "Åtgärder och medelstam" in page for page in pages)
    assert PERIOD in pages[0]


def test_check_warns_when_latitude_and_longitude_look_swapped():
    from treedist.adapters import Inputs

    frame = pd.DataFrame({AO: ["A"], LAT: ["18.07"], LON: ["59.33"]})
    inputs = Inputs(pd.DataFrame(), pd.DataFrame(), None, None, set(), Facts(sites(frame)))
    messages = [str(f) for f in _places(frame, inputs)]
    assert any("latitud" in m and "omkastad" in m for m in messages)
