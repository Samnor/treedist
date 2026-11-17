"""What the work orders hold: the measures, optional, read only for the appendix and never by the method."""

import pandas as pd
from test_appendix import DEMO, PERIOD, demo_run
from test_sankey import mixed  # noqa: F401  the fixture

from treedist.bilaga_html import mill_appendix_html
from treedist.contract import MEASURE, STEM, TABLES
from treedist.schema import AO, DEST, VOL
from treedist.workorders import Facts, measures


def facts():
    return Facts(measures(pd.DataFrame({AO: ["A", "A", "B"], MEASURE: ["slutavverkning", "gallring", "slutavverkning"],
                                        STEM: ["0,45", "0.12", "0.5"], VOL: ["900", "300", None]})))


def test_a_work_order_with_measures_of_very_different_mean_stem_is_marked(mixed):  # noqa: F811
    page = mill_appendix_html(mixed, mixed.invoice[DEST].iloc[0], facts=facts())
    assert "Avverkningsformer och medelstam" in page and '<td class="flag">0,45</td>' in page and '<td class="flag">0,12</td>' in page
    assert "<td>0,50</td>" in page
    assert "Underlaget har avverkningsformer för 2 avtalsobjekt. Av dem har 1 flera avverkningsformer, och för A är" in page


def test_a_run_reads_the_measures_into_the_appendix(tmp_path):
    work_orders = pd.read_csv(f"{DEMO}/avtalsobjekt_{PERIOD}.csv", dtype=str)
    held = tmp_path / "atgarder.csv"
    pd.DataFrame({AO: work_orders[AO], MEASURE: "gallring", STEM: "0.15"}).to_csv(held, index=False)
    out = demo_run(tmp_path, "avverkningsformer", "--avverkningsformer", str(held))
    pages = [p.read_text(encoding="utf-8") for p in (out / "bilagor").glob("*.html")]
    assert pages and all("Avverkningsformer och medelstam</h3>" in page for page in pages)
    assert PERIOD in pages[0]


def test_the_appendix_has_no_map_and_the_contract_no_positions(tmp_path, mixed):  # noqa: F811
    page = mill_appendix_html(mixed, mixed.invoice[DEST].iloc[0], facts=facts())
    assert 'class="map"' not in page and "Kartan" not in page and "läge" not in page
    columns = {column.name for table in TABLES.values() for column in table.columns}
    assert not columns & {"latitud", "longitud", "nord_sweref99tm", "ost_sweref99tm", "grupp"}
    # A source that still has the positions is read as before; the columns are just not used.
    work_orders = pd.read_csv(f"{DEMO}/avtalsobjekt_{PERIOD}.csv", dtype=str).assign(latitud="63.5", longitud="18.5")
    places = tmp_path / "avtalsobjekt.csv"
    work_orders.to_csv(places, index=False)
    out = demo_run(tmp_path, "lage", "--avtalsobjekt", str(places))
    assert all('class="map"' not in p.read_text(encoding="utf-8") for p in (out / "bilagor").glob("*.html"))
