"""Monte Carlo over distribution and volume uncertainty.

Each draw re-samples what is not known:

    composition    sampling noise around the allocated composition, or around a
                   whole donor work order where none of its own data exists
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


def _sample_composition(rng: np.random.Generator, c: Component, n: int) -> np.ndarray:
    if c.donors is None:
        mean = np.tile(c.q, (n, 1))
    else:
        mean = c.donors[rng.choice(len(c.donors), size=n, p=c.donor_weights)]
    if np.isinf(c.concentration) or len(c.q) == 1:
        return mean
    gamma = rng.standard_gamma(mean * c.concentration)
    totals = gamma.sum(axis=1, keepdims=True)
    # A tiny concentration can underflow every cell; fall back to the mean.
    return np.where(totals > 0, gamma / np.where(totals > 0, totals, 1.0), mean)


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
        x = np.zeros((n, *grid.shape))
        for c in parts:
            rows = [d_index[d] for d in c.diameters]
            cols = [l_index[l] for l in c.lengths]
            x[:, rows, cols] += _sample_composition(rng, c, n) * c.volume

        fixed[key] += x
        # A load reversed within the month leaves no measured volume, and so no volume error.
        error = volume_errors.get((ao, sortiment, destination), np.zeros(n))
        total[key] += x * (1 + error)[:, None, None]

    return Draws(fixed, total)
