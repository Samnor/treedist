from dataclasses import replace

import pandas as pd
import pytest
from conftest import checked_deliveries, checked_harvest, delivery_frame, harvest_frame

from treedist.core.allocate import BrokenAssumption, close_month
from treedist.core.ledger import Ledger
from treedist.schema import BRUTTO, DEST, DIA, PRODUCED_FOR, SORT, TIER, VOL

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


def test_overdelivery_falls_back_on_work_order_history(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 80.0), ("A", "TALL", "20", "340", 20.0)])
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 150.0)], cfg), "2026-01", set(), cfg)
    tiers = step.allocation.groupby(TIER)[VOL].sum()
    assert tiers["S1"] == pytest.approx(100.0)
    assert tiers["S2"] == pytest.approx(50.0)
    assert step.ledger.deficit[VOL].sum() == pytest.approx(50.0)


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


def test_finished_transport_is_written_off_after_a_month_without_deliveries(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0)])
    # The table says the transport is finished, but the month still measured a delivery: the stock waits.
    january = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 90.0)], cfg), "2026-01", {"A"},
                          cfg)
    assert january.closed == frozenset() and january.ledger.transport_done == {"A"}
    assert january.ledger.stock[VOL].sum() == pytest.approx(10.0)
    # A delivery measured late, the month after, still takes the stock.
    february = close_month(january.ledger, harvest_frame("2026-02", []), delivery_frame("2026-02", [("A", "TALL", 4.0)], cfg),
                           "2026-02", set(), cfg)
    assert set(february.allocation[TIER]) == {"S1"} and february.closed == frozenset()
    # A month without deliveries writes the rest off, even when that month's table no longer lists the avtalsobjekt.
    march = close_month(february.ledger, harvest_frame("2026-03", []), delivery_frame("2026-03", [], cfg), "2026-03", set(),
                        cfg)
    assert march.closed == {"A"} and march.ledger.transport_done == frozenset()
    assert march.reconciliation["avskrivet"].sum() == pytest.approx(6.0)
    assert march.ledger.stock.empty


def test_wood_cannot_leave_before_it_was_harvested(cfg):
    df = pd.DataFrame(
        {
            "avtalsobjekt": ["A", "A"],
            "producerat_handelssortiment": ["TALL", "TALL"],
            "diameterklass": ["14", "20"],
            "langdklass": ["340", "340"],
            "volym_m3fub": [100.0, 100.0],
            "avverkningsdatum": ["2026-01-02", "2026-01-25"],
        }
    )
    harvest = checked_harvest(df, "2026-01")
    deliveries = delivery_frame("2026-01", [("A", "TALL", 40.0)], cfg)
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    assert by_class(step) == pytest.approx({"14": 40.0})


def test_trucks_that_follow_the_harvester_take_the_oldest_wood_and_later_trucks_a_mix(cfg):
    df = pd.DataFrame(
        {
            "avtalsobjekt": ["A"] * 3,
            "producerat_handelssortiment": ["TALL"] * 3,
            "diameterklass": ["14", "20", "26"],
            "langdklass": ["340"] * 3,
            "volym_m3fub": [100.0] * 3,
            "avverkningsdatum": ["2026-01-02", "2026-01-05", "2026-01-20"],
        }
    )
    harvest = checked_harvest(df, "2026-01")
    deliveries = delivery_frame("2026-01", [("A", "TALL", 140.0)], cfg)
    first = 100.0 * cfg.calibration
    overlapping = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    assert by_class(overlapping) == pytest.approx({"14": first, "20": 140.0 - first})
    after = deliveries.assign(leveransdatum=pd.Timestamp("2026-01-25"))
    pro_rata = close_month(Ledger.empty(), harvest, after, "2026-01", set(), cfg)
    assert by_class(pro_rata) == pytest.approx({"14": 140 / 3, "20": 140 / 3, "26": 140 / 3})
    switched_off = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), replace(cfg, oldest_first=False))
    assert by_class(switched_off) == pytest.approx(by_class(pro_rata))


