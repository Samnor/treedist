"""Monte Carlo over distribution and volume uncertainty, for judging the method. A run never draws.

The allocation is deterministic: the matrices and the appendix never depend on a draw. What the evaluation asks is
whether the method knows how uncertain it is: does the true value of a month's delivery fall inside the method's
90 % interval nine times in ten? Each draw re-samples what is not known:

    composition    Dirichlet noise around the allocated composition, as wide as the part's sample warrants
    volume         delivery measurement error, independent per delivery plus an error shared by all deliveries
                   measured the same way

`fixed` holds draws with volumes as measured, the spread of the distribution; `total` adds volume error and
describes what was physically delivered.
"""

from __future__ import annotations

import tomllib
from collections import defaultdict
from dataclasses import dataclass, field, fields
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.allocate import Component
from ..core.matrices import Grid, MatrixKey
from ..schema import AO, DEST, SORT, VOL


@dataclass(frozen=True)
class VolumeMethod:
    """Error model for one delivery measurement method.

    `unit_cv` is the relative SD of one control unit (a log or a pile), so a delivery of n units has CV
    unit_cv / sqrt(n). `systematic_sd` is shared by all deliveries measured with the method in a month.
    `default_units` stands in when a delivery does not say how many units it had.
    """

    unit_cv: float
    default_units: float
    systematic_sd: float


def default_volume_methods() -> dict[str, VolumeMethod]:
    return {
        "stockmatning": VolumeMethod(0.043, 150, 0.0005),
        "travmatning": VolumeMethod(0.051, 3, 0.0015),
        "vagning": VolumeMethod(0.069, 3, 0.005),
        "skordarmatning": VolumeMethod(0.050, 150, 0.005),
        "okand": VolumeMethod(0.080, 1, 0.02),
    }


@dataclass(frozen=True)
class Uncertainty:
    """The Monte Carlo's parameters; see docs/metod.md."""

    design_effect: float = 200.0
    default_log_volume: float = 0.25
    pool_remaining_share: float = 0.5
    finite_population: bool = True
    volume_error: bool = True
    log_counts: bool = True
    intervals: bool = True
    mc_draws: int = 2000
    seed: int = 20261102
    volume_methods: dict[str, VolumeMethod] = field(default_factory=default_volume_methods)

    def __post_init__(self) -> None:
        if self.mc_draws < 100:
            raise ValueError("mc_draws måste vara minst 100")


def load_uncertainty(path: Path | None) -> Uncertainty:
    """The Monte Carlo's parameters in a configuration file; the method's own are read by config.load_config."""
    if path is None:
        return Uncertainty()
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    known = {f.name for f in fields(Uncertainty)}
    values = {k: v for k, v in raw.items() if k in known}
    if "volume_methods" in values:
        methods = default_volume_methods()
        for name, given in values["volume_methods"].items():
            methods[name] = VolumeMethod(**given)
        values["volume_methods"] = methods
    return Uncertainty(**values)


def _sample_size(log_count: float, remaining_share: float, u: Uncertainty) -> float:
    """How precisely a part of a harvest is known when the rest stayed behind.

    Logs travel in piles from one part of the stand, so the effective number of independent logs is the count
    divided by the design effect. What stayed behind is the finite population correction: the less of the harvest
    that left, the more the part can differ from the whole. The harvester's classing of each log caps the precision
    at one independent error per log.
    """
    effective = max(log_count / u.design_effect, 1.0)
    if not u.finite_population:
        return min(effective, float(log_count))
    return min(max(effective / remaining_share - 1, 1.0), float(log_count))


