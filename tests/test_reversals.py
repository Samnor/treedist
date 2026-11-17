"""Negative delivery rows: loads reversed in the same month, or after they were invoiced."""


import pandas as pd
import pytest
from conftest import checked_deliveries, harvest_frame

from treedist.core.allocate import BrokenAssumption, close_month
from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.schema import DIA, VOL


def loads(period, rows, cfg):
    """rows: (load id, ao, sortiment, net, gross)"""
    df = pd.DataFrame(rows, columns=["leveransnummer", "avtalsobjekt", "handelssortiment", "volym_m3fub", "brutto_m3fub"])
    return checked_deliveries(df.assign(leveransdatum=f"{period}-20", matmetod="stockmatning"), period)


def stock_of(step):
    return step.ledger.stock.groupby(DIA)[VOL].sum().to_dict()


HARVEST = [("A", "TALL", "14", "340", 60.0), ("A", "TALL", "24", "340", 40.0)]


def test_a_load_reversed_in_its_own_month_is_not_delivered(cfg):
    deliveries = loads("2026-01", [("L1", "A", "TALL", 45.0, 45.0), ("L1", "A", "TALL", -45.0, -45.0)], cfg)
    step = close_month(Ledger.empty(), harvest_frame("2026-01", HARVEST), deliveries, "2026-01", set(), cfg)
    assert step.allocation[VOL].sum() == pytest.approx(0.0)
    assert step.credits.empty
    assert step.ledger.stock[VOL].sum() == pytest.approx(100.0)


def test_a_remeasured_load_delivers_the_new_volume(cfg):
    rows = [("L1", "A", "TALL", 45.0, 45.0), ("L1", "A", "TALL", -45.0, -45.0), ("L1", "A", "TALL", 40.0, 40.0)]
    step = close_month(Ledger.empty(), harvest_frame("2026-01", HARVEST), loads("2026-01", rows, cfg), "2026-01", set(), cfg)
    assert step.allocation[VOL].sum() == pytest.approx(40.0)
    assert step.ledger.stock[VOL].sum() == pytest.approx(60.0)


def test_a_load_reversed_a_month_later_is_credited_as_invoiced_and_returns_to_stock(cfg):
    first = close_month(
        Ledger.empty(), harvest_frame("2026-01", HARVEST), loads("2026-01", [("L1", "A", "TALL", 50.0, 50.0)], cfg),
        "2026-01", set(), cfg,
    )
    invoiced = first.allocation.groupby(DIA)[VOL].sum()
    second = close_month(
        first.ledger, harvest_frame("2026-02", []), loads("2026-02", [("L1", "A", "TALL", -50.0, -50.0)], cfg),
        "2026-02", set(), cfg,
    )
    credited = second.credits.groupby(DIA)[VOL].sum()
    assert credited.to_dict() == pytest.approx((-invoiced).to_dict())
    assert stock_of(second) == pytest.approx({"14": 60.0, "24": 40.0})
    assert second.ledger.billed[VOL].abs().sum() == pytest.approx(0.0, abs=1e-6)
    assert second.reconciliation["levererat"].sum() == pytest.approx(-50.0)


def test_the_invoice_bills_the_measurement_including_credits(cfg):
    first = run_month(
        Ledger.empty(), harvest_frame("2026-01", HARVEST), loads("2026-01", [("L1", "A", "TALL", 50.0, 51.0)], cfg),
        "2026-01", set(), cfg,
    )
    second = run_month(
        first.step.ledger, harvest_frame("2026-02", []),
        loads("2026-02", [("L1", "A", "TALL", -50.0, -51.0), ("L2", "A", "TALL", 30.0, 30.0)], cfg),
        "2026-02", set(), cfg,
    )
    by_type = second.invoice.groupby("radtyp")["volym_m3fub"].sum()
    assert by_type["KREDITERING"] == pytest.approx(-50.0)
    assert by_type["LEVERANS"] == pytest.approx(30.0)


def test_net_and_gross_must_have_the_same_sign(cfg):
    with pytest.raises(ValueError, match="olika tecken"):
        loads("2026-01", [("L1", "A", "TALL", -5.0, 5.0)], cfg)


def test_a_load_reversed_later_is_credited_as_its_own_month_was_invoiced(tmp_path, cfg):
    jan = close_month(Ledger.empty(), harvest_frame("2026-01", [("A", "TALL", "14", "340", 50.0)]),
                      loads("2026-01", [("L1", "A", "TALL", 50.0, 50.0)], cfg), "2026-01", set(), cfg)
    jan.ledger.save(tmp_path)
    feb = close_month(Ledger.load(tmp_path, "2026-01"), harvest_frame("2026-02", [("A", "TALL", "30", "340", 50.0)]),
                      loads("2026-02", [("L2", "A", "TALL", 50.0, 50.0)], cfg), "2026-02", set(), cfg)
    feb.ledger.save(tmp_path)
    reversal = loads("2026-03", [("L1", "A", "TALL", -50.0, -50.0)], cfg)

    mar = close_month(Ledger.load(tmp_path, "2026-02"), harvest_frame("2026-03", []), reversal, "2026-03", set(), cfg)
    assert mar.credits.groupby(DIA)[VOL].sum().to_dict() == pytest.approx({"14": -50.0})
    assert stock_of(mar) == pytest.approx({"14": 50.0})
    assert mar.ledger.billed.groupby(DIA)[VOL].sum().to_dict() == pytest.approx({"30": 50.0})


