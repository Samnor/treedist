"""Run the method over a simulated flow and score it against the facit."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..core.ledger import Ledger
from ..core.matrices import SortimentMatrices
from ..schema import DEST, DIA, LEN, SORT, VOL, sorted_groups, validate_deliveries, validate_harvest
from .model import Model, evaluate_month
from .prices import PriceList
from .simulate import SimMonth, SimParams, example_price_list, simulate


@dataclass
class BacktestResult:
    per_month: pd.DataFrame
    summary: dict[str, float]


def _pivot(block: pd.DataFrame, diameters: list[str], lengths: list[str]) -> np.ndarray:
    if block.empty:
        return np.zeros((len(diameters), len(lengths)))
    pivot = block.pivot_table(index=DIA, columns=LEN, values=VOL, aggfunc="sum", fill_value=0.0)
    return pivot.reindex(index=diameters, columns=lengths, fill_value=0.0).to_numpy()


def _shares(values: np.ndarray) -> np.ndarray:
    total = values.sum()
    return values / total if total > 0 else values


def _score(
    month: SimMonth, m: SortimentMatrices, prices: PriceList, naive: np.ndarray | None, draws=None
) -> dict[str, float | str]:
    """How far one matrix is from the facit, its errors weighed in kronor; `draws` are the month's Monte Carlo
    draws, for whether the value's interval covers the true value."""
    total_draws = draws.total[(m.destination, m.sortiment)] if draws is not None else None
    truth_block = month.truth[(month.truth[SORT] == m.sortiment) & (month.truth[DEST] == m.destination)]
    diameters = sorted_groups([*m.grid.diameters, *truth_block[DIA]])
    lengths = sorted_groups([*m.grid.lengths, *truth_block[LEN]])

    def on_axes(values: np.ndarray) -> np.ndarray:
        return m.frame(values).reindex(index=diameters, columns=lengths, fill_value=0.0).to_numpy()

    truth = _pivot(truth_block, diameters, lengths)
    estimate = on_axes(m.delivered)
    price = prices.grid(m.sortiment, m.destination, diameters, lengths)

    true_price = float((_shares(truth) * price).sum())
    estimate_price = float((_shares(estimate) * price).sum())
    true_value = float((truth * price).sum())
    cell_coverage = value_coverage = np.nan
    if total_draws is not None:
        low, high = on_axes(np.quantile(total_draws, 0.05, axis=0)), on_axes(np.quantile(total_draws, 0.95, axis=0))
        # Half a thousandth of a cell is rounding noise, not a covered prediction.
        active = (truth > 0) | (estimate > 0.05)
        inside = (truth >= low - 1e-9) & (truth <= high + 1e-9)
        if truth[active].sum():
            cell_coverage = float(truth[active & inside].sum() / truth[active].sum())
        values = (total_draws * prices.grid(m.sortiment, m.destination, m.grid.diameters, m.grid.lengths)).sum(axis=(1, 2))
        value_low, value_high = np.quantile(values, [0.05, 0.95])
        value_coverage = float(value_low <= true_value <= value_high)

    row = {
        "period": month.period,
        DEST: m.destination,
        SORT: m.sortiment,
        "levererat_facit": float(truth.sum()),
        "levererat_matt": float(estimate.sum()),
        "fel_placerad_andel": 0.5 * float(np.abs(_shares(estimate) - _shares(truth)).sum()),
        "prisfel_kr_m3": estimate_price - true_price,
        "cell_tackning_90": cell_coverage,
        "varde_inom_90": value_coverage,
        "andel_s1": float(m.by_tier["S1"].sum() / estimate.sum()) if estimate.sum() > 0 else np.nan,
    }
    if naive is not None:
        naive_values = m.frame(naive).reindex(index=diameters, columns=lengths, fill_value=0.0).to_numpy()
        row["fel_placerad_andel_naiv"] = 0.5 * float(np.abs(_shares(naive_values) - _shares(truth)).sum())
        row["prisfel_kr_m3_naiv"] = float((_shares(naive_values) * price).sum()) - true_price
    return row


def run_backtest(params: SimParams, model: Model, burn_in: int = 2) -> BacktestResult:
    prices = PriceList.from_frame(example_price_list())
    ledger = Ledger.empty()
    rows = []
    for month in simulate(params):
        harvest = validate_harvest(month.harvest, month.period)
        deliveries = validate_deliveries(month.deliveries, month.period)
        output = evaluate_month(ledger, harvest, deliveries, month.period, month.transport_done, model)
        ledger = output.step.ledger

        for m in output.matrices.values():
            if m.delivered.sum() <= 0:
                continue
            # The obvious shortcut: this month's harvest, ignoring the lag.
            naive = m.harvested if m.harvested.sum() > 0 else None
            rows.append(_score(month, m, prices, naive, output.draws))

    per_month = pd.DataFrame(rows)
    periods = sorted(per_month["period"].unique())
    settled = per_month[per_month["period"].isin(periods[burn_in:])]
    weights = settled["levererat_facit"]

    def weighted(column: str) -> float:
        usable = settled[column].notna()
        return float(np.average(settled.loc[usable, column].abs(), weights=weights[usable]))

    summary = {
        "manader_utvarderade": float(len(periods) - burn_in),
        "volym_m3fub": float(weights.sum()),
        "andel_s1": float(np.average(settled["andel_s1"], weights=weights)),
        "fel_placerad_andel": weighted("fel_placerad_andel"),
        "fel_placerad_andel_naiv": weighted("fel_placerad_andel_naiv"),
        "prisfel_kr_m3": weighted("prisfel_kr_m3"),
        "prisfel_kr_m3_naiv": weighted("prisfel_kr_m3_naiv"),
        "cell_tackning_90": float(np.average(settled["cell_tackning_90"], weights=weights)),
        "varde_inom_90": float(settled["varde_inom_90"].mean()),
    }
    return BacktestResult(per_month, summary)
