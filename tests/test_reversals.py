"""Negative delivery rows: loads reversed in the same month, or after they were invoiced."""

import pandas as pd
import pytest
from conftest import harvest_frame

from treedist.core.allocate import close_month
from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.schema import DIA, VOL, validate_deliveries


def loads(period, rows, cfg):
    """rows: (load id, ao, sortiment, net, gross)"""
    df = pd.DataFrame(rows, columns=["leverans_id", "arbetsorder", "handelssortiment", "volym_m3fub", "brutto_m3fub"])
    return validate_deliveries(df.assign(leveransdatum=f"{period}-20", matmetod="stockmatning"), period, cfg)


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


def test_a_reversed_provisional_load_settles_the_deficit_instead_of_the_stock(cfg):
    pool = [(f"D{i}", "TALL", "20", "340", 100.0) for i in range(5)]
    first = close_month(
        Ledger.empty(), harvest_frame("2026-01", pool), loads("2026-01", [("L1", "NY", "TALL", 10.0, 10.0)], cfg),
        "2026-01", set(), cfg,
    )
    assert first.ledger.deficit[VOL].sum() == pytest.approx(10.0)
    second = close_month(
        first.ledger, harvest_frame("2026-02", []), loads("2026-02", [("L1", "NY", "TALL", -10.0, -10.0)], cfg),
        "2026-02", set(), cfg,
    )
    assert second.ledger.deficit[VOL].sum() == pytest.approx(0.0, abs=1e-9)
    assert second.credits.groupby(DIA)[VOL].sum().to_dict() == pytest.approx({"20": -10.0})
    assert not (second.ledger.stock["arbetsorder"] == "NY").any()


def test_more_reversed_than_was_invoiced_is_credited_on_the_unknown_class(cfg):
    step = close_month(
        Ledger.empty(), harvest_frame("2026-01", HARVEST), loads("2026-01", [("L9", "A", "TALL", -5.0, -5.0)], cfg),
        "2026-01", set(), cfg,
    )
    assert step.credits.groupby(DIA)[VOL].sum().to_dict() == pytest.approx({"OKÄND": -5.0})


def test_the_invoice_bills_the_measurement_including_credits(cfg, prices):
    first = run_month(
        Ledger.empty(), harvest_frame("2026-01", HARVEST), loads("2026-01", [("L1", "A", "TALL", 50.0, 51.0)], cfg),
        prices, "2026-01", set(), cfg,
    )
    second = run_month(
        first.step.ledger, harvest_frame("2026-02", []),
        loads("2026-02", [("L1", "A", "TALL", -50.0, -51.0), ("L2", "A", "TALL", 30.0, 30.0)], cfg),
        prices, "2026-02", set(), cfg,
    )
    by_type = second.invoice.groupby("radtyp")["volym_m3fub"].sum()
    assert by_type["KREDITERING"] == pytest.approx(-50.0)
    assert by_type["LEVERANS"] == pytest.approx(30.0)


def test_net_and_gross_must_have_the_same_sign(cfg):
    with pytest.raises(ValueError, match="olika tecken"):
        loads("2026-01", [("L1", "A", "TALL", -5.0, 5.0)], cfg)


def test_a_ledger_saved_before_credits_still_loads(tmp_path, cfg):
    step = close_month(Ledger.empty(), harvest_frame("2026-01", HARVEST), loads("2026-01", [], cfg), "2026-01", set(), cfg)
    folder = step.ledger.save(tmp_path)
    (folder / "fakturerat.csv").unlink()
    assert Ledger.load(tmp_path, "2026-01").billed.empty
