"""The month's matrices, one set per assortment (diameter × length, m3fub)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .allocate import CERTAINTY_TIERS, MonthStep
from .invoice import PriceList
from .schema import DIA, LEN, SORT, TIER, VOL, sorted_groups
from .uncertainty import Draws, Grid


@dataclass
class SortimentMatrices:
    sortiment: str
    grid: Grid
    delivered: np.ndarray
    by_tier: dict[str, np.ndarray]
    std: np.ndarray
    std_distribution: np.ndarray
    p05: np.ndarray
    p95: np.ndarray
    harvested: np.ndarray
    closing_stock: np.ndarray
    corrections: np.ndarray
    price_kr: np.ndarray
    value_kr: np.ndarray
    value_draws_fixed: np.ndarray
    value_draws_total: np.ndarray

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


def build_grids(step: MonthStep) -> dict[str, Grid]:
    """Axes per assortment: every class seen in any of the month's tables."""
    delivered = {c.sortiment for c in step.components}
    frames = [step.allocation, step.corrections, step.harvest, step.ledger.stock]
    grids = {}
    for sortiment in sorted(
        delivered | set(step.harvest[SORT]) | set(step.ledger.stock[SORT]) | set(step.corrections[SORT])
    ):
        diameters: list[str] = []
        lengths: list[str] = []
        for frame in frames:
            block = frame[frame[SORT] == sortiment]
            diameters.extend(block[DIA])
            lengths.extend(block[LEN])
        for c in step.components:
            if c.sortiment == sortiment:
                diameters.extend(c.diameters)
                lengths.extend(c.lengths)
        grids[sortiment] = Grid(tuple(sorted_groups(diameters)), tuple(sorted_groups(lengths)))
    return grids


def _dense(block: pd.DataFrame, grid: Grid) -> np.ndarray:
    if block.empty:
        return np.zeros(grid.shape)
    pivot = block.pivot_table(index=DIA, columns=LEN, values=VOL, aggfunc="sum", fill_value=0.0)
    return pivot.reindex(index=list(grid.diameters), columns=list(grid.lengths), fill_value=0.0).to_numpy()


def _price_matrix(sortiment: str, grid: Grid, prices: PriceList) -> np.ndarray:
    out = np.full(grid.shape, np.nan)
    for i, diameter in enumerate(grid.diameters):
        for j, length in enumerate(grid.lengths):
            price = prices.price_ore(sortiment, diameter, length)
            if price is not None:
                out[i, j] = price / 100
    return out


def build_matrices(
    step: MonthStep, grids: dict[str, Grid], draws: Draws, prices: PriceList
) -> dict[str, SortimentMatrices]:
    result = {}
    for sortiment, grid in grids.items():
        allocation = step.allocation[step.allocation[SORT] == sortiment]
        by_tier = {t: _dense(allocation[allocation[TIER] == t], grid) for t in CERTAINTY_TIERS}
        delivered = sum(by_tier.values())

        fixed, total = draws.fixed[sortiment], draws.total[sortiment]
        # Unpriced products have NaN in `price_kr`, carry no value and are flagged on the invoice.
        price = _price_matrix(sortiment, grid, prices)
        priced = np.nan_to_num(price)

        result[sortiment] = SortimentMatrices(
            sortiment=sortiment,
            grid=grid,
            delivered=delivered,
            by_tier=by_tier,
            std=total.std(axis=0),
            std_distribution=fixed.std(axis=0),
            p05=np.quantile(total, 0.05, axis=0),
            p95=np.quantile(total, 0.95, axis=0),
            harvested=_dense(step.harvest[step.harvest[SORT] == sortiment], grid),
            closing_stock=_dense(step.ledger.stock[step.ledger.stock[SORT] == sortiment], grid),
            corrections=_dense(step.corrections[step.corrections[SORT] == sortiment], grid),
            price_kr=price,
            value_kr=delivered * priced,
            value_draws_fixed=(fixed * priced).sum(axis=(1, 2)),
            value_draws_total=(total * priced).sum(axis=(1, 2)),
        )
    return result
