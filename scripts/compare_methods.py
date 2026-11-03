"""Compare three ways of estimating the month's delivery matrices against the facit.

Matrices are per destination and assortment.

    A  ledger        mass balance per work order, assortment pool for missing data
    B  convolution   no work orders: harvest smeared over a storage time distribution
    C  ledger+       A, with missing data borrowed from comparable work orders

Run from the repository root:

    uv run python scripts/compare_methods.py --out docs/metodjamforelse_resultat.csv
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from math import erfc
from pathlib import Path

import numpy as np
import pandas as pd

from treedist.backtest import _score
from treedist.config import Config
from treedist.invoice import PriceList
from treedist.ledger import Ledger
from treedist.pipeline import run_month
from treedist.schema import AO, DEST, DIA, LEN, SORT, TIER, VINTAGE, VOL, validate_deliveries, validate_harvest
from treedist.simulate import SimMonth, SimParams, example_price_list, simulate

SCENARIOS = {
    "bas": {},
    "30 % utan skördardata": {"no_harvester_data_share": 0.30},
    "stora skillnader inom AO": {"landing_diameter_sd": 0.20},
}
# Fresh seeds for each final check; earlier ones were 61-68.
SEEDS = (71, 72, 73, 74, 75, 76, 77, 78)
BURN_IN = 2
LAG_MEDIAN_DAYS = 32.0
LAG_SIGMA = 0.6

def _lag_cdf(age: np.ndarray) -> np.ndarray:
    """Share of wood that has left after `age` days."""
    z = (np.log(np.maximum(age, 0.5)) - np.log(LAG_MEDIAN_DAYS)) / LAG_SIGMA
    return 1 - 0.5 * np.vectorize(erfc)(z / np.sqrt(2))


def _index(estimate: pd.Series, truth: pd.Series) -> float:
    """Half the summed difference in shares: Reynolds' error index on volume."""
    joined = pd.concat([estimate, truth], axis=1, keys=["e", "t"]).fillna(0.0)
    return 0.5 * float((joined["e"] / joined["e"].sum() - joined["t"] / joined["t"].sum()).abs().sum())


def _month_scores(estimate: pd.DataFrame, truth: pd.DataFrame, prices: PriceList) -> dict[str, float]:
    e = estimate.groupby([DEST, SORT, DIA, LEN])[VOL].sum()
    t = truth.groupby([DEST, SORT, DIA, LEN])[VOL].sum()
    rows = []
    for key in t.index.droplevel([2, 3]).unique():
        if key not in e.index.droplevel([2, 3]):
            continue
        es, ts = e.xs(key, level=(0, 1)), t.xs(key, level=(0, 1))
        joined = pd.concat([es, ts], axis=1, keys=["e", "t"]).fillna(0.0)
        price = np.array([(prices.price_ore(key[1], d, l, key[0]) or 0) / 100 for d, l in joined.index])
        rows.append(
            {
                "vikt": float(ts.sum()),
                "index_matris": _index(es, ts),
                "index_diameter": _index(es.groupby(level=0).sum(), ts.groupby(level=0).sum()),
                "prisfel": abs(float((joined["e"] / joined["e"].sum() * price).sum() - (joined["t"] / joined["t"].sum() * price).sum())),
            }
        )
    frame = pd.DataFrame(rows)
    return {c: float(np.average(frame[c], weights=frame["vikt"])) for c in frame.columns if c != "vikt"}


def _work_order_scores(allocation: pd.DataFrame, truth: pd.DataFrame) -> dict[str, list[tuple[float, float]]]:
    """Diameter index per work order and assortment, split by where the data came from."""
    out: dict[str, list[tuple[float, float]]] = {"S1": [], "S3": []}
    tiers = allocation.groupby([AO, SORT, TIER])[VOL].sum().unstack(fill_value=0.0)
    estimated = allocation.groupby([AO, SORT, DIA])[VOL].sum()
    actual = truth.groupby([AO, SORT, DIA])[VOL].sum()
    for key in tiers.index:
        if key not in actual.index.droplevel(2):
            continue
        row = tiers.loc[key]
        tier = next((t for t in ("S1", "S3") if t in row.index and row[t] / row.sum() > 0.95), None)
        if tier:
            volume = float(actual.xs(key, level=(0, 1)).sum())
            out[tier].append((_index(estimated.xs(key, level=(0, 1)), actual.xs(key, level=(0, 1))), volume))
    return out