def test_a_reversed_load_beyond_the_stock_settles_the_deficit_before_the_stock(cfg):
    # NY harvested 4 and delivered 10: 4 from its stock and 6 beyond it, as an estimate.
    first = close_month(
        Ledger.empty(), harvest_frame("2026-01", [("NY", "TALL", "20", "340", 4.0)]),
        loads("2026-01", [("L1", "NY", "TALL", 10.0, 10.0)], cfg), "2026-01", set(), cfg,
    )
    assert first.ledger.deficit[VOL].sum() == pytest.approx(6.0)
    second = close_month(
        first.ledger, harvest_frame("2026-02", []), loads("2026-02", [("L1", "NY", "TALL", -10.0, -10.0)], cfg),
        "2026-02", set(), cfg,
    )
    assert second.ledger.deficit[VOL].sum() == pytest.approx(0.0, abs=1e-9)
    assert second.credits.groupby(DIA)[VOL].sum().to_dict() == pytest.approx({"20": -10.0})
    assert stock_of(second) == pytest.approx({"20": 4.0})


def test_more_reversed_than_its_load_was_invoiced_stops_the_month(cfg):
    first = close_month(Ledger.empty(), harvest_frame("2026-01", HARVEST), loads("2026-01", [("L1", "A", "TALL", 50.0, 50.0)], cfg),
                        "2026-01", set(), cfg)
    with pytest.raises(BrokenAssumption, match="1 vända lass har mer volym än som fakturerats för avtalsobjektet och "
                                               "sortimentet, 5.0 m3fub: A TALL till SAG 5.0"):
        close_month(first.ledger, harvest_frame("2026-02", []), loads("2026-02", [("L1", "A", "TALL", -55.0, -55.0)], cfg),
                    "2026-02", set(), cfg)


def test_a_reversal_whose_leveransnummer_the_ledger_does_not_hold_stops_the_month(cfg):
    # A correction carries the number of the load it reverses. L9 was never delivered, although A has invoiced volume.
    first = close_month(Ledger.empty(), harvest_frame("2026-01", HARVEST), loads("2026-01", [("L1", "A", "TALL", 50.0, 50.0)], cfg),
                        "2026-01", set(), cfg)
    with pytest.raises(BrokenAssumption, match=r"1 vända lass har ett leveransnummer som inte finns i liggaren, 5.0 m3fub: "
                                               r"L9 \(A\) 5.0"):
        close_month(first.ledger, harvest_frame("2026-02", []), loads("2026-02", [("L9", "A", "TALL", -5.0, -5.0)], cfg),
                    "2026-02", set(), cfg)


def remeasured(cfg, net, gross):
    """L1, invoiced in January as 48 net of 50 gross, is reversed in February and booked again under its number."""
    first = close_month(Ledger.empty(), harvest_frame("2026-01", HARVEST), loads("2026-01", [("L1", "A", "TALL", 48.0, 50.0)], cfg),
                        "2026-01", set(), cfg)
    rows = [("L1", "A", "TALL", -48.0, -50.0), ("L1", "A", "TALL", net, gross)]
    second = close_month(first.ledger, harvest_frame("2026-02", []), loads("2026-02", rows, cfg), "2026-02", set(), cfg)
    return first, second


def test_a_load_remeasured_to_a_lower_net_volume_is_credited_and_moves_no_wood(cfg):
    first, second = remeasured(cfg, 46.0, 50.0)
    invoiced = first.allocation.groupby(DIA)[VOL].sum()
    assert second.credits.groupby(DIA)[VOL].sum().to_dict() == pytest.approx((-invoiced * 2 / 48).to_dict())
    assert second.allocation.empty
    # The same wood left the landing: none of it comes back to the stock.
    assert stock_of(second) == pytest.approx(stock_of(first))


def test_a_load_remeasured_to_a_higher_net_volume_is_invoiced_and_moves_no_wood(cfg):
    first, second = remeasured(cfg, 50.0, 50.0)
    assert second.allocation[VOL].sum() == pytest.approx(2.0)
    assert set(second.allocation["sakerhetsklass"]) == {"S2"}
    assert second.credits.empty
    assert stock_of(second) == pytest.approx(stock_of(first))
    assert second.ledger.deficit.empty


def test_a_load_remeasured_to_less_wood_returns_the_gross_difference(cfg):
    first, second = remeasured(cfg, 43.0, 45.0)
    assert second.credits[VOL].sum() == pytest.approx(-5.0)
    assert sum(stock_of(second).values()) == pytest.approx(sum(stock_of(first).values()) + 5.0)


def test_late_harvester_data_does_not_change_what_an_earlier_month_invoiced(cfg):
    jan = close_month(Ledger.empty(), harvest_frame("2026-01", [("NY", "TALL", "20", "340", 4.0)]),
                      loads("2026-01", [("L1", "NY", "TALL", 10.0, 10.0)], cfg), "2026-01", set(), cfg)
    feb = close_month(jan.ledger, harvest_frame("2026-02", [("NY", "TALL", "30", "340", 20.0)]),
                      loads("2026-02", [("L2", "NY", "TALL", 10.0, 10.0)], cfg), "2026-02", set(), cfg)
    by_month = feb.ledger.billed.groupby(["period", DIA])[VOL].sum()
    assert by_month[by_month.abs() > 1e-9].to_dict() == pytest.approx({("2026-01", "20"): 10.0, ("2026-02", "30"): 10.0})
    # The 6 delivered beyond the stock in January left the late wood's stock, so they are not delivered twice.
    assert stock_of(feb) == pytest.approx({"30": 4.0})

    # A January load reversed in March is credited as January invoiced it, the estimate included.
    mar = close_month(feb.ledger, harvest_frame("2026-03", []),
                      loads("2026-03", [("L1", "NY", "TALL", -10.0, -10.0)], cfg), "2026-03", set(), cfg)
    assert mar.credits.groupby(DIA)[VOL].sum().to_dict() == pytest.approx({"20": -10.0})
    assert mar.ledger.stock[VOL].sum() == pytest.approx(14.0)
