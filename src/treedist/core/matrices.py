"""The month's matrices, one set per destination and assortment (diameter × length, m3fub)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..schema import DEST, DIA, LEN, PRODUCED, PRODUCED_FOR, SORT, TIER, VOL, sorted_groups
from .allocate import CERTAINTY_TIERS, MonthStep


MatrixKey = tuple[str, str]
# What a matrix is keyed by in each kind of frame: where and as what the wood was measured, and, for harvest and stock,
# the mottagningsplats it was produced for and the assortment it was produced as.
MEASURED_KEY = [DEST, SORT]
PRODUCED_KEY = [PRODUCED_FOR, PRODUCED]


@dataclass(frozen=True)
class Grid:
    diameters: tuple[str, ...]
    lengths: tuple[str, ...]

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.diameters), len(self.lengths))


@dataclass
class SortimentMatrices:
    destination: str
    sortiment: str
    grid: Grid
    delivered: np.ndarray
    by_tier: dict[str, np.ndarray]
    harvested: np.ndarray
    closing_stock: np.ndarray
    # Loads reversed after the month they were invoiced in, as negative volume.
    credits: np.ndarray
    # Only with intervals; see uncertainty/.

    @property
    def share(self) -> np.ndarray:
        total = self.delivered.sum()
        return self.delivered / total if total > 0 else np.zeros_like(self.delivered)

    def frame(self, values: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(
            values,
            index=pd.Index(self.grid.diameters, name=DIA),
            columns=pd.Index(self.grid.lengths, name=LEN),
        )


def build_grids(step: MonthStep) -> dict[MatrixKey, Grid]:
    """Axes per destination and assortment: every class seen in the month's tables."""
    frames = [
        (step.allocation, MEASURED_KEY),
        (step.credits, MEASURED_KEY),
        # Harvest and stock count at the mottagningsplats they were produced for.
        (step.harvest, PRODUCED_KEY),
        (step.ledger.stock, PRODUCED_KEY),
    ]
    diameters: dict[MatrixKey, list[str]] = defaultdict(list)
    lengths: dict[MatrixKey, list[str]] = defaultdict(list)
    for frame, columns in frames:
        for key, block in frame.groupby(columns, sort=False):
            diameters[key].extend(block[DIA])
            lengths[key].extend(block[LEN])
    for c in step.components:
        key = (c.destination, c.sortiment)
        diameters[key].extend(c.diameters)
        lengths[key].extend(c.lengths)
    return {k: Grid(tuple(sorted_groups(diameters[k])), tuple(sorted_groups(lengths[k]))) for k in sorted(diameters)}


def _select(frame: pd.DataFrame, key: MatrixKey, columns: list[str] = MEASURED_KEY) -> pd.DataFrame:
    return frame[(frame[columns[0]] == key[0]) & (frame[columns[1]] == key[1])]


def _dense(block: pd.DataFrame, grid: Grid) -> np.ndarray:
    if block.empty:
        return np.zeros(grid.shape)
    pivot = block.pivot_table(index=DIA, columns=LEN, values=VOL, aggfunc="sum", fill_value=0.0)
    return pivot.reindex(index=list(grid.diameters), columns=list(grid.lengths), fill_value=0.0).to_numpy()


def build_matrices(
    step: MonthStep, grids: dict[MatrixKey, Grid]
) -> dict[MatrixKey, SortimentMatrices]:
    harvest, stock = step.harvest, step.ledger.stock
    result = {}
    for key, grid in grids.items():
        allocation = _select(step.allocation, key)
        by_tier = {t: _dense(allocation[allocation[TIER] == t], grid) for t in CERTAINTY_TIERS}
        delivered = sum(by_tier.values())

        matrices = SortimentMatrices(
            destination=key[0],
            sortiment=key[1],
            grid=grid,
            delivered=delivered,
            by_tier=by_tier,
            harvested=_dense(_select(harvest, key, PRODUCED_KEY), grid),
            closing_stock=_dense(_select(stock, key, PRODUCED_KEY), grid),
            credits=_dense(_select(step.credits, key), grid),
        )
        result[key] = matrices
    return result
