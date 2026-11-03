"""The month's matrices, one set per destination and assortment (diameter × length, m3fub)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from ..schema import AO, DEST, DIA, LEN, NO_DESTINATION, SORT, TIER, VOL, sorted_groups
from .allocate import CERTAINTY_TIERS, MonthStep
from .invoice import PriceList

if TYPE_CHECKING:
    from ..uncertainty.monte_carlo import Draws

MatrixKey = tuple[str, str]


@dataclass(frozen=True)
class Grid:
    diameters: tuple[str, ...]
    lengths: tuple[str, ...]

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.diameters), len(self.lengths))

    def diameter_widths_mm(self) -> np.ndarray:
        """Width of the numeric diameter classes, which sort first on the axis.

        The top class repeats its neighbour's width. Labels such as "-" and
        OKÄND have no neighbours and stay out of the diameter shift.
        """
        floors = []
        for diameter in self.diameters:
            try:
                floors.append(float(diameter))
            except ValueError:
                break
        if len(floors) < 2:
            return np.empty(0)
        widths = np.diff(floors)
        return np.append(widths, widths[-1]) * 10


@dataclass
class SortimentMatrices:
    destination: str
    sortiment: str
    grid: Grid
    delivered: np.ndarray
    by_tier: dict[str, np.ndarray]
    harvested: np.ndarray
    closing_stock: np.ndarray
    corrections: np.ndarray
    price_kr: np.ndarray
    value_kr: np.ndarray
    # Only with intervals; see uncertainty/.
    std: np.ndarray | None = None
    std_distribution: np.ndarray | None = None
    p05: np.ndarray | None = None
    p95: np.ndarray | None = None
    value_draws_fixed: np.ndarray | None = None
    value_draws_total: np.ndarray | None = None

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


def _with_destination(frame: pd.DataFrame, step: MonthStep) -> pd.DataFrame:
    """Harvest and stock belong to a work order; they count at its planned destination."""
    planned = frame[AO].map(step.work_orders.destinations).astype(object).fillna(NO_DESTINATION)
    return frame.assign(**{DEST: planned})


def build_grids(step: MonthStep) -> dict[MatrixKey, Grid]:
    """Axes per destination and assortment: every class seen in the month's tables."""
    frames = [
        step.allocation,
        step.corrections,
        _with_destination(step.harvest, step),
        _with_destination(step.ledger.stock, step),
    ]
    diameters: dict[MatrixKey, list[str]] = defaultdict(list)
    lengths: dict[MatrixKey, list[str]] = defaultdict(list)
    for frame in frames:
        for key, block in frame.groupby([DEST, SORT], sort=False):
            diameters[key].extend(block[DIA])
            lengths[key].extend(block[LEN])
    for c in step.components:
        key = (c.destination, c.sortiment)
        diameters[key].extend(c.diameters)
        lengths[key].extend(c.lengths)
    return {k: Grid(tuple(sorted_groups(diameters[k])), tuple(sorted_groups(lengths[k]))) for k in sorted(diameters)}


def _select(frame: pd.DataFrame, key: MatrixKey) -> pd.DataFrame:
    return frame[(frame[DEST] == key[0]) & (frame[SORT] == key[1])]


def _dense(block: pd.DataFrame, grid: Grid) -> np.ndarray:
    if block.empty:
        return np.zeros(grid.shape)
    pivot = block.pivot_table(index=DIA, columns=LEN, values=VOL, aggfunc="sum", fill_value=0.0)
    return pivot.reindex(index=list(grid.diameters), columns=list(grid.lengths), fill_value=0.0).to_numpy()


def _price_matrix(key: MatrixKey, grid: Grid, prices: PriceList) -> np.ndarray:
    out = np.full(grid.shape, np.nan)
    for i, diameter in enumerate(grid.diameters):
        for j, length in enumerate(grid.lengths):
            price = prices.price_ore(key[1], diameter, length, key[0])
            if price is not None:
                out[i, j] = price / 100
    return out


def build_matrices(
    step: MonthStep, grids: dict[MatrixKey, Grid], draws: Draws | None, prices: PriceList
) -> dict[MatrixKey, SortimentMatrices]:
    harvest = _with_destination(step.harvest, step)
    stock = _with_destination(step.ledger.stock, step)
    result = {}
    for key, grid in grids.items():
        allocation = _select(step.allocation, key)
        by_tier = {t: _dense(allocation[allocation[TIER] == t], grid) for t in CERTAINTY_TIERS}
        delivered = sum(by_tier.values())

        # Unpriced products have NaN in `price_kr`, carry no value and are flagged on the invoice.
        price = _price_matrix(key, grid, prices)
        priced = np.nan_to_num(price)

        matrices = SortimentMatrices(
            destination=key[0],
            sortiment=key[1],
            grid=grid,
            delivered=delivered,
            by_tier=by_tier,
            harvested=_dense(_select(harvest, key), grid),
            closing_stock=_dense(_select(stock, key), grid),
            corrections=_dense(_select(step.corrections, key), grid),
            price_kr=price,
            value_kr=delivered * priced,
        )
        if draws is not None:
            fixed, total = draws.fixed[key], draws.total[key]
            matrices.std = total.std(axis=0)
            matrices.std_distribution = fixed.std(axis=0)
            matrices.p05 = np.quantile(total, 0.05, axis=0)
            matrices.p95 = np.quantile(total, 0.95, axis=0)
            matrices.value_draws_fixed = (fixed * priced).sum(axis=(1, 2))
            matrices.value_draws_total = (total * priced).sum(axis=(1, 2))
        result[key] = matrices
    return result