def felled(rows):
    """rows: (diameter, volume, felling day), all in work order A, TALL, 2026-01."""
    df = pd.DataFrame([("A", "TALL", d, "340", v, day) for d, v, day in rows],
                      columns=["avtalsobjekt", "producerat_handelssortiment", "diameterklass", "langdklass", "volym_m3fub",
                               "avverkningsdatum"])
    return checked_harvest(df, "2026-01")


def test_the_day_method_takes_only_wood_felled_by_the_day_of_the_load(cfg):
    harvest = felled([("14", 100.0, "2026-01-02"), ("20", 100.0, "2026-01-10")])
    deliveries = delivery_frame("2026-01", [("A", "TALL", 120.0)], cfg).assign(leveransdatum=pd.Timestamp("2026-01-05"))
    month = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    assert by_class(month) == pytest.approx({"14": 100.0, "20": 20.0})

    day = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), replace(cfg, draw_per_day=True))
    tiers = day.allocation.groupby([TIER, DIA])[VOL].sum().to_dict()
    # The load takes the wood felled by January 5; the rest is beyond the stock, as the whole harvest so far.
    assert tiers == pytest.approx({("S1", "14"): 100.0, ("S2", "14"): 10.0, ("S2", "20"): 10.0})
    # The wood felled after the load stays in the stock, and what left beyond it is owed.
    assert day.ledger.stock[VOL].sum() == pytest.approx(100.0)
    assert day.ledger.deficit[BRUTTO].sum() == pytest.approx(20.0)


def test_the_day_method_goes_day_by_day_and_each_mill_gets_what_it_received(cfg):
    harvest = felled([("14", 50.0, "2026-01-02"), ("20", 50.0, "2026-01-10")])
    deliveries = delivery_frame("2026-01", [("A", "TALL", 40.0), ("A", "TALL", 50.0)], cfg)
    deliveries[DEST] = ["X", "Y"]
    deliveries["leveransdatum"] = pd.to_datetime(["2026-01-05", "2026-01-12"])
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), replace(cfg, draw_per_day=True))
    assert set(step.allocation[TIER]) == {"S1"}
    per_mill = step.allocation.groupby([DEST, DIA])[VOL].sum().to_dict()
    # January 5 has only the first felling; January 12 takes what is left of it first, then the second.
    assert per_mill == pytest.approx({("X", "14"): 40.0, ("Y", "14"): 10.0, ("Y", "20"): 40.0})
    assert step.ledger.stock[VOL].sum() == pytest.approx(10.0)


def test_the_day_method_draws_as_the_month_method_when_all_wood_was_felled_before_the_first_load(cfg):
    harvest = felled([("14", 60.0, "2026-01-02"), ("20", 40.0, "2026-01-03")])
    deliveries = delivery_frame("2026-01", [("A", "TALL", 30.0), ("A", "TALL", 25.0)], cfg)
    deliveries[DEST] = ["X", "Y"]
    deliveries["leveransdatum"] = pd.to_datetime(["2026-01-05", "2026-01-20"])
    month = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    day = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), replace(cfg, draw_per_day=True))
    columns = [DEST, DIA, TIER]
    pd.testing.assert_frame_equal(day.allocation.groupby(columns)[VOL].sum().reset_index(),
                                  month.allocation.groupby(columns)[VOL].sum().reset_index())
    assert day.felled_after == {}


