"""Monthly allocation of delivered volume onto diameter × length classes.

The delivery measurement decides how much was delivered per work order and
assortment. The harvester data decides how that volume is distributed. Each
allocated volume gets a certainty class by where its distribution came from:

    S1  the work order's own unconsumed harvester stock
    S2  the work order's harvest history (more delivered than stock)
    S3  other work orders of the same assortment (no harvester data for this one)
    S4  nothing to go on; booked on the OKÄND class

S2-S4 volumes are provisional. They stay in the ledger's deficit, and when
harvester data arrives later the difference is booked as a correction.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from .config import Config
from .ledger import DEFICIT_COLUMNS, HISTORY_COLUMNS, STOCK_COLUMNS, Ledger, merge, take
from .schema import AO, DIA, LEN, LOGS, SORT, TIER, UNKNOWN_CLASS, VINTAGE, VOL

CERTAINTY_TIERS = ("S1", "S2", "S3", "S4")
TIER_NAMES = {
    "S1": "Skördarmätt, eget lager",
    "S2": "Skördarmätt, AO-historik",
    "S3": "Sortimentspool",
    "S4": "Okänd fördelning",
}


@dataclass(frozen=True)
class Component:
    """One allocated volume with its composition, input to the Monte Carlo.

    The composition is drawn from Dirichlet(concentration * q), where an
    infinite concentration means it is known (the whole stock was delivered).
    With `donors`, one row per similar work order, a draw is instead a whole
    donor's composition: stands differ by shifting the entire distribution, so
    neighbouring classes move together in a way a Dirichlet cannot express.
    """

    ao: str
    sortiment: str
    tier: str
    volume: float
    diameters: tuple[str, ...]
    lengths: tuple[str, ...]
    q: np.ndarray
    concentration: float
    harvester_based: bool
    donors: np.ndarray | None = None
    donor_weights: np.ndarray | None = None


@dataclass(frozen=True)
class Pool:
    """Harvest history of one assortment, all work orders on the same cells."""

    shares: pd.Series
    donors: np.ndarray
    donor_weights: np.ndarray


@dataclass
class MonthStep:
    period: str
    harvest: pd.DataFrame
    allocation: pd.DataFrame
    corrections: pd.DataFrame
    reconciliation: pd.DataFrame
    components: list[Component]
    ledger: Ledger


def _composition(block: pd.DataFrame) -> pd.Series:
    """Volume shares per (diameter, length)."""
    summed = block.groupby([DIA, LEN], sort=True)[VOL].sum()
    return summed / summed.sum()


def _build_pool(history: pd.DataFrame) -> Pool:
    per_ao = history.pivot_table(index=AO, columns=[DIA, LEN], values=VOL, aggfunc="sum", fill_value=0.0)
    per_ao.columns.names = [DIA, LEN]
    totals = per_ao.sum(axis=1).to_numpy()
    shares = per_ao.sum(axis=0) / totals.sum()
    return Pool(shares, per_ao.to_numpy() / totals[:, None], totals / totals.sum())


def _calibrated_harvest(harvest: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    return harvest.assign(**{VOL: harvest[VOL] * cfg.calibration})


def _component(
    key: tuple[str, str], tier: str, volume: float, shares: pd.Series, concentration: float, harvester_based: bool
) -> Component:
    return Component(
        ao=key[0],
        sortiment=key[1],
        tier=tier,
        volume=volume,
        diameters=tuple(shares.index.get_level_values(0)),
        lengths=tuple(shares.index.get_level_values(1)),
        q=shares.to_numpy(dtype=float),
        concentration=concentration,
        harvester_based=harvester_based,
    )


def _own_stock_concentration(taken: pd.DataFrame, delivered: float, available: float, cfg: Config) -> float:
    """Precision of a draw from the stock, a cluster sample without replacement.

    Logs travel in piles, hence the design effect. The finite population
    correction makes the composition certain once the whole stock is delivered.
    """
    remaining_share = 1 - delivered / available
    if remaining_share <= 1e-9:
        return float("inf")

    logs = taken[LOGS].sum(min_count=len(taken))
    mean_log = delivered / logs if logs > 0 else cfg.default_log_volume
    effective = max(delivered / mean_log / cfg.design_effect, 1.0)
    return max(effective / remaining_share - 1, 1.0)


def _unknown_shares() -> pd.Series:
    index = pd.MultiIndex.from_tuples([(UNKNOWN_CLASS, UNKNOWN_CLASS)], names=[DIA, LEN])
    return pd.Series([1.0], index=index)


def close_month(
    ledger: Ledger,
    harvest: pd.DataFrame,
    deliveries: pd.DataFrame,
    period: str,
    closed_aos: set[str],
    cfg: Config,
) -> MonthStep:
    """Roll the ledger through one month and allocate its deliveries."""
    if ledger.period is not None and ledger.period >= period:
        raise ValueError(f"Liggaren är redan stängd för {ledger.period}, kan inte stänga {period}")

    calibrated = _calibrated_harvest(harvest, cfg)
    stock_keys = [AO, SORT, DIA, LEN, VINTAGE]
    history_keys = [AO, SORT, DIA, LEN]
    stock = merge([ledger.stock, calibrated[STOCK_COLUMNS]], stock_keys, STOCK_COLUMNS)
    history = merge([ledger.history, calibrated[HISTORY_COLUMNS]], history_keys, HISTORY_COLUMNS)

    pools = {s: _build_pool(block) for s, block in history.groupby(SORT, sort=False)}

    stock_by_key = dict(tuple(stock.groupby([AO, SORT], sort=False)))
    history_by_key = dict(tuple(history.groupby([AO, SORT], sort=False)))
    deficit_by_key = dict(tuple(ledger.deficit.groupby([AO, SORT], sort=False)))
    harvested = calibrated.groupby([AO, SORT], sort=False)[VOL].sum()
    delivered = deliveries.groupby([AO, SORT], sort=False)[VOL].sum()

    empty_stock = stock.iloc[0:0]
    empty_deficit = ledger.deficit.iloc[0:0]
    keys = sorted(set(stock_by_key) | set(deficit_by_key) | set(delivered.index))

    allocations: list[pd.DataFrame] = []
    corrections: list[pd.DataFrame] = []
    closing_stock: list[pd.DataFrame] = []
    closing_deficit: list[pd.DataFrame] = []
    components: list[Component] = []
    reconciliation: list[dict] = []

    def book(key: tuple[str, str], tier: str, volume: float, shares: pd.Series) -> pd.DataFrame:
        cells = (volume * shares).rename(VOL).reset_index()
        allocations.append(cells.assign(**{AO: key[0], SORT: key[1], TIER: tier}))
        return cells.assign(**{AO: key[0], SORT: key[1]})

    for key in keys:
        block = stock_by_key.get(key, empty_stock)
        owed = deficit_by_key.get(key, empty_deficit)
        opening = float(block[VOL].sum()) - float(harvested.get(key, 0.0))

        # Harvester data for wood already invoiced provisionally settles that first.
        corrected = 0.0
        if len(owed) and len(block):
            owed_total = float(owed[VOL].sum())
            corrected = min(owed_total, float(block[VOL].sum()))
            taken, block = take(block, corrected, cfg.draw_policy)
            actual = taken.groupby([DIA, LEN], sort=False, as_index=False)[VOL].sum()
            fraction = corrected / owed_total
            released = owed.assign(**{VOL: -owed[VOL] * fraction})[[DIA, LEN, VOL]]
            net = pd.concat([actual, released]).groupby([DIA, LEN], sort=False, as_index=False)[VOL].sum()
            corrections.append(net.assign(**{AO: key[0], SORT: key[1]}))
            owed = owed.assign(**{VOL: owed[VOL] * (1 - fraction)})
            owed = owed[owed[VOL] > 1e-9]

        volume = float(delivered.get(key, 0.0))
        available = float(block[VOL].sum())
        covered = 0.0
        if volume > 0:
            if available > 0 and volume <= available * (1 + cfg.coverage_tolerance):
                taken, block = take(block, min(volume, available), cfg.draw_policy)
                shares = _composition(taken)
                concentration = _own_stock_concentration(taken, min(volume, available), available, cfg)
                book(key, "S1", volume, shares)
                components.append(_component(key, "S1", volume, shares, concentration, True))
                covered = volume
            else:
                if available > 0:
                    taken, block = take(block, available, cfg.draw_policy)
                    shares = _composition(taken)
                    book(key, "S1", available, shares)
                    components.append(_component(key, "S1", available, shares, float("inf"), True))
                    covered = available

                shortfall = volume - available
                donors = None
                if key in history_by_key:
                    tier, shares = "S2", _composition(history_by_key[key])
                    concentration, harvester_based = cfg.history_concentration, True
                elif key[1] in pools:
                    pool = pools[key[1]]
                    tier, shares = "S3", pool.shares
                    concentration, harvester_based = cfg.pool_concentration_default, False
                    donors = pool if len(pool.donors) >= cfg.pool_min_donors else None
                else:
                    tier, shares = "S4", _unknown_shares()
                    concentration, harvester_based = float("inf"), False
                provisional = book(key, tier, shortfall, shares)
                part = _component(key, tier, shortfall, shares, concentration, harvester_based)
                if donors is not None:
                    part = replace(part, donors=donors.donors, donor_weights=donors.donor_weights)
                components.append(part)
                owed = merge([owed, provisional[DEFICIT_COLUMNS]], [AO, SORT, DIA, LEN], DEFICIT_COLUMNS)

        written_off = 0.0
        if key[0] in closed_aos:
            written_off = float(block[VOL].sum())
            block = empty_stock
            owed = empty_deficit

        closing_stock.append(block)
        closing_deficit.append(owed)
        reconciliation.append(
            {
                AO: key[0],
                SORT: key[1],
                "ingaende_lager": opening,
                "skordat_kalibrerat": float(harvested.get(key, 0.0)),
                "levererat": volume,
                "tackning_s1": covered / volume if volume > 0 else np.nan,
                "korrigerat": corrected,
                "utgaende_lager": float(block[VOL].sum()),
                "underskott": float(owed[VOL].sum()),
                "avskrivet": written_off,
            }
        )

    allocation_columns = [AO, SORT, DIA, LEN, TIER, VOL]
    correction_columns = [AO, SORT, DIA, LEN, VOL]
    allocation = (
        pd.concat(allocations, ignore_index=True)[allocation_columns]
        if allocations
        else pd.DataFrame(columns=allocation_columns)
    )
    correction = (
        pd.concat(corrections, ignore_index=True)[correction_columns]
        if corrections
        else pd.DataFrame(columns=correction_columns)
    )

    return MonthStep(
        period=period,
        harvest=harvest,
        allocation=allocation,
        corrections=correction,
        reconciliation=pd.DataFrame(reconciliation),
        components=components,
        ledger=Ledger(
            period,
            merge(closing_stock, stock_keys, STOCK_COLUMNS),
            history,
            merge(closing_deficit, history_keys, DEFICIT_COLUMNS),
        ),
    )
