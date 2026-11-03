from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from conftest import delivery_frame, harvest_frame

from treedist.core.allocate import close_month
from treedist.core.ledger import Ledger
from treedist.schema import DEST, DIA, SORT, TIER, VOL, WorkOrders, validate_harvest

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


def test_borrowed_distribution_draws_parts_of_donor_harvests(cfg):
    rows = [(f"B{i}", "TALL", str(14 + 2 * i), "340", 50.0) for i in range(6)]
    harvest = validate_harvest(
        pd.DataFrame(rows, columns=["arbetsorder", "handelssortiment", "diametergrupp", "langdgrupp", "volym_m3fub"])
        .assign(avverkningsdatum=["2026-01-02", "2026-01-20"] * 3),
        "2026-01",
    )
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 10.0)], cfg), "2026-01", set(), cfg)
    (component,) = step.components
    assert component.tier == "S3"
    assert component.donor_parts is not None and len(component.donor_parts) == 6
    assert np.isfinite(component.concentration)


def test_overdelivery_draws_a_part_of_the_work_orders_harvest(cfg):
    rows = [("A", "TALL", "14", "340", 50.0), ("A", "TALL", "26", "340", 50.0)]
    harvest = validate_harvest(
        pd.DataFrame(rows, columns=["arbetsorder", "handelssortiment", "diametergrupp", "langdgrupp", "volym_m3fub"])
        .assign(avverkningsdatum=["2026-01-02", "2026-01-20"]),
        "2026-01",
    )
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 150.0)], cfg), "2026-01", set(), cfg)
    (overdelivered,) = [c for c in step.components if c.tier == "S2"]
    assert overdelivered.mixture is not None and len(overdelivered.mixture) == 2


def reclassified(period, rows, cfg):
    """rows: (ao, measured assortment, produced assortment, volume)"""
    deliveries = delivery_frame(period, [(ao, measured, volume) for ao, measured, _, volume in rows], cfg)
    return deliveries.assign(producerat_handelssortiment=[produced for _, _, produced, _ in rows])


def test_reclassified_wood_leaves_the_produced_stock_and_is_billed_as_measured(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 75.0), ("A", "TALL", "20", "340", 25.0)])
    deliveries = reclassified("2026-01", [("A", "TALL", "TALL", 20.0), ("A", "MASSA", "TALL", 20.0)], cfg)
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)

    billed = step.allocation.groupby(SORT)[VOL].sum()
    assert billed.to_dict() == pytest.approx({"TALL": 20.0, "MASSA": 20.0})
    assert set(step.allocation[TIER]) == {"S1"}
    assert step.ledger.stock[VOL].sum() == pytest.approx(60.0)
    assert {c.sortiment for c in step.components} == {"TALL", "MASSA"}


def test_correction_of_reclassified_wood_lands_on_the_measured_assortment(cfg):
    january = harvest_frame("2026-01", [("B", "TALL", "20", "340", 100.0)])
    deliveries = reclassified("2026-01", [("A", "MASSA", "TALL", 10.0)], cfg)
    first = close_month(Ledger.empty(), january, deliveries, "2026-01", set(), cfg)
    assert set(first.ledger.deficit["fakturerat_handelssortiment"]) == {"MASSA"}

    february = harvest_frame("2026-02", [("A", "TALL", "30", "340", 50.0)])
    second = close_month(first.ledger, february, delivery_frame("2026-02", [], cfg), "2026-02", set(), cfg)
    assert set(second.corrections[SORT]) == {"MASSA"}
    assert second.corrections.set_index(DIA)[VOL]["30"] == pytest.approx(10.0)


def test_closing_a_work_order_writes_off_stock(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0)])
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 90.0)], cfg), "2026-01", {"A"}, cfg)
    assert step.reconciliation["avskrivet"].sum() == pytest.approx(10.0)
    assert step.ledger.stock.empty


def test_wood_cannot_leave_before_it_was_harvested(cfg):
    df = pd.DataFrame(
        {
            "arbetsorder": ["A", "A"],
            "handelssortiment": ["TALL", "TALL"],
            "diametergrupp": ["14", "20"],
            "langdgrupp": ["340", "340"],
            "volym_m3fub": [100.0, 100.0],
            "avverkningsdatum": ["2026-01-02", "2026-01-25"],
        }
    )
    harvest = validate_harvest(df, "2026-01")
    deliveries = delivery_frame("2026-01", [("A", "TALL", 40.0)], cfg)
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    assert by_class(step) == pytest.approx({"14": 40.0})