def test_the_day_method_counts_an_earlier_estimate_off_the_wood_felled_by_then(cfg):
    per_day = replace(cfg, draw_per_day=True)
    january = close_month(Ledger.empty(), felled([("14", 50.0, "2026-01-02")]),
                          delivery_frame("2026-01", [("A", "TALL", 80.0)], cfg).assign(
                              leveransdatum=pd.Timestamp("2026-01-20")), "2026-01", set(), per_day)
    assert january.ledger.deficit[BRUTTO].sum() == pytest.approx(30.0)
    # February brings the late harvester data for January's wood, and February's own wood.
    late = pd.DataFrame([("A", "TALL", "20", "340", 30.0, "2026-01-15"), ("A", "TALL", "26", "340", 60.0, "2026-02-03")],
                        columns=["avtalsobjekt", "producerat_handelssortiment", "diameterklass", "langdklass", "volym_m3fub",
                                 "avverkningsdatum"])
    february = close_month(january.ledger, checked_harvest(late, "2026-02"),
                           delivery_frame("2026-02", [("A", "TALL", 40.0)], cfg).assign(
                               leveransdatum=pd.Timestamp("2026-02-10")), "2026-02", set(), per_day)
    # What left beyond the stock in January is counted off the wood felled in January, and February's load takes
    # February's wood.
    assert by_class(february) == pytest.approx({"26": 40.0})
    assert set(february.allocation[TIER]) == {"S1"}
    assert february.ledger.stock.groupby(DIA)[VOL].sum().to_dict() == pytest.approx({"26": 20.0})


def test_the_day_method_shows_and_settles_what_it_estimated_while_later_wood_remained(cfg):
    harvest = felled([("14", 100.0, "2026-01-10")])
    deliveries = delivery_frame("2026-01", [("A", "TALL", 30.0)], cfg).assign(leveransdatum=pd.Timestamp("2026-01-05"))
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), replace(cfg, draw_per_day=True))
    assert set(step.allocation[TIER]) == {"S2"}
    assert step.felled_after == pytest.approx({("A", "TALL"): 30.0})
    # The next month counts what left beyond the stock off the wood felled in January, before the rest is written off.
    after = close_month(step.ledger, harvest_frame("2026-02", []), delivery_frame("2026-02", [], cfg), "2026-02", {"A"},
                        replace(cfg, draw_per_day=True))
    row = after.reconciliation.iloc[0]
    assert (row["avraknat"], row["avskrivet"], row["avskrivet_underskott"]) == pytest.approx((30.0, 70.0, 0.0))


def test_gross_leaves_stock_and_net_is_allocated(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0)])
    deliveries = delivery_frame("2026-01", [("A", "TALL", 18.0)], cfg).assign(brutto_m3fub=20.0)
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    assert step.allocation[VOL].sum() == pytest.approx(18.0)
    assert step.ledger.stock[VOL].sum() == pytest.approx(80.0)
    net_only = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), replace(cfg, draw_gross=False))
    assert net_only.ledger.stock[VOL].sum() == pytest.approx(82.0)


def test_one_work_order_split_between_destinations_shares_its_stock(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 60.0), ("A", "TALL", "20", "340", 40.0)])
    deliveries = delivery_frame("2026-01", [("A", "TALL", 30.0), ("A", "TALL", 10.0)], cfg)
    deliveries[DEST] = ["X", "Y"]
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    per_destination = step.allocation.groupby(DEST)[VOL].sum()
    assert per_destination["X"] == pytest.approx(30.0)
    assert per_destination["Y"] == pytest.approx(10.0)
    assert step.ledger.stock[VOL].sum() == pytest.approx(60.0)


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
        {"avtalsobjekt": ["A"], "producerat_handelssortiment": ["MASSA"], "diameterklass": [None], "langdklass": [""], "volym_m3fub": [10.0]}
    )
    step = close_month(
        Ledger.empty(), checked_harvest(df, "2026-01"), delivery_frame("2026-01", [("A", "MASSA", 5.0)], cfg), "2026-01", set(), cfg
    )
    assert step.allocation.loc[0, SORT] == "MASSA"
    assert step.allocation.loc[0, DIA] == "-"


