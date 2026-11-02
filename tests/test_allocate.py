from dataclasses import replace

import pandas as pd
import pytest
from conftest import delivery_frame, harvest_frame

from treedist.allocate import close_month
from treedist.ledger import Ledger
from treedist.schema import DIA, SORT, TIER, VOL, validate_harvest

NO_HARVEST = [("X", "X", "14", "340", 0.0)]


def by_class(step):
    return step.allocation.groupby(DIA)[VOL].sum().to_dict()


def test_delivered_wood_keeps_the_distribution_of_an_earlier_month(cfg):
    january = harvest_frame("2026-01", [("A", "TALL", "14", "340", 75.0), ("A", "TALL", "20", "340", 25.0)])
    first = close_month(Ledger.empty(), january, delivery_frame("2026-01", [], cfg), "2026-01", set(), cfg)
    assert first.allocation.empty

    february = harvest_frame("2026-02", [("B", "TALL", "30", "340", 100.0)])
    second = close_month(
        first.ledger, february, delivery_frame("2026-02", [("A", "TALL", 40.0)], cfg), "2026-02", set(), cfg
    )
    assert by_class(second) == pytest.approx({"14": 30.0, "20": 10.0})
    assert set(second.allocation[TIER]) == {"S1"}


def test_allocation_preserves_delivered_volume_and_ledger_balances(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 60.0), ("A", "TALL", "20", "370", 40.0)])
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 30.0)], cfg), "2026-01", set(), cfg)
    assert step.allocation[VOL].sum() == pytest.approx(30.0)
    assert step.ledger.stock[VOL].sum() == pytest.approx(70.0)
    assert step.ledger.history[VOL].sum() == pytest.approx(100.0)


def test_calibration_reduces_harvested_volume(cfg):
    calibrated = replace(cfg, harvester_bias=0.01, handling_loss=0.02)
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0)])
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [], cfg), "2026-01", set(), calibrated)
    assert step.ledger.stock[VOL].sum() == pytest.approx(100 * 0.99 * 0.98)


def test_small_overdelivery_within_tolerance_is_fully_s1(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0)])
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 102.0)], cfg), "2026-01", set(), cfg)
    assert set(step.allocation[TIER]) == {"S1"}
    assert step.allocation[VOL].sum() == pytest.approx(102.0)
    assert step.ledger.deficit.empty


def test_overdelivery_beyond_tolerance_falls_back_on_work_order_history(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 80.0), ("A", "TALL", "20", "340", 20.0)])
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 150.0)], cfg), "2026-01", set(), cfg)
    tiers = step.allocation.groupby(TIER)[VOL].sum()
    assert tiers["S1"] == pytest.approx(100.0)
    assert tiers["S2"] == pytest.approx(50.0)
    assert step.ledger.deficit[VOL].sum() == pytest.approx(50.0)


def test_work_order_without_harvester_data_uses_assortment_pool(cfg):
    harvest = harvest_frame("2026-01", [("B", "TALL", "20", "340", 100.0)])
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 10.0)], cfg), "2026-01", set(), cfg)
    assert set(step.allocation[TIER]) == {"S3"}
    assert by_class(step) == pytest.approx({"20": 10.0})


def test_assortment_without_any_data_goes_on_unknown_class(cfg):
    harvest = harvest_frame("2026-01", [("B", "GRAN", "20", "340", 100.0)])
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 10.0)], cfg), "2026-01", set(), cfg)
    assert set(step.allocation[TIER]) == {"S4"}
    assert by_class(step) == pytest.approx({"OKÄND": 10.0})


def test_late_harvester_data_corrects_provisional_distribution(cfg):
    january = harvest_frame("2026-01", [("B", "TALL", "20", "340", 100.0)])
    first = close_month(Ledger.empty(), january, delivery_frame("2026-01", [("A", "TALL", 10.0)], cfg), "2026-01", set(), cfg)
    assert first.ledger.deficit[VOL].sum() == pytest.approx(10.0)

    february = harvest_frame("2026-02", [("A", "TALL", "30", "340", 50.0)])
    second = close_month(first.ledger, february, delivery_frame("2026-02", [], cfg), "2026-02", set(), cfg)

    moved = second.corrections.set_index(DIA)[VOL]
    assert moved["30"] == pytest.approx(10.0)
    assert moved["20"] == pytest.approx(-10.0)
    assert moved.sum() == pytest.approx(0.0)
    assert second.ledger.deficit.empty
    stock_a = second.ledger.stock[second.ledger.stock["arbetsorder"] == "A"][VOL].sum()
    assert stock_a == pytest.approx(40.0)


def test_closing_a_work_order_writes_off_stock(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0)])
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 90.0)], cfg), "2026-01", {"A"}, cfg)
    assert step.reconciliation["avskrivet"].sum() == pytest.approx(10.0)
    assert step.ledger.stock.empty


def test_fifo_draws_oldest_harvest_month_first(cfg):
    fifo = replace(cfg, draw_policy="fifo")
    january = harvest_frame("2026-01", [("A", "TALL", "14", "340", 50.0)])
    first = close_month(Ledger.empty(), january, delivery_frame("2026-01", [], cfg), "2026-01", set(), fifo)
    february = harvest_frame("2026-02", [("A", "TALL", "20", "340", 50.0)])
    second = close_month(first.ledger, february, delivery_frame("2026-02", [("A", "TALL", 40.0)], cfg), "2026-02", set(), fifo)
    assert by_class(second) == pytest.approx({"14": 40.0})


def test_month_cannot_be_closed_twice(cfg):
    step = close_month(Ledger.empty(), harvest_frame("2026-01", NO_HARVEST), delivery_frame("2026-01", [], cfg), "2026-01", set(), cfg)
    with pytest.raises(ValueError, match="redan stängd"):
        close_month(step.ledger, harvest_frame("2026-01", NO_HARVEST), delivery_frame("2026-01", [], cfg), "2026-01", set(), cfg)


def test_assortment_without_classes_is_supported(cfg):
    df = pd.DataFrame(
        {"arbetsorder": ["A"], "handelssortiment": ["MASSA"], "diametergrupp": [None], "langdgrupp": [""], "volym_m3fub": [10.0]}
    )
    step = close_month(
        Ledger.empty(), validate_harvest(df, "2026-01"), delivery_frame("2026-01", [("A", "MASSA", 5.0)], cfg), "2026-01", set(), cfg
    )
    assert step.allocation.loc[0, SORT] == "MASSA"
    assert step.allocation.loc[0, DIA] == "-"
