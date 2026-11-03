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
from .ledger import DEFICIT_COLUMNS, HISTORY_COLUMNS, STOCK_COLUMNS, Ledger, merge, split, take
from .schema import (
    AO,
    BRUTTO,
    DEST,
    DIA,
    LEN,
    LOGS,
    NO_DESTINATION,
    SORT,
    TIER,
    UNKNOWN_CLASS,
    VINTAGE,
    VOL,
    WorkOrders,
)

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

    A draw first picks a mean composition, then adds Dirichlet noise with
    `concentration` around it (infinite when the composition is known).

    Without `mixture` the mean is `q`. With it, the mean is built from rows of
    whole compositions, because neighbouring classes move together: within a
    work order the rows are parts of the harvest, weighted by Dirichlet with
    `mixture_concentration`. Among work orders, where that is None, a draw is
    one donor's composition.
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
    mixture: np.ndarray | None = None
    mixture_weights: np.ndarray | None = None
    mixture_concentration: float | None = None
    destination: str = NO_DESTINATION


@dataclass(frozen=True)
class Pool:
    """Harvest history of comparable work orders, all on the same cells."""

    cells: pd.MultiIndex
    donors: np.ndarray
    donor_weights: np.ndarray
    work_orders: tuple[str, ...] = ()


@dataclass
class MonthStep:
    period: str
    harvest: pd.DataFrame
    allocation: pd.DataFrame
    corrections: pd.DataFrame
    reconciliation: pd.DataFrame
    components: list[Component]
    ledger: Ledger
    work_orders: WorkOrders


def _composition(block: pd.DataFrame) -> pd.Series:
    """Volume shares per (diameter, length)."""
    summed = block.groupby([DIA, LEN], sort=True)[VOL].sum()
    return summed / summed.sum()


def _build_pool(history: pd.DataFrame) -> Pool:
    per_ao = history.pivot_table(index=AO, columns=[DIA, LEN], values=VOL, aggfunc="sum", fill_value=0.0)
    per_ao.columns.names = [DIA, LEN]
    totals = per_ao.sum(axis=1).to_numpy()
    return Pool(per_ao.columns, per_ao.to_numpy() / totals[:, None], totals / totals.sum(), tuple(per_ao.index))


def _draw_fractions(block: pd.DataFrame, dated: pd.DataFrame, volume: float, cfg: Config) -> np.ndarray:
    """Share of each stock row taken by the month's deliveries.

    Wood cannot leave before it is harvested and forwarded, so each delivery
    draws pro rata from what existed on its date. What dates cannot place, for
    instance because a harvest date is off, is taken pro rata from the rest.
    """
    stock = block[VOL].to_numpy(dtype=float)
    if cfg.draw_policy == "proportional":
        return np.full(len(stock), min(volume / stock.sum(), 1.0))

    left = stock.copy()
    harvested = pd.to_datetime(block[VINTAGE]).to_numpy("datetime64[D]").astype(np.int64)
    days = dated["leveransdatum"].to_numpy("datetime64[D]").astype(np.int64)
    amounts = dated[BRUTTO].to_numpy(dtype=float) * volume / float(dated[BRUTTO].sum())

    unplaced = 0.0
    for j in np.argsort(days, kind="stable"):
        weight = left * (harvested <= days[j] - cfg.min_forwarding_days)
        available = weight.sum()
        used = min(amounts[j], available)
        if available > 0:
            left -= weight * used / available
        unplaced += amounts[j] - used

    remaining = left.sum()
    if unplaced > 1e-12 and remaining > 0:
        left *= max(1 - unplaced / remaining, 0.0)
    return np.clip(1 - left / stock, 0.0, 1.0)


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