def _split_month(cfg, per_destination: bool):
    """One work order cut for two mills in the same assortment: thin logs for KLEN, thick for GROV."""
    raw = pd.DataFrame(
        [("A", "TALL", "14", "400", 40.0, "KLEN"), ("A", "TALL", "30", "500", 60.0, "GROV")],
        columns=["avtalsobjekt", "producerat_handelssortiment", "diameterklass", "langdklass", "volym_m3fub", "producerat_for_mottagningsplats"],
    )
    harvest = checked_harvest(raw, "2026-01")
    deliveries = pd.DataFrame(
        [("A", "TALL", 40.0, "KLEN"), ("A", "TALL", 60.0, "GROV")],
        columns=["avtalsobjekt", "handelssortiment", "volym_m3fub", "mottagningsplats"],
    ).assign(leveransnummer=["1", "2"], leveransdatum="2026-01-20", matmetod="stockmatning")

    deliveries = checked_deliveries(deliveries, "2026-01")
    return close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(),
                       replace(cfg, stock_per_destination=per_destination))


def test_each_mill_first_gets_the_wood_cut_for_it(cfg):
    step = _split_month(cfg, True)
    per_mill = step.allocation.groupby([DEST, DIA])[VOL].sum()
    assert per_mill[("KLEN", "14")] == pytest.approx(40.0)
    assert per_mill[("GROV", "30")] == pytest.approx(60.0)
    assert ("KLEN", "30") not in per_mill.index


def test_a_shared_stock_gives_every_mill_the_same_mix(cfg):
    step = _split_month(cfg, False)
    per_mill = step.allocation.groupby([DEST, DIA])[VOL].sum()
    assert per_mill[("KLEN", "30")] == pytest.approx(24.0)


def test_a_load_takes_the_wood_produced_for_its_mill_and_never_another_mills(cfg):
    """VIOL 3 says which mottagningsplats a delivery's wood was produced for: the load takes that stock wherever it was
    measured, and what that stock cannot cover is beyond the stock, not wood cut for another mill."""
    raw = pd.DataFrame(
        [("A", "TALL", "14", "400", 50.0, "KLEN"), ("A", "TALL", "30", "500", 50.0, "GROV")],
        columns=["avtalsobjekt", "producerat_handelssortiment", "diameterklass", "langdklass", "volym_m3fub", "producerat_for_mottagningsplats"],
    )
    harvest = checked_harvest(raw, "2026-01")
    deliveries = checked_deliveries(pd.DataFrame(
        [("A", "TALL", 30.0, "KLEN", "KLEN"), ("A", "TALL", 20.0, "MIX", "KLEN"), ("A", "TALL", 10.0, "MIX", "MIX")],
        columns=["avtalsobjekt", "handelssortiment", "volym_m3fub", "mottagningsplats", "producerat_for_mottagningsplats"],
    ).assign(leveransnummer=["1", "2", "3"], leveransdatum="2026-01-20", matmetod="stockmatning"), "2026-01")
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), replace(cfg, stock_per_destination=True))
    per_mill = step.allocation.groupby([DEST, TIER, DIA])[VOL].sum()
    # KLEN's 50 is shared by its two loads, the one measured at MIX too.
    assert per_mill[("KLEN", "S1", "14")] == pytest.approx(30.0)
    assert per_mill[("MIX", "S1", "14")] == pytest.approx(20.0)
    # The load produced for MIX has no stock of its own: an estimate from the whole harvest, GROV's wood left alone.
    assert per_mill[("MIX", "S2")].sum() == pytest.approx(10.0)
    assert not (step.allocation[TIER] == "S1").loc[step.allocation[DIA] == "30"].any()
    assert step.ledger.stock.groupby(PRODUCED_FOR)[VOL].sum().to_dict() == pytest.approx({"GROV": 50.0})


