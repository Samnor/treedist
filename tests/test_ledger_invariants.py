"""What the ledger must keep true from month to month, also where the data is awkward.

Late harvester data is counted off the stock by the gross volume that left beyond it, and moves nothing that was
invoiced; volume delivered beyond a closed work order's stock never disappears unseen; a credit never invents harvested
wood; and a reversal's id or destination never changes where its volume is credited when the work order's invoices say
where it came from.
"""

from dataclasses import replace

import pandas as pd
import pytest
from conftest import MILL, checked_deliveries, harvest_frame

from treedist.core.allocate import BrokenAssumption, close_month
from treedist.core.ledger import Ledger
from treedist.schema import BRUTTO, DIA, VOL

COLUMNS = ["leveransnummer", "avtalsobjekt", "handelssortiment", "volym_m3fub", "brutto_m3fub", "mottagningsplats"]
OWN = [("X", "TALL", "20", "400", 10.0)]


def loads(period, rows, cfg):
    """rows: (load id, ao, sortiment, net, gross, destination)"""
    frame = pd.DataFrame(rows, columns=COLUMNS).astype(str) if rows else pd.DataFrame(columns=COLUMNS)
    # The wood was produced for the harvest's mottagningsplats, wherever it was measured.
    frame = frame.assign(leveransdatum=f"{period}-20", matmetod="stockmatning", producerat_for_mottagningsplats=MILL)
    return checked_deliveries(frame, period)


def month(ledger, period, harvest, deliveries, cfg, closed=()):
    return close_month(ledger, harvest_frame(period, harvest), loads(period, deliveries, cfg), period, set(closed), cfg)


def billed_per_class(*steps):
    frames = [f for s in steps for f in (s.allocation, s.credits) if len(f)]
    return pd.concat(frames).groupby(DIA)[VOL].sum().round(9).to_dict()


def test_late_harvester_data_takes_the_gross_volume_that_left_beyond_the_stock(cfg):
    first = month(Ledger.empty(), "2026-01", OWN, [("L1", "X", "TALL", 95.0, 100.0, "S")], cfg)
    # 10 of the 100 that left were in the stock; the other 90 left beyond it, 85.5 of them invoiced.
    assert first.ledger.deficit[BRUTTO].sum() == pytest.approx(90.0)
    assert first.ledger.deficit[VOL].sum() == pytest.approx(85.5)
    second = month(first.ledger, "2026-02", [("X", "TALL", "30", "400", 200.0)], [], cfg)
    assert second.allocation.empty and second.credits.empty
    assert billed_per_class(first, second) == pytest.approx({"20": 95.0})
    assert second.ledger.deficit.empty
    stock = second.ledger.stock
    assert stock.loc[stock["avtalsobjekt"] == "X", VOL].sum() == pytest.approx(110.0)


def test_closing_a_work_order_records_the_volume_delivered_beyond_its_stock(cfg):
    first = month(Ledger.empty(), "2026-01", OWN, [("L1", "X", "TALL", 40.0, 40.0, "S")], cfg, closed={"X"})
    step = month(first.ledger, "2026-02", [], [], cfg)
    row = step.reconciliation.set_index("avtalsobjekt").loc["X"]
    assert row["avskrivet_underskott"] == pytest.approx(30.0)
    assert step.ledger.deficit.empty and step.ledger.stock.empty


def test_a_credit_puts_no_wood_in_a_stock_the_harvester_never_reported(cfg):
    """A ledger from a version that borrowed distributions can hold invoiced volume without harvester data."""
    first = month(Ledger.empty(), "2026-01", OWN, [("L1", "X", "TALL", 40.0, 40.0, "S")], cfg, closed={"X"})
    older = replace(first.ledger, history=first.ledger.history.iloc[0:0])
    second = month(older, "2026-02", [], [("L1", "X", "TALL", -40.0, -40.0, "S")], cfg)
    assert second.credits[VOL].sum() == pytest.approx(-40.0)
    assert not (second.ledger.stock["avtalsobjekt"] == "X").any()


def test_a_reversal_under_another_number_than_its_load_stops_the_month(cfg):
    # A correction has the leveransnummer of the load it reverses; under a number of its own it reverses nothing known.
    harvest = [("X", "TALL", "20", "400", 100.0)]
    rows = [("L1", "X", "TALL", 40.0, 40.0, "S"), ("L9", "X", "TALL", -40.0, -40.0, "S")]
    with pytest.raises(BrokenAssumption, match="leveransnummer som inte finns i liggaren, 40.0 m3fub: L9"):
        month(Ledger.empty(), "2026-01", harvest, rows, cfg)


def test_a_reversal_at_another_destination_than_its_load_stops_the_month(cfg):
    # A correction has the mottagningsplats of the load it reverses; at another one nothing was invoiced to credit.
    harvest = [("X", "TALL", "20", "400", 100.0)]
    first = month(Ledger.empty(), "2026-01", harvest, [("L1", "X", "TALL", 40.0, 40.0, "S")], cfg)
    with pytest.raises(BrokenAssumption, match="mer volym än som fakturerats .* X TALL till T 40.0"):
        month(first.ledger, "2026-02", [], [("L1", "X", "TALL", -40.0, -40.0, "T")], cfg)


def test_a_reversed_load_returns_its_wood_to_the_pile_it_was_produced_for(cfg):
    # Cut for MILL and measured at T: reversed, the wood is back in MILL's pile, where the next load for MILL finds it.
    harvest = [("X", "TALL", "20", "400", 100.0)]
    first = month(Ledger.empty(), "2026-01", harvest, [("L1", "X", "TALL", 40.0, 40.0, "T")], cfg)
    second = month(first.ledger, "2026-02", [], [("L1", "X", "TALL", -40.0, -40.0, "T")], cfg)
    assert second.ledger.stock.groupby("producerat_for_mottagningsplats")[VOL].sum().to_dict() == pytest.approx({MILL: 100.0})
