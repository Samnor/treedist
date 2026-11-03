from dataclasses import replace

import numpy as np
import pytest
from conftest import delivery_frame, harvest_frame

from treedist.core.allocate import close_month
from treedist.core.ledger import Ledger
from treedist.core.matrices import build_grids
from treedist.core.pipeline import run_month
from treedist.uncertainty.monte_carlo import monte_carlo


KEY = ("-", "TALL")


def two_class_harvest(ao="A"):
    return harvest_frame("2026-01", [(ao, "TALL", "14", "340", 500.0), (ao, "TALL", "20", "340", 500.0)])


def test_only_measurement_noise_remains_when_the_whole_stock_is_delivered(cfg, prices):
    deliveries = delivery_frame("2026-01", [("A", "TALL", 1000.0)], cfg)
    m = run_month(Ledger.empty(), two_class_harvest(), deliveries, prices, "2026-01", set(), cfg).matrices[KEY]
    assert 0 < m.std_distribution.max() < 0.01 * 1000
    assert m.std.max() > m.std_distribution.max()


def test_composition_uncertainty_falls_as_more_of_the_stock_is_delivered(cfg, prices):
    many = replace(cfg, mc_draws=2000)

    def relative_spread(volume):
        deliveries = delivery_frame("2026-01", [("A", "TALL", volume)], cfg)
        m = run_month(Ledger.empty(), two_class_harvest(), deliveries, prices, "2026-01", set(), many).matrices[KEY]
        return m.std_distribution.max() / volume

    assert relative_spread(900.0) < relative_spread(100.0)


def test_fixed_volume_draws_add_up_to_delivered_volume(cfg, prices):
    deliveries = delivery_frame("2026-01", [("A", "TALL", 300.0)], cfg)
    step = close_month(Ledger.empty(), two_class_harvest(), deliveries, "2026-01", set(), cfg)
    grids = build_grids(step)
    draws = monte_carlo(step.components, deliveries, grids, cfg)
    assert draws.fixed[KEY].sum(axis=(1, 2)) == pytest.approx(np.full(cfg.mc_draws, 300.0))


def test_volume_error_only_enters_the_total_draws(cfg, prices):
    deliveries = delivery_frame("2026-01", [("A", "TALL", 300.0)], cfg)
    step = close_month(Ledger.empty(), two_class_harvest(), deliveries, "2026-01", set(), cfg)
    draws = monte_carlo(step.components, deliveries, build_grids(step), cfg)
    assert draws.total[KEY].sum(axis=(1, 2)).std() > 1.0


def test_pool_volume_is_less_certain_than_own_stock(cfg, prices):
    donors = [
        (f"D{i}", "TALL", diameter, "340", 100.0)
        for i, diameter in enumerate(["14", "16", "18", "20", "22", "24"])
    ]
    harvest = harvest_frame("2026-01", [*donors, ("A", "TALL", "14", "340", 50.0), ("A", "TALL", "24", "340", 50.0)])

    def spread(ao):
        deliveries = delivery_frame("2026-01", [(ao, "TALL", 40.0)], cfg)
        m = run_month(Ledger.empty(), harvest, deliveries, prices, "2026-01", set(), cfg).matrices[KEY]
        return m.std_distribution.max()

    assert spread("NY") > spread("A")


def test_donor_draws_keep_whole_compositions(cfg):
    harvest = harvest_frame("2026-01", [(f"D{i}", "TALL", "14" if i % 2 else "24", "340", 100.0) for i in range(6)])
    deliveries = delivery_frame("2026-01", [("NY", "TALL", 40.0)], cfg)
    step = close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    draws = monte_carlo(step.components, deliveries, build_grids(step), cfg)
    # Every draw is one work order's wood, never a blend of the two groups.
    assert set(np.unique(draws.fixed[KEY].round(6))) == {0.0, 40.0}


def test_remainder_of_a_split_work_order_stays_uncertain(cfg):
    january = delivery_frame("2026-01", [("A", "TALL", 500.0)], cfg)
    first = close_month(Ledger.empty(), two_class_harvest(), january, "2026-01", set(), cfg)
    february = delivery_frame("2026-02", [("A", "TALL", 500.0)], cfg)
    second = close_month(first.ledger, two_class_harvest().iloc[0:0], february, "2026-02", set(), cfg)
    assert first.components[0].concentration == pytest.approx(second.components[0].concentration)


def test_light_intervals_leave_out_volume_error_and_the_finite_population_correction(cfg, prices):
    light = replace(cfg, volume_error=False, finite_population=False)
    deliveries = delivery_frame("2026-01", [("A", "TALL", 1000.0)], cfg)
    step = close_month(Ledger.empty(), two_class_harvest(), deliveries, "2026-01", set(), light)
    (component,) = step.components
    draws = monte_carlo(step.components, deliveries, build_grids(step), light)
    assert np.allclose(draws.total[KEY], draws.fixed[KEY])
    # The whole stock left, yet without the correction the noise is as for any part of it.
    assert component.concentration < 1000.0