def concentration(c: Component, u: Uncertainty) -> float:
    """The Dirichlet concentration of a part's composition: its sample size.

    From the stock (S1) it rests on the logs counted in what left, or on its volume when they were not counted, and
    sampling uncertainty disappears only if the whole harvest left in one month. Emptying a stock in a second month
    does not count: that remainder is the harvest minus an uncertain first part. Beyond the stock (S2) a
    typical share of the unknown harvest, `pool_remaining_share`, is taken to stay behind.
    """
    if c.tier != "S1":
        return _sample_size(c.basis / u.default_log_volume, u.pool_remaining_share, u)
    logs = c.logs if u.log_counts else 0.0
    log_count = logs if logs > 0 else c.basis / u.default_log_volume
    remaining_share = max(1 - c.basis / c.harvested, 0.0)
    if remaining_share <= 1e-9 and u.finite_population:
        return float(log_count)
    return _sample_size(log_count, remaining_share, u)


@dataclass
class Draws:
    """Monte Carlo draws per (destination, assortment), shaped (draws, diameters, lengths)."""

    fixed: dict[MatrixKey, np.ndarray]
    total: dict[MatrixKey, np.ndarray]


def _sample_composition(rng: np.random.Generator, c: Component, n: int, u: Uncertainty) -> np.ndarray:
    alpha = concentration(c, u)
    mean = np.tile(c.q, (n, 1))
    if np.isinf(alpha) or len(c.q) == 1:
        return mean
    gamma = rng.standard_gamma(mean * alpha)
    totals = gamma.sum(axis=1, keepdims=True)
    # A tiny concentration can underflow every cell; fall back to the mean.
    return np.where(totals > 0, gamma / np.where(totals > 0, totals, 1.0), mean)


def _volume_errors(
    deliveries: pd.DataFrame, n: int, rng: np.random.Generator, u: Uncertainty
) -> dict[tuple[str, str, str], np.ndarray]:
    """Relative volume error per (contract object, assortment, destination) and draw."""
    shared = {m: rng.normal(0, vm.systematic_sd, n) for m, vm in u.volume_methods.items()}

    errors = {}
    for key, block in deliveries.groupby([AO, SORT, DEST], sort=False):
        volume = float(block[VOL].sum())
        if volume <= 0:
            continue
        unit_cv = block["matmetod"].map(lambda m: u.volume_methods[m].unit_cv)
        defaults = block["matmetod"].map(lambda m: u.volume_methods[m].default_units)
        units = block["antal_matenheter"].where(block["antal_matenheter"] > 0, defaults)
        independent = np.sqrt(float(((block[VOL] * unit_cv) ** 2 / units).sum()))
        common = sum(float(amount) * shared[m] for m, amount in block.groupby("matmetod")[VOL].sum().items())
        errors[key] = (common + rng.normal(0, independent, n)) / volume
    return errors


def monte_carlo(
    components: list[Component], deliveries: pd.DataFrame, grids: dict[MatrixKey, Grid], u: Uncertainty
) -> Draws:
    rng = np.random.default_rng(u.seed)
    n = u.mc_draws
    fixed = {k: np.zeros((n, *g.shape)) for k, g in grids.items()}
    total = {k: np.zeros((n, *g.shape)) for k, g in grids.items()}
    volume_errors = _volume_errors(deliveries, n, rng, u) if u.volume_error else {}

    grouped: dict[tuple[str, str, str], list[Component]] = defaultdict(list)
    for c in components:
        grouped[(c.ao, c.sortiment, c.destination)].append(c)

    for (ao, sortiment, destination), parts in sorted(grouped.items()):
        key = (destination, sortiment)
        grid = grids[key]
        d_index = {d: i for i, d in enumerate(grid.diameters)}
        l_index = {length: i for i, length in enumerate(grid.lengths)}
        x = np.zeros((n, *grid.shape))
        for c in parts:
            rows = [d_index[d] for d in c.diameters]
            cols = [l_index[length] for length in c.lengths]
            x[:, rows, cols] += _sample_composition(rng, c, n, u) * c.volume

        fixed[key] += x
        # A load reversed within the month leaves no measured volume, and so no volume error.
        error = volume_errors.get((ao, sortiment, destination), np.zeros(n))
        total[key] += x * (1 + error)[:, None, None]

    return Draws(fixed, total)