def _month_with_unreported_destination(cfg, on: bool):
    """KLEN's wood is 50, of which 20 was reported without the mottagningsplats it was produced for, as hpr allows."""
    raw = pd.DataFrame(
        [("A", "TALL", "14", "400", 30.0, "KLEN"), ("A", "TALL", "18", "400", 20.0, "-"),
         ("A", "TALL", "30", "500", 50.0, "GROV")],
        columns=["avtalsobjekt", "producerat_handelssortiment", "diameterklass", "langdklass", "volym_m3fub", "producerat_for_mottagningsplats"],
    )
    deliveries = checked_deliveries(pd.DataFrame(
        [("A", "TALL", 45.0, "KLEN", "KLEN"), ("A", "TALL", 40.0, "GROV", "GROV")],
        columns=["avtalsobjekt", "handelssortiment", "volym_m3fub", "mottagningsplats", "producerat_for_mottagningsplats"],
    ).assign(leveransnummer=["1", "2"], leveransdatum="2026-01-20", matmetod="stockmatning"), "2026-01")
    return close_month(Ledger.empty(), checked_harvest(raw, "2026-01"), deliveries, "2026-01", set(),
                       replace(cfg, stock_without_destination=on))


def test_wood_reported_without_a_mottagningsplats_is_taken_once_the_loads_own_pile_is_empty(cfg):
    step = _month_with_unreported_destination(cfg, True)
    per_mill = step.allocation.groupby([DEST, TIER, DIA])[VOL].sum()
    # KLEN's load takes its own 30 and 15 of the 20 without a mottagningsplats; nothing is an estimate.
    assert per_mill[("KLEN", "S1", "14")] == pytest.approx(30.0)
    assert per_mill[("KLEN", "S1", "18")] == pytest.approx(15.0)
    assert not (step.allocation[TIER] == "S2").any()
    # GROV's load is covered by its own pile and leaves the other alone.
    assert per_mill["GROV"].to_dict() == pytest.approx({("S1", "30"): 40.0})
    assert step.ledger.stock.groupby(PRODUCED_FOR)[VOL].sum().to_dict() == pytest.approx({"-": 5.0, "GROV": 10.0})


def test_without_the_setting_no_load_takes_wood_reported_without_a_mottagningsplats(cfg):
    step = _month_with_unreported_destination(cfg, False)
    per_mill = step.allocation.groupby([DEST, TIER])[VOL].sum()
    assert per_mill[("KLEN", "S1")] == pytest.approx(30.0)
    assert per_mill[("KLEN", "S2")] == pytest.approx(15.0)


def test_a_load_first_takes_the_wood_at_its_start_place(cfg):

    raw = pd.DataFrame(
        [("A", "TALL", "14", "400", 50.0, "P1"), ("A", "TALL", "30", "500", 50.0, "P2")],
        columns=["avtalsobjekt", "producerat_handelssortiment", "diameterklass", "langdklass", "volym_m3fub", "startplats"],
    )
    deliveries = checked_deliveries(pd.DataFrame(
        [("A", "TALL", 30.0, "P2")], columns=["avtalsobjekt", "handelssortiment", "volym_m3fub", "startplats"],
    ).assign(leveransnummer=["1"], leveransdatum="2026-01-20", matmetod="stockmatning"), "2026-01")
    step = close_month(Ledger.empty(), checked_harvest(raw, "2026-01"), deliveries, "2026-01", set(),
                       replace(cfg, stock_per_landing=True))
    assert step.allocation.groupby(DIA)[VOL].sum().to_dict() == pytest.approx({"30": 30.0})
    left = step.ledger.stock.groupby("startplats")[VOL].sum()
    assert left["P1"] == pytest.approx(50.0) and left["P2"] == pytest.approx(20.0)


