"""The evaluation's Monte Carlo: does the method know how uncertain it is? A run never draws."""

from dataclasses import replace

import numpy as np
import pytest
from conftest import delivery_frame, harvest_frame

from treedist.core.allocate import close_month
from treedist.core.ledger import Ledger
from treedist.core.matrices import build_grids
from treedist.dev.model import evaluate_month
from treedist.dev.uncertainty import concentration, monte_carlo


KEY = ("SAG", "TALL")


def two_class_harvest(ao="A"):
    return harvest_frame("2026-01", [(ao, "TALL", "14", "340", 500.0), (ao, "TALL", "20", "340", 500.0)])


def test_only_measurement_noise_remains_when_the_whole_stock_is_delivered(cfg, model):
    deliveries = delivery_frame("2026-01", [("A", "TALL", 1000.0)], cfg)
    draws = evaluate_month(Ledger.empty(), two_class_harvest(), deliveries, "2026-01", set(), model).draws
    fixed, total = draws.fixed[KEY].std(axis=0), draws.total[KEY].std(axis=0)
    assert 0 < fixed.max() < 0.01 * 1000
    assert total.max() > fixed.max()


def test_composition_uncertainty_falls_as_more_of_the_stock_is_delivered(cfg, model):
    many = replace(model, mc_draws=2000)

    def relative_spread(volume):
        deliveries = delivery_frame("2026-01", [("A", "TALL", volume)], cfg)
        draws = evaluate_month(Ledger.empty(), two_class_harvest(), deliveries, "2026-01", set(), many).draws
        return draws.fixed[KEY].std(axis=0).max() / volume

    assert relative_spread(900.0) < relative_spread(100.0)


def test_fixed_volume_draws_add_up_to_delivered_volume(cfg, model):
    deliveries = delivery_frame("2026-01", [("A", "TALL", 300.0)], cfg)
    step = close_month(Ledger.empty(), two_class_harvest(), deliveries, "2026-01", set(), cfg)
    grids = build_grids(step)
    draws = monte_carlo(step.components, deliveries, grids, model.uncertainty)
    assert draws.fixed[KEY].sum(axis=(1, 2)) == pytest.approx(np.full(model.mc_draws, 300.0))


def test_volume_error_only_enters_the_total_draws(cfg, model):
    deliveries = delivery_frame("2026-01", [("A", "TALL", 300.0)], cfg)
    step = close_month(Ledger.empty(), two_class_harvest(), deliveries, "2026-01", set(), cfg)
    draws = monte_carlo(step.components, deliveries, build_grids(step), model.uncertainty)
    assert draws.total[KEY].sum(axis=(1, 2)).std() > 1.0


def test_volume_beyond_the_stock_is_drawn_from_the_whole_harvest(cfg, model):
    january = delivery_frame("2026-01", [("A", "TALL", 1000.0)], cfg)
    first = close_month(Ledger.empty(), two_class_harvest(), january, "2026-01", set(), cfg)
    february = delivery_frame("2026-02", [("A", "TALL", 300.0)], cfg)
    second = close_month(first.ledger, two_class_harvest().iloc[0:0], february, "2026-02", set(), cfg)
    assert {c.tier for c in second.components} == {"S2"}
    draws = monte_carlo(second.components, february, build_grids(second), model.uncertainty)
    assert draws.fixed[KEY].sum(axis=(1, 2)) == pytest.approx(np.full(model.mc_draws, 300.0))
    # Both of the harvest's classes are drawn, and how much of each is uncertain.
    assert (draws.fixed[KEY].std(axis=0) > 0).sum() == 2


def test_remainder_of_a_split_work_order_stays_uncertain(cfg, model):
    january = delivery_frame("2026-01", [("A", "TALL", 500.0)], cfg)
    first = close_month(Ledger.empty(), two_class_harvest(), january, "2026-01", set(), cfg)
    february = delivery_frame("2026-02", [("A", "TALL", 500.0)], cfg)
    second = close_month(first.ledger, two_class_harvest().iloc[0:0], february, "2026-02", set(), cfg)
    u = model.uncertainty
    assert concentration(first.components[0], u) == pytest.approx(concentration(second.components[0], u))


def test_light_intervals_leave_out_volume_error_and_the_finite_population_correction(cfg, model):
    light = replace(model, volume_error=False, finite_population=False).uncertainty
    deliveries = delivery_frame("2026-01", [("A", "TALL", 1000.0)], cfg)
    step = close_month(Ledger.empty(), two_class_harvest(), deliveries, "2026-01", set(), cfg)
    (component,) = step.components
    draws = monte_carlo(step.components, deliveries, build_grids(step), light)
    assert np.allclose(draws.total[KEY], draws.fixed[KEY])
    # The whole stock left, yet without the correction the noise is as for any part of it.
    assert concentration(component, light) < 1000.0


def test_without_log_counts_the_noise_follows_the_volume(cfg, model):
    volume_only = replace(model, log_counts=False, finite_population=False).uncertainty
    deliveries = delivery_frame("2026-01", [("A", "TALL", 400.0)], cfg)
    few, many = (
        concentration(close_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg).components[0], volume_only)
        for harvest in (two_class_harvest(), two_class_harvest().assign(antal_stockar=50000))
    )
    assert few == many == pytest.approx(400.0 / volume_only.default_log_volume / volume_only.design_effect)
