"""Monte Carlo over distribution and volume uncertainty.

Each draw re-samples what is not known:

    composition    which parts of the harvest left, or a whole donor work order
                   where none of its own data exists, plus sampling noise
    diameter bias  a work order's harvester reads systematically high or low,
                   moving volume between neighbouring diameter classes
    volume         delivery measurement error, independent per delivery plus an
                   error shared by all deliveries measured the same way

`fixed` holds draws with volumes as measured: that is the spread of an invoice,
whose volumes are contractually the measurement. `total` adds volume error and
describes what was physically delivered.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import Config
from ..core.allocate import Component
from ..core.matrices import Grid, MatrixKey
from ..schema import AO, DEST, SORT, VOL


@dataclass
class Draws:
    """Monte Carlo draws per (destination, assortment)."""

    fixed: dict[MatrixKey, np.ndarray]
    total: dict[MatrixKey, np.ndarray]


def _sample_part(
    rng: np.random.Generator, blocks: np.ndarray, weights: np.ndarray, concentration: float, n: int
) -> np.ndarray:
    """Compositions of `n` random parts of a harvest made of `blocks`."""
    gamma = rng.standard_gamma(weights * concentration, size=(n, len(blocks)))
    totals = gamma.sum(axis=1, keepdims=True)
    drawn = np.where(totals > 0, gamma / np.where(totals > 0, totals, 1.0), weights)
    return drawn @ blocks


def _sample_mean(rng: np.random.Generator, c: Component, n: int) -> np.ndarray:
    if c.mixture is None:
        return np.tile(c.q, (n, 1))
    if c.mixture_concentration is None:
        return c.mixture[rng.choice(len(c.mixture), size=n, p=c.mixture_weights)]
    if c.donor_parts is None:
        return _sample_part(rng, c.mixture, c.mixture_weights, c.mixture_concentration, n)
    donors = rng.choice(len(c.mixture), size=n, p=c.mixture_weights)
    out = np.empty((n, len(c.q)))
    for donor in np.unique(donors):
        drawn = donors == donor
        blocks, weights = c.donor_parts[donor]
        out[drawn] = _sample_part(rng, blocks, weights, c.mixture_concentration, int(drawn.sum()))
    return out


def _sample_composition(rng: np.random.Generator, c: Component, n: int) -> np.ndarray:
    mean = _sample_mean(rng, c, n)
    if np.isinf(c.concentration) or len(c.q) == 1:
        return mean
    gamma = rng.standard_gamma(mean * c.concentration)
    totals = gamma.sum(axis=1, keepdims=True)
    # A tiny concentration can underflow every cell; fall back to the mean.
    return np.where(totals > 0, gamma / np.where(totals > 0, totals, 1.0), mean)


def _shift_diameters(x: np.ndarray, widths_mm: np.ndarray, bias_mm: np.ndarray) -> np.ndarray:
    """Move a share of each numeric class to its neighbour, `bias_mm` per draw."""
    k = len(widths_mm)
    if k == 0:
        return x
    up = np.clip(np.maximum(bias_mm, 0)[:, None] / widths_mm[None, :], 0, 1)[:, :, None]
    down = np.clip(np.maximum(-bias_mm, 0)[:, None] / widths_mm[None, :], 0, 1)[:, :, None]

    numeric = x[:, :k, :]
    moved_up = numeric * up
    moved_down = numeric * down
    shifted = numeric - moved_up - moved_down
    shifted[:, 1:, :] += moved_up[:, :-1, :]
    shifted[:, :-1, :] += moved_down[:, 1:, :]
    # The outer classes have no neighbour to give to.
    shifted[:, -1, :] += moved_up[:, -1, :]
    shifted[:, 0, :] += moved_down[:, 0, :]

    out = x.copy()
    out[:, :k, :] = shifted
    return out


def _volume_errors(
    deliveries: pd.DataFrame, n: int, rng: np.random.Generator, cfg: Config
) -> dict[tuple[str, str, str], np.ndarray]:
    """Relative volume error per (work order, assortment, destination) and draw."""
    shared = {m: rng.normal(0, vm.systematic_sd, n) for m, vm in cfg.volume_methods.items()}

    errors = {}
    for key, block in deliveries.groupby([AO, SORT, DEST], sort=False):
        volume = float(block[VOL].sum())
        if volume <= 0:
            continue
        unit_cv = block["matmetod"].map(lambda m: cfg.volume_methods[m].unit_cv)
        independent = np.sqrt(float(((block[VOL] * unit_cv) ** 2 / block["antal_matenheter"]).sum()))
        common = sum(float(amount) * shared[m] for m, amount in block.groupby("matmetod")[VOL].sum().items())
        errors[key] = (common + rng.normal(0, independent, n)) / volume
    return errors


def monte_carlo(
    components: list[Component], deliveries: pd.DataFrame, grids: dict[MatrixKey, Grid], cfg: Config
) -> Draws:
    rng = np.random.default_rng(cfg.seed)
    n = cfg.mc_draws
    fixed = {k: np.zeros((n, *g.shape)) for k, g in grids.items()}
    total = {k: np.zeros((n, *g.shape)) for k, g in grids.items()}
    volume_errors = _volume_errors(deliveries, n, rng, cfg)

    grouped: dict[tuple[str, str, str], list[Component]] = defaultdict(list)
    for c in components:
        grouped[(c.ao, c.sortiment, c.destination)].append(c)

    for (ao, sortiment, destination), parts in sorted(grouped.items()):
        key = (destination, sortiment)
        grid = grids[key]
        d_index = {d: i for i, d in enumerate(grid.diameters)}
        l_index = {l: i for i, l in enumerate(grid.lengths)}
        harvester = np.zeros((n, *grid.shape))
        other = np.zeros((n, *grid.shape))

        for c in parts:
            rows = [d_index[d] for d in c.diameters]
            cols = [l_index[l] for l in c.lengths]
            target = harvester if c.harvester_based else other
            target[:, rows, cols] += _sample_composition(rng, c, n) * c.volume

        bias_mm = rng.normal(0, cfg.diameter_bias_sd_mm, n)
        x = _shift_diameters(harvester, grid.diameter_widths_mm(), bias_mm) + other
        fixed[key] += x
        # A load reversed within the month leaves no measured volume, and so no volume error.
        error = volume_errors.get((ao, sortiment, destination), np.zeros(n))
        total[key] += x * (1 + error)[:, None, None]

    return Draws(fixed, total)