def _convolved(month: SimMonth, history: pd.DataFrame, deliveries: pd.DataFrame) -> pd.DataFrame:
    """Method B: each harvest date contributes what the lag says left this month."""
    start, end = pd.Period(month.period, freq="M").start_time, pd.Period(month.period, freq="M").end_time.normalize()
    dates = pd.to_datetime(history[VINTAGE])
    age_end = np.maximum((end - dates).dt.days.to_numpy(dtype=float), 0.0)
    age_start = np.maximum((start - dates).dt.days.to_numpy(dtype=float), 0.0)
    weighted = history.assign(_w=history[VOL] * (_lag_cdf(age_end) - _lag_cdf(age_start)))
    weighted = weighted.groupby([DEST, SORT, DIA, LEN], as_index=False)["_w"].sum()
    totals = deliveries.groupby(["mottagningsplats", SORT])[VOL].sum().rename_axis([DEST, SORT]).rename("_total")
    weighted = weighted.join(totals, on=[DEST, SORT])
    weighted[VOL] = weighted["_w"] / weighted.groupby([DEST, SORT])["_w"].transform("sum") * weighted["_total"]
    return weighted.dropna(subset=[VOL])[[DEST, SORT, DIA, LEN, VOL]]


def _run_ledger(months: list[SimMonth], cfg: Config, prices: PriceList, advanced: bool, collect) -> None:
    if not advanced:
        cfg = replace(cfg, donor_destination_weight=1.0, donor_group_weight=1.0, donor_sibling_cm=0.0)
    ledger = Ledger.empty()
    for index, month in enumerate(months):
        harvest = validate_harvest(month.harvest, month.period)
        known = month.work_orders
        deliveries = validate_deliveries(month.deliveries, month.period, cfg, known)
        output = run_month(ledger, harvest, deliveries, prices, month.period, month.closed_aos, cfg, known)
        ledger = output.step.ledger
        if index >= BURN_IN:
            collect(month, output)


def evaluate(scenario: str, overrides: dict, seed: int, cfg: Config, prices: PriceList) -> list[dict]:
    months = simulate(SimParams(months=12, seed=seed, **overrides))
    rows = []

    for name, advanced in (("A liggare", False), ("C liggare+", True)):
        month_rows, tiers = [], {"S1": [], "S3": []}
        allocated, delivered = [], []

        def collect(month: SimMonth, output) -> None:
            scores = _month_scores(output.step.allocation, month.truth, prices)
            covered = [
                _score(month, m, prices, None) for m in output.matrices.values() if m.delivered.sum() > 0
            ]
            weights = [c["levererat_facit"] for c in covered]
            scores["cell_90"] = float(np.average([c["cell_tackning_90"] for c in covered], weights=weights))
            scores["varde_90"] = float(np.mean([c["varde_inom_90"] for c in covered]))
            scores["andel_s1"] = float(np.average([c["andel_s1"] for c in covered], weights=weights))
            month_rows.append(scores)
            allocated.append(output.step.allocation)
            delivered.append(month.truth)
            for tier, values in _work_order_scores(output.step.allocation, month.truth).items():
                tiers[tier].extend(values)

        _run_ledger(months, cfg, prices, advanced, collect)
        row = pd.DataFrame(month_rows).mean().to_dict()
        whole = _month_scores(pd.concat(allocated), pd.concat(delivered), prices)
        row["kum_index"] = whole["index_matris"]
        row["kum_prisfel"] = whole["prisfel"]
        for tier, values in tiers.items():
            row[f"ao_index_{tier}"] = float(np.average([v for v, _ in values], weights=[w for _, w in values])) if values else np.nan
        rows.append({"scenario": scenario, "seed": seed, "metod": name, **row})

    history = []
    convolved, naive = [], []
    for index, month in enumerate(months):
        harvest = month.harvest.astype({VOL: float})
        harvest = harvest.assign(**{DEST: harvest[AO].map(month.work_orders.destinations)})
        history.append(harvest)
        deliveries = month.deliveries
        if index >= BURN_IN:
            convolved.append(_month_scores(_convolved(month, pd.concat(history), deliveries), month.truth, prices))
            shares = harvest.groupby([DEST, SORT, DIA, LEN], as_index=False)[VOL].sum()
            naive.append(_month_scores(shares, month.truth, prices))
    rows.append({"scenario": scenario, "seed": seed, "metod": "B faltning", **pd.DataFrame(convolved).mean().to_dict()})
    rows.append({"scenario": scenario, "seed": seed, "metod": "Naiv", **pd.DataFrame(naive).mean().to_dict()})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("docs/metodjamforelse_resultat.csv"))
    parser.add_argument("--draws", type=int, default=500)
    args = parser.parse_args()

    cfg = Config(mc_draws=args.draws)
    prices = PriceList.from_frame(example_price_list())
    rows = []
    for scenario, overrides in SCENARIOS.items():
        for seed in SEEDS:
            rows.extend(evaluate(scenario, overrides, seed, cfg, prices))

    results = pd.DataFrame(rows)
    summary = results.drop(columns="seed").groupby(["scenario", "metod"], sort=False).mean().round(4)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.out)
    pd.set_option("display.width", 220, "display.max_columns", 30)
    print(summary.to_string())


if __name__ == "__main__":
    main()
