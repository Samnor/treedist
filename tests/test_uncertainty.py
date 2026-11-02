from dataclasses import replace

import numpy as np
import pytest
from conftest import delivery_frame, harvest_frame

from treedist.allocate import close_month
from treedist.ledger import Ledger
from treedist.matrices import build_grids
from treedist.pipeline import run_month
from treedist.uncertainty import Grid, _shift_diameters, monte_carlo


def two_class_harvest(ao="A"):
    return harvest_frame("2026-01", [(ao, "TALL", "14", "340", 500.0), (ao, "TALL", "20", "340", 500.0)])


def test_composition_is_certain_when_the_whole_stock_is_delivered(cfg, prices):
    still = replace(cfg, diameter_bias_sd_mm=0.0)
    deliveries = delivery_frame("2026-01", [("A", "TALL", 1000.0)], cfg)
    m = run_month(Ledger.empty(), two_class_harvest(), deliveries, prices, "2026-01", set(), still).matrices["TALL"]
    assert m.std_distribution.max() == pytest.approx(0.0, abs=1e-9)
    assert m.std.max() > 0


def test_composition_uncertainty_falls_as_more_of_the_stock_is_delivered(cfg, prices):
    still = replace(cfg, diameter_bias_sd_mm=0.0, mc_draws=2000)

    def relative_spread(volume):
        deliveries = delivery_frame("2026-01", [("A", "TALL", volume)], cfg)
        m = run_month(Ledger.empty(), two_class_harvest(), deliveries, prices, "2026-01", set(), still).matrices["TALL"]
        return m.std_distribution.max() / volume

    assert relative_spread(900.0) < relative_spread(100.0)


def test_fixed_volume_draws_add_up_to_delivered_volume(cfg, prices):
    deliveries = delivery_frame("2026-01", [("A", "TALL", 300.0)], cfg)
    step = close_month(Ledger.empty(), two_class_harvest(), deliveries, "2026-01", set(), cfg)
    grids = build_grids(step)
    draws = monte_carlo(step.components, deliveries, grids, cfg)
    assert draws.fixed["TALL"].sum(axis=(1, 2)) == pytest.approx(np.full(cfg.mc_draws, 300.0))


def test_volume_error_only_enters_the_total_draws(cfg, prices):
    deliveries = delivery_frame("2026-01", [("A", "TALL", 300.0)], cfg)
    step = close_month(Ledger.empty(), two_class_harvest(), deliveries, "2026-01", set(), cfg)
    draws = monte_carlo(step.components, deliveries, build_grids(step), cfg)
    assert draws.total["TALL"].sum(axis=(1, 2)).std() > 1.0


def test_pool_volume_is_less_certain_than_own_stock(cfg, prices):
    donors = [
        (f"D{i}", "TALL", diameter, "340", 100.0)
        for i, diameter in enumerate(["14", "16", "18", "20", "22", "24"])
    ]
    harvest = harvest_frame("2026-01", [*donors, ("A", "TALL", "14", "340", 50.0), ("A", "TALL", "24", "340", 50.0)])

    def spread(ao):
        deliveries = delivery_frame("2026-01", [(ao, "TALL", 40.0)], cfg)
        m = run_month(Ledger.empty(), harvest, deliveries, prices, "2026-01", set(), cfg).matrices["TALL"]
        return m.std_distribution.max()

    assert spread("NY") > spread("A")


def test_donor_draws_keep_whole_compositions(cfg):
    harvest = harvest_frame("2026-01", [(f"D{i}", "TALL", "14" if i % 2 else "24", "340", 100.0) for i in range(6)])
    deliveries = delivery_frame("2026-01", [("NY", "TALL", 40.0)], cfg)
    still = replace(cfg, diameter_bias_sd_mm=0.0)
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), still)
    draws = monte_carlo(step.components, deliveries, build_grids(step), still)
    # Every draw is one work order's wood, never a blend of the two groups.
    assert set(np.unique(draws.fixed["TALL"].round(6))) == {0.0, 40.0}


def test_diameter_shift_preserves_volume():
    x = np.array([[[10.0], [20.0], [30.0]], [[10.0], [20.0], [30.0]]])
    widths = Grid(("14", "16", "18"), ("340",)).diameter_widths_mm()
    shifted = _shift_diameters(x, widths, np.array([5.0, -5.0]))
    assert shifted.sum(axis=(1, 2)) == pytest.approx([60.0, 60.0])
    assert shifted[0, 1, 0] == pytest.approx(20 * 0.75 + 10 * 0.25)
    assert shifted[1, 1, 0] == pytest.approx(20 * 0.75 + 30 * 0.25)


def test_labels_stay_out_of_the_diameter_shift():
    grid = Grid(("14", "16", "OKÄND"), ("340",))
    x = np.array([[[10.0], [20.0], [5.0]]])
    shifted = _shift_diameters(x, grid.diameter_widths_mm(), np.array([5.0]))
    assert shifted[0, 2, 0] == 5.0
    assert shifted.sum() == pytest.approx(35.0)