def test_a_load_without_harvester_data_of_its_own_stops_the_month(cfg):
    # B has harvester data in another assortment only, and C none at all.
    harvest = harvest_frame("2026-01", [("A", "TALL", "20", "340", 100.0), ("B", "GRAN", "20", "340", 100.0)])
    deliveries = delivery_frame("2026-01", [("A", "TALL", 10.0), ("B", "TALL", 30.0), ("C", "GRAN", 20.0)], cfg)
    with pytest.raises(BrokenAssumption, match="2 avtalsobjekt och sortiment saknar egen skördardata, 50.0 m3fub: "
                                               "B TALL 30.0, C GRAN 20.0") as stop:
        close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    # A new ledger is the likeliest cause, so the stop says what the first month needs.
    assert "Liggaren är ny" in str(stop.value) and "Månaden körs inte" in str(stop.value)


def test_harvester_data_from_an_earlier_month_is_the_loads_own(cfg):
    january = harvest_frame("2026-01", [("A", "TALL", "20", "340", 10.0)])
    first = close_month(Ledger.empty(), january, delivery_frame("2026-01", [("A", "TALL", 10.0)], cfg), "2026-01", set(), cfg)
    # The stock is empty, but A has a harvest history: the load is an estimate (S2), not a stop.
    second = close_month(first.ledger, harvest_frame("2026-02", []), delivery_frame("2026-02", [("A", "TALL", 5.0)], cfg),
                         "2026-02", set(), cfg)
    assert set(second.allocation[TIER]) == {"S2"} and by_class(second) == pytest.approx({"20": 5.0})
    with pytest.raises(BrokenAssumption, match="1 avtalsobjekt och sortiment saknar egen skördardata") as stop:
        close_month(first.ledger, harvest_frame("2026-02", []), delivery_frame("2026-02", [("B", "TALL", 5.0)], cfg),
                    "2026-02", set(), cfg)
    assert "Liggaren är ny" not in str(stop.value)


def late(cfg, deliveries):
    """A delivers 30 with 20 harvested in class 14; the rest of its harvest, class 30, is reported a month later."""
    january = harvest_frame("2026-01", [("A", "TALL", "14", "340", 20.0)])
    first = close_month(Ledger.empty(), january, deliveries, "2026-01", set(), cfg)
    february = harvest_frame("2026-02", [("A", "TALL", "30", "340", 50.0)])
    return first, close_month(first.ledger, february, delivery_frame("2026-02", [], cfg), "2026-02", set(), cfg)


def test_late_harvester_data_is_counted_off_the_stock_and_the_estimate_stands(cfg):
    first, second = late(cfg, delivery_frame("2026-01", [("A", "TALL", 30.0)], cfg))
    assert first.allocation.groupby(TIER)[VOL].sum().to_dict() == pytest.approx({"S1": 20.0, "S2": 10.0})
    assert by_class(first) == pytest.approx({"14": 30.0})
    assert first.ledger.deficit[VOL].sum() == pytest.approx(10.0)

    # The 10 delivered beyond the stock are not delivered again: they leave the late wood's stock.
    assert second.ledger.deficit.empty
    assert second.ledger.stock[VOL].sum() == pytest.approx(40.0)
    assert second.reconciliation["avraknat"].sum() == pytest.approx(10.0)
    # Nothing is invoiced for it: January's estimate stands as it was invoiced.
    assert second.allocation.empty and second.credits.empty
    assert second.ledger.billed.groupby(DIA)[VOL].sum().to_dict() == pytest.approx({"14": 30.0})
    # How the estimate differed from the harvester data is kept for follow-up, and sums to nothing.
    moved = second.corrections.set_index(DIA)[VOL]
    assert moved.to_dict() == pytest.approx({"14": -10.0, "30": 10.0})


def test_the_comparison_with_late_harvester_data_follows_the_measured_assortment_and_the_mill(cfg):
    deliveries = reclassified("2026-01", [("A", "MASSA", "TALL", 30.0)], cfg)
    deliveries[DEST] = "X"
    first, second = late(cfg, deliveries)
    assert set(first.ledger.deficit[SORT]) == {"MASSA"}
    assert set(second.corrections[SORT]) == {"MASSA"} and set(second.corrections[DEST]) == {"X"}