def test_trucks_that_follow_the_harvester_take_the_oldest_wood(cfg):
    df = pd.DataFrame(
        {
            "arbetsorder": ["A"] * 3,
            "handelssortiment": ["TALL"] * 3,
            "diametergrupp": ["14", "20", "26"],
            "langdgrupp": ["340"] * 3,
            "volym_m3fub": [100.0] * 3,
            "avverkningsdatum": ["2026-01-02", "2026-01-05", "2026-01-20"],
        }
    )
    harvest = validate_harvest(df, "2026-01")
    deliveries = delivery_frame("2026-01", [("A", "TALL", 140.0)], cfg)
    first = 100.0 * cfg.calibration
    overlapping = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    assert by_class(overlapping) == pytest.approx({"14": first, "20": 140.0 - first})
    pro_rata = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), replace(cfg, overlap_fifo=False))
    assert by_class(pro_rata) == pytest.approx({"14": 70.0, "20": 70.0})


def test_gross_leaves_stock_and_net_is_allocated(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0)])
    deliveries = delivery_frame("2026-01", [("A", "TALL", 18.0)], cfg).assign(brutto_m3fub=20.0)
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    assert step.allocation[VOL].sum() == pytest.approx(18.0)
    assert step.ledger.stock[VOL].sum() == pytest.approx(80.0)


def test_groups_choose_comparable_work_orders(cfg):
    rows = [(f"N{i}", "TALL", "14", "340", 100.0) for i in range(5)]
    rows += [(f"S{i}", "TALL", "30", "340", 100.0) for i in range(5)]
    groups = {**{f"N{i}": "norra" for i in range(5)}, **{f"S{i}": "sodra" for i in range(5)}, "NY": "sodra"}
    deliveries = delivery_frame("2026-01", [("NY", "TALL", 10.0)], cfg)
    known = WorkOrders(groups=groups)
    step = close_month(Ledger.empty(), harvest_frame("2026-01", rows), deliveries, "2026-01", set(), cfg, known)
    assert by_class(step)["30"] == pytest.approx(10.0 * 4 / 5)


def test_destination_chooses_comparable_work_orders(cfg):
    rows = [(f"K{i}", "TALL", "14", "340", 100.0) for i in range(5)]
    rows += [(f"G{i}", "TALL", "30", "340", 100.0) for i in range(5)]
    planned = {**{f"K{i}": "KLEN" for i in range(5)}, **{f"G{i}": "GROV" for i in range(5)}, "NY": "GROV"}
    known = WorkOrders(destinations=planned)
    deliveries = delivery_frame("2026-01", [("NY", "TALL", 10.0)], cfg, work_orders=known)
    step = close_month(Ledger.empty(), harvest_frame("2026-01", rows), deliveries, "2026-01", set(), cfg, known)
    assert by_class(step)["30"] == pytest.approx(10.0 * 16 / 17)
    assert set(step.allocation[DEST]) == {"GROV"}


def test_other_assortment_of_the_work_order_chooses_donors(cfg):
    rows = []
    for i, diameter in enumerate(["14", "20", "26", "32", "38", "14", "20", "26", "32", "38"]):
        rows.append((f"D{i}", "TALL", diameter, "340", 100.0))
        rows.append((f"D{i}", "GRAN", diameter, "340", 100.0))
    rows.append(("NY", "GRAN", "32", "340", 100.0))
    deliveries = delivery_frame("2026-01", [("NY", "TALL", 10.0)], cfg)
    step = close_month(Ledger.empty(), harvest_frame("2026-01", rows), deliveries, "2026-01", set(), cfg)
    assert by_class(step)["32"] == pytest.approx(10.0, abs=0.1)


def test_one_work_order_split_between_destinations_shares_its_stock(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 60.0), ("A", "TALL", "20", "340", 40.0)])
    deliveries = delivery_frame("2026-01", [("A", "TALL", 30.0), ("A", "TALL", 10.0)], cfg)
    deliveries[DEST] = ["X", "Y"]
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    per_destination = step.allocation.groupby(DEST)[VOL].sum()
    assert per_destination["X"] == pytest.approx(30.0)
    assert per_destination["Y"] == pytest.approx(10.0)
    assert step.ledger.stock[VOL].sum() == pytest.approx(60.0)


def test_correction_follows_the_destination_of_the_delivery(cfg):
    january = harvest_frame("2026-01", [("B", "TALL", "20", "340", 100.0)])
    deliveries = delivery_frame("2026-01", [("A", "TALL", 10.0)], cfg)
    deliveries[DEST] = "X"
    first = close_month(Ledger.empty(), january, deliveries, "2026-01", set(), cfg)
    february = harvest_frame("2026-02", [("A", "TALL", "30", "340", 50.0)])
    second = close_month(first.ledger, february, delivery_frame("2026-02", [], cfg), "2026-02", set(), cfg)
    assert set(second.corrections[DEST]) == {"X"}


def test_fully_rejected_delivery_only_empties_stock(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0)])
    deliveries = delivery_frame("2026-01", [("A", "TALL", 0.0)], cfg).assign(brutto_m3fub=20.0)
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    assert step.allocation.empty
    assert step.ledger.stock[VOL].sum() == pytest.approx(80.0)


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