def _stock_component(
    key: tuple[str, str], taken: pd.DataFrame, volume: float, harvested: float, cfg: Config
) -> Component:
    """How well a draw from the stock is known.

    What the month's deliveries leave out of the whole harvest is the finite
    population correction, so sampling uncertainty disappears only if all of it
    leaves in one month. Emptying a stock in a second month does not count: that
    remainder is the harvest minus an uncertain first part. The harvester's
    classing of each log stays uncertain, which caps the precision at one
    independent error per log. Logs travel in piles and piles come from one
    part of the stand, so sampling has two levels: which parts of the harvest
    left, measured as compositions of harvest date blocks, and noise within them.
    """
    shares = _composition(taken)
    logs = taken[LOGS].sum(min_count=1)
    log_count = logs if logs > 0 else volume / cfg.default_log_volume
    remaining_share = max(1 - volume / harvested, 0.0)
    if remaining_share <= 1e-9:
        return _component(key, "S1", volume, shares, float(log_count), True)

    effective = max(log_count / cfg.design_effect, 1.0)
    concentration = min(max(effective / remaining_share - 1, 1.0), float(log_count))
    part = _component(key, "S1", volume, shares, concentration, True)

    days = pd.to_datetime(taken[VINTAGE]).to_numpy("datetime64[D]").astype(np.int64)
    blocks = taken.assign(_block=days // cfg.stock_block_days)
    if blocks["_block"].nunique() < 2:
        return part
    matrix = blocks.pivot_table(index="_block", columns=[DIA, LEN], values=VOL, aggfunc="sum", fill_value=0.0)
    matrix = matrix.reindex(columns=shares.index, fill_value=0.0)
    totals = matrix.sum(axis=1).to_numpy()
    clusters = max(volume / cfg.cluster_volume, 1.0)
    return replace(
        part,
        mixture=matrix.to_numpy() / totals[:, None],
        mixture_weights=totals / totals.sum(),
        mixture_concentration=max(clusters / remaining_share - 1, cfg.mixture_min_concentration),
    )


def _unknown_shares() -> pd.Series:
    index = pd.MultiIndex.from_tuples([(UNKNOWN_CLASS, UNKNOWN_CLASS)], names=[DIA, LEN])
    return pd.Series([1.0], index=index)


def _mean_diameters(history: pd.DataFrame) -> dict[tuple[str, str], float]:
    """Volume weighted mean diameter class per work order and assortment."""
    diameters = pd.to_numeric(history[DIA], errors="coerce")
    known = history.assign(_volume_cm=diameters * history[VOL])[diameters.notna()]
    summed = known.groupby([AO, SORT], sort=False)[["_volume_cm", VOL]].sum()
    return (summed["_volume_cm"] / summed[VOL]).to_dict()


def _donor_weights(
    key: tuple[str, str],
    destination: str,
    pool: Pool,
    work_orders: WorkOrders,
    mean_diameters: dict[tuple[str, str], float],
    cfg: Config,
) -> np.ndarray:
    """How much each work order counts as a donor: soft nearest neighbours.

    All donors take part, weighted by volume and by what is known to resemble
    the work order. Its other assortments say most: a stand with thick spruce
    tends to have thick pine, so the difference between the assortments on
    other work orders predicts the missing one.
    """
    group = work_orders.groups.get(key[0])
    same_destination = np.array([work_orders.destinations.get(a) == destination for a in pool.work_orders])
    same_group = np.array([group is not None and work_orders.groups.get(a) == group for a in pool.work_orders])
    weights = pool.donor_weights.copy()
    weights *= np.where(same_destination, cfg.donor_destination_weight, 1.0)
    weights *= np.where(same_group, cfg.donor_group_weight, 1.0)

    siblings = sorted(s for a, s in mean_diameters if a == key[0] and s != key[1])
    if siblings and cfg.donor_sibling_cm > 0:
        sibling = siblings[0]
        own = np.array([mean_diameters.get((a, key[1]), np.nan) for a in pool.work_orders])
        other = np.array([mean_diameters.get((a, sibling), np.nan) for a in pool.work_orders])
        both = ~np.isnan(own) & ~np.isnan(other)
        if both.sum() >= cfg.pool_min_pairs:
            expected = mean_diameters[(key[0], sibling)] + float((own[both] - other[both]).mean())
            known = ~np.isnan(own)
            weights[known] *= np.exp(-0.5 * ((own[known] - expected) / cfg.donor_sibling_cm) ** 2)
    total = weights.sum()
    return weights / total if total > 0 else pool.donor_weights


def _pool_component(
    key: tuple[str, str], volume: float, pool: Pool, weights: np.ndarray, cfg: Config
) -> tuple[pd.Series, Component]:
    """Distribution of wood without harvester data, from comparable work orders."""
    shares = pd.Series(weights @ pool.donors, index=pool.cells)
    shares = shares[shares > 0]
    part = _component(key, "S3", volume, shares, cfg.pool_concentration_default, False)
    if len(pool.donors) < cfg.pool_min_donors:
        return shares, part
    return shares, replace(
        part,
        concentration=float("inf"),
        mixture=pool.donors[:, pool.cells.get_indexer(shares.index)],
        mixture_weights=weights,
    )


def close_month(
    ledger: Ledger,
    harvest: pd.DataFrame,
    deliveries: pd.DataFrame,
    period: str,
    closed_aos: set[str],
    cfg: Config,
    work_orders: WorkOrders | None = None,
) -> MonthStep:
    """Roll the ledger through one month and allocate its deliveries.

    The ledger is shared by all destinations: a work order's stock is one pile
    of wood wherever it goes. Volume delivered to several destinations from one
    work order is split by net volume.

    Wood without harvester data borrows from comparable work orders, see
    `_donor_weights`.
    """
    if ledger.period is not None and ledger.period >= period:
        raise ValueError(f"Liggaren är redan stängd för {ledger.period}, kan inte stänga {period}")
    work_orders = work_orders or WorkOrders()

    calibrated = harvest.assign(**{VOL: harvest[VOL] * cfg.calibration})
    stock_keys = [AO, SORT, DIA, LEN, VINTAGE]
    history_keys = [AO, SORT, DIA, LEN]
    stock = merge([ledger.stock, calibrated[STOCK_COLUMNS]], stock_keys, STOCK_COLUMNS)
    history = merge([ledger.history, calibrated[HISTORY_COLUMNS]], history_keys, HISTORY_COLUMNS)

    pools = {s: _build_pool(block) for s, block in history.groupby(SORT, sort=False)}
    mean_diameters = _mean_diameters(history)

    stock_by_key = dict(tuple(stock.groupby([AO, SORT], sort=False)))
    history_by_key = dict(tuple(history.groupby([AO, SORT], sort=False)))
    deficit_by_key = dict(tuple(ledger.deficit.groupby([AO, SORT], sort=False)))
    harvested = calibrated.groupby([AO, SORT], sort=False)[VOL].sum()
    delivered = deliveries.groupby([AO, SORT], sort=False)[VOL].sum()
    physical = deliveries.groupby([AO, SORT], sort=False)[BRUTTO].sum()
    dated_by_key = dict(tuple(deliveries.groupby([AO, SORT], sort=False)))
    split_by_key = {
        key: block.groupby(DEST, sort=True)[VOL].sum() / block[VOL].sum()
        for key, block in dated_by_key.items()
        if block[VOL].sum() > 0
    }

    empty_stock = stock.iloc[0:0]
    empty_deficit = ledger.deficit.iloc[0:0]
    keys = sorted(set(stock_by_key) | set(deficit_by_key) | set(delivered.index))

    allocations: list[pd.DataFrame] = []
    corrections: list[pd.DataFrame] = []
    closing_stock: list[pd.DataFrame] = []
    closing_deficit: list[pd.DataFrame] = []
    components: list[Component] = []
    reconciliation: list[dict] = []

    def book(key: tuple[str, str], part: Component, shares: pd.Series) -> pd.DataFrame:
        """Record a volume per destination, returning what was booked."""
        booked = []
        for destination, share in split_by_key[key].items():
            cells = (part.volume * share * shares).rename(VOL).rename_axis([DIA, LEN]).reset_index()
            booked.append(cells.assign(**{AO: key[0], SORT: key[1], DEST: destination}))
            components.append(replace(part, destination=destination, volume=part.volume * share))
        rows = pd.concat(booked, ignore_index=True)
        allocations.append(rows.assign(**{TIER: part.tier}))
        return rows

    for key in keys:
        block = stock_by_key.get(key, empty_stock)
        owed = deficit_by_key.get(key, empty_deficit)
        opening = float(block[VOL].sum()) - float(harvested.get(key, 0.0))

        # Harvester data for wood already invoiced provisionally settles that first.
        corrected = 0.0
        if len(owed) and len(block):
            owed_total = float(owed[VOL].sum())
            corrected = min(owed_total, float(block[VOL].sum()))
            taken, block = take(block, corrected)
            actual = taken.groupby([DIA, LEN], sort=False, as_index=False)[VOL].sum()
            fraction = corrected / owed_total
            released = owed.assign(**{VOL: -owed[VOL] * fraction})[[DEST, DIA, LEN, VOL]]
            for destination, unsettled in released.groupby(DEST, sort=False):
                earned = actual.assign(**{VOL: actual[VOL] * unsettled[VOL].sum() / released[VOL].sum()})
                changes = pd.concat([earned, unsettled[[DIA, LEN, VOL]]])
                net_change = changes.groupby([DIA, LEN], sort=False, as_index=False)[VOL].sum()
                corrections.append(net_change.assign(**{AO: key[0], SORT: key[1], DEST: destination}))
            owed = owed.assign(**{VOL: owed[VOL] * (1 - fraction)})
            owed = owed[owed[VOL] > 1e-9]

        # Gross volume left the stock. Net volume is what is measured for payment.
        net = float(delivered.get(key, 0.0))
        volume = float(physical.get(key, 0.0))
        net_share = net / volume if volume > 0 else 1.0
        available = float(block[VOL].sum())
        covered = 0.0
        if volume > 0:
            if available > 0:
                drawn = min(volume, available)
                fraction = _draw_fractions(block, dated_by_key[key], drawn, cfg)
                taken, block = split(block, fraction)
                covered = volume if volume <= available * (1 + cfg.coverage_tolerance) else available
                if net > 0:
                    harvested_total = max(float(history_by_key[key][VOL].sum()), drawn)
                    part = _stock_component(key, taken, drawn, harvested_total, cfg)
                    book(key, replace(part, volume=covered * net_share), _composition(taken))

            shortfall = volume - covered
            if shortfall > 0 and net > 0:
                billed = shortfall * net_share
                if key in history_by_key:
                    shares = _composition(history_by_key[key])
                    part = _component(key, "S2", billed, shares, cfg.history_concentration, True)
                elif key[1] in pools:
                    destination = work_orders.destinations.get(key[0], split_by_key[key].index[0])
                    pool = pools[key[1]]
                    weights = _donor_weights(key, destination, pool, work_orders, mean_diameters, cfg)
                    shares, part = _pool_component(key, billed, pool, weights, cfg)
                else:
                    shares = _unknown_shares()
                    part = _component(key, "S4", billed, shares, float("inf"), False)
                provisional = book(key, part, shares)
                unsettled = provisional.assign(**{VOL: provisional[VOL] / net_share})
                owed = merge([owed, unsettled[DEFICIT_COLUMNS]], [AO, SORT, DEST, DIA, LEN], DEFICIT_COLUMNS)

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
                "levererat": net,
                "levererat_brutto": volume,
                "tackning_s1": covered / volume if volume > 0 else np.nan,
                "korrigerat": corrected,
                "utgaende_lager": float(block[VOL].sum()),
                "underskott": float(owed[VOL].sum()),
                "avskrivet": written_off,
            }
        )

    allocation_columns = [AO, SORT, DEST, DIA, LEN, TIER, VOL]
    correction_columns = [AO, SORT, DEST, DIA, LEN, VOL]
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
            merge(closing_deficit, [AO, SORT, DEST, DIA, LEN], DEFICIT_COLUMNS),
        ),
        work_orders=work_orders,
    )
