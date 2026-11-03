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

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from ..config import Config
from ..schema import (
    AO,
    BILLED,
    BRUTTO,
    DEST,
    DIA,
    LEN,
    LOGS,
    NO_DESTINATION,
    PRODUCED,
    SORT,
    TIER,
    UNKNOWN_CLASS,
    VINTAGE,
    VOL,
    WorkOrders,
)
from .ledger import (
    BILLED_COLUMNS,
    BILLED_KEYS,
    DEFICIT_COLUMNS,
    DEFICIT_KEYS,
    HISTORY_COLUMNS,
    STOCK_COLUMNS,
    Ledger,
    merge,
    split,
    take,
)

CERTAINTY_TIERS = ("S1", "S2", "S3", "S4")
CREDIT_COLUMNS = [AO, SORT, DEST, DIA, LEN, VOL]
TIER_NAMES = {
    "S1": "Skördardata, eget lager",
    "S2": "Skördardata, AO-historik",
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
    one donor's composition. With `donor_parts` the draw then takes a part of
    that donor's harvest, the same way as within a work order.
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
    donor_parts: tuple[tuple[np.ndarray, np.ndarray], ...] | None = None


@dataclass(frozen=True)
class Pool:
    """Harvest history of comparable work orders, all on the same cells.

    `parts` holds each donor's harvest date blocks: compositions and weights.
    """

    cells: pd.MultiIndex
    donors: np.ndarray
    donor_weights: np.ndarray
    work_orders: tuple[str, ...] = ()
    parts: tuple[tuple[np.ndarray, np.ndarray], ...] = ()


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
    # Loads reversed after the month they were invoiced in: negative volumes, on the invoice as KREDITERING.
    credits: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=CREDIT_COLUMNS))


def _composition(block: pd.DataFrame) -> pd.Series:
    """Volume shares per (diameter, length)."""
    summed = block.groupby([DIA, LEN], sort=True)[VOL].sum()
    return summed / summed.sum()


def _blocks(frame: pd.DataFrame, cells: pd.Index, cfg: Config) -> tuple[np.ndarray, np.ndarray]:
    """Compositions of the harvest date blocks on `cells`, and their volume weights."""
    days = pd.to_datetime(frame[VINTAGE]).to_numpy("datetime64[D]").astype(np.int64)
    blocks = frame.assign(_block=days // cfg.stock_block_days)
    matrix = blocks.pivot_table(index="_block", columns=[DIA, LEN], values=VOL, aggfunc="sum", fill_value=0.0)
    matrix = matrix.reindex(columns=cells, fill_value=0.0).to_numpy()
    totals = matrix.sum(axis=1)
    kept = totals > 0
    return matrix[kept] / totals[kept, None], totals[kept] / totals[kept].sum()


def _build_pool(history: pd.DataFrame, cfg: Config) -> Pool:
    per_ao = history.pivot_table(index=AO, columns=[DIA, LEN], values=VOL, aggfunc="sum", fill_value=0.0)
    per_ao.columns.names = [DIA, LEN]
    totals = per_ao.sum(axis=1).to_numpy()
    by_ao = dict(tuple(history.groupby(AO, sort=False)))
    parts = tuple(_blocks(by_ao[ao], per_ao.columns, cfg) for ao in per_ao.index)
    return Pool(per_ao.columns, per_ao.to_numpy() / totals[:, None], totals / totals.sum(), tuple(per_ao.index), parts)


def _part_concentrations(volume: float, log_count: float, remaining_share: float, cfg: Config) -> tuple[float, float]:
    """Precision of the cells and of the harvest blocks when part of a harvest left.

    What the deliveries leave out of the whole harvest is the finite population
    correction. Logs travel in piles from one part of the stand, so the
    effective number of independent logs is reduced by the design effect, and
    whole blocks of the harvest move together in clusters.
    """
    effective = max(log_count / cfg.design_effect, 1.0)
    cells = min(max(effective / remaining_share - 1, 1.0), float(log_count))
    clusters = max(volume / cfg.cluster_volume, 1.0)
    return cells, max(clusters / remaining_share - 1, cfg.mixture_min_concentration)


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

    # Trucks that start while the harvester is still there follow it, oldest wood first.
    dates, date_of = np.unique(harvested, return_inverse=True)
    oldest_first = cfg.overlap_fifo and days.min() <= harvested.max()

    unplaced = 0.0
    for j in np.argsort(days, kind="stable"):
        weight = left * (harvested <= days[j] - cfg.min_forwarding_days)
        available = weight.sum()
        used = min(amounts[j], available)
        if oldest_first:
            per_date = np.bincount(date_of, weights=weight, minlength=len(dates))
            taken = np.clip(used - (np.cumsum(per_date) - per_date), 0.0, per_date)
            share = np.divide(taken, per_date, out=np.zeros_like(per_date), where=per_date > 0)
            left -= weight * share[date_of]
        elif available > 0:
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
    independent error per log. Sampling has two levels: which parts of the
    harvest left, measured as compositions of harvest date blocks, and noise
    within them.
    """
    shares = _composition(taken)
    logs = taken[LOGS].sum(min_count=1)
    log_count = logs if logs > 0 else volume / cfg.default_log_volume
    remaining_share = max(1 - volume / harvested, 0.0)
    if remaining_share <= 1e-9:
        return _component(key, "S1", volume, shares, float(log_count), True)

    concentration, mixture_concentration = _part_concentrations(volume, log_count, remaining_share, cfg)
    part = _component(key, "S1", volume, shares, concentration, True)
    blocks, weights = _blocks(taken, shares.index, cfg)
    if len(weights) < 2:
        return part
    return replace(part, mixture=blocks, mixture_weights=weights, mixture_concentration=mixture_concentration)


def _history_component(
    key: tuple[str, str], volume: float, history: pd.DataFrame, shares: pd.Series, cfg: Config
) -> Component:
    """More delivered than the stock holds: wood the harvester data does not show yet.

    It is usually a part of the stand not reported yet, so a draw is a part of
    the work order's harvest rather than its average.
    """
    concentration, mixture_concentration = _part_concentrations(
        volume, volume / cfg.default_log_volume, cfg.pool_remaining_share, cfg
    )
    part = _component(key, "S2", volume, shares, concentration, True)
    blocks, weights = _blocks(history, shares.index, cfg)
    if len(weights) < 2:
        return part
    return replace(part, mixture=blocks, mixture_weights=weights, mixture_concentration=mixture_concentration)


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
            differences = own[both] - other[both]
            expected = mean_diameters[(key[0], sibling)] + float(differences.mean())
            # The kernel is as wide as the prediction is uncertain, so that the
            # spread among the chosen donors is the spread of the missing stand.
            residual = float(np.sqrt(differences.var(ddof=1) * (1 + 1 / both.sum())))
            width = max(cfg.donor_sibling_cm, residual)
            known = ~np.isnan(own)
            weights[known] *= np.exp(-0.5 * ((own[known] - expected) / width) ** 2)
    total = weights.sum()
    return weights / total if total > 0 else pool.donor_weights


def _pool_component(
    key: tuple[str, str], volume: float, pool: Pool, weights: np.ndarray, cfg: Config
) -> tuple[pd.Series, Component]:
    """Distribution of wood without harvester data, from comparable work orders.

    A draw is a part of one donor's harvest, as if the donor had delivered it:
    the work order's own harvest is unknown, so a typical share of it,
    `pool_remaining_share`, is assumed to stay behind.
    """
    shares = pd.Series(weights @ pool.donors, index=pool.cells)
    shares = shares[shares > 0]
    part = _component(key, "S3", volume, shares, cfg.pool_concentration_default, False)
    if len(pool.donors) < cfg.pool_min_donors:
        return shares, part
    columns = pool.cells.get_indexer(shares.index)
    concentration, mixture_concentration = _part_concentrations(
        volume, volume / cfg.default_log_volume, cfg.pool_remaining_share, cfg
    )
    return shares, replace(
        part,
        concentration=concentration,
        mixture=pool.donors[:, columns],
        mixture_weights=weights,
        mixture_concentration=mixture_concentration,
        donor_parts=tuple((blocks[:, columns], block_weights) for blocks, block_weights in pool.parts),
    )


def _split_reversals(deliveries: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Net reversals against their load within the month: (deliveries, reversals of earlier months).

    A load is the same delivery id, or without ids the same work order,
    assortments and destination. What a load's negative rows do not cancel in
    the month reverses a load invoiced earlier, and stays as one negative row.
    """
    reversing = (deliveries[VOL] < 0) | (deliveries[BRUTTO] < 0)
    if not reversing.any():
        return deliveries, deliveries.iloc[0:0]
    load = [AO, SORT, PRODUCED, DEST]
    if "leverans_id" in deliveries.columns:
        load = ["leverans_id", *load]
    touched = deliveries.groupby(load, sort=False, dropna=False)[VOL].transform(lambda v: bool((v < 0).any()))
    untouched = deliveries[~touched.astype(bool)]

    kept, reversed_ = [untouched], []
    for _, block in deliveries[touched.astype(bool)].groupby(load, sort=False, dropna=False):
        positive = block[block[VOL] >= 0]
        net, gross = float(block[VOL].sum()), float(block[BRUTTO].sum())
        if net >= 0 and len(positive) and positive[VOL].sum() > 0:
            scaled = positive.assign(
                **{
                    VOL: positive[VOL] * net / positive[VOL].sum(),
                    BRUTTO: positive[BRUTTO] * max(gross, 0.0) / max(positive[BRUTTO].sum(), 1e-12),
                }
            )
            kept.append(scaled[scaled[BRUTTO] > 1e-12])
        elif net < 0:
            reversed_.append(block[block[VOL] < 0].head(1).assign(**{VOL: net, BRUTTO: min(gross, net)}))
    remaining = pd.concat(kept, ignore_index=True)
    reversals = pd.concat(reversed_, ignore_index=True) if reversed_ else deliveries.iloc[0:0]
    return remaining, reversals


def _credit(
    invoiced: pd.DataFrame, pending: pd.DataFrame, net: float, gross: float
) -> tuple[pd.Series, pd.Series, pd.Series, float]:
    """How a reversed load is credited: (from stock, from provisional, unknown, share of the deficit settled).

    The load is one of those invoiced on the work order, and which one is not
    known, so it is credited with the work order's invoiced distribution. The
    part still provisional is taken from the deficit in the same proportion as
    the deficit is of what was invoiced; the rest returns to the stock. More
    reversed than was ever invoiced is credited on the unknown class.
    """
    billed = invoiced.groupby([DIA, LEN], sort=False)[VOL].sum().clip(lower=0.0)
    ratio = net / gross if gross > 0 else 1.0
    owed = pending.groupby([DIA, LEN], sort=False)[VOL].sum() * ratio
    total = float(billed.sum())
    amount = min(net, total)
    provisional = amount * min(float(owed.sum()) / total, 1.0) if total > 0 else 0.0
    settled_shares = billed.sub(owed, fill_value=0.0).clip(lower=0.0)
    if settled_shares.sum() <= 0:
        settled_shares = billed
    settled = amount - provisional
    from_stock = settled_shares / settled_shares.sum() * settled if settled > 0 else billed.iloc[0:0]
    from_deficit = owed / owed.sum() * provisional if provisional > 0 else billed.iloc[0:0]
    unknown = _unknown_shares() * (net - amount) if net - amount > 1e-9 else billed.iloc[0:0]
    settled_share = provisional / float(owed.sum()) if provisional > 0 else 0.0
    return from_stock, from_deficit, unknown, settled_share


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
    work order is split by net volume. So is volume the mill measured in as
    another assortment than the harvester produced: it leaves the produced
    assortment's stock and is booked on the assortment it was measured as.

    Wood without harvester data borrows from comparable work orders, see
    `_donor_weights`.
    """
    if ledger.period is not None and ledger.period >= period:
        raise ValueError(f"Liggaren är redan stängd för {ledger.period}, kan inte stänga {period}")
    work_orders = work_orders or WorkOrders()

    calibrated = harvest.assign(**{VOL: harvest[VOL] * cfg.calibration})
    stock_keys = [AO, SORT, DIA, LEN, VINTAGE]
    history_keys = [AO, SORT, DIA, LEN, VINTAGE]
    stock = merge([ledger.stock, calibrated[STOCK_COLUMNS]], stock_keys, STOCK_COLUMNS)
    history = merge([ledger.history, calibrated[HISTORY_COLUMNS]], history_keys, HISTORY_COLUMNS)

    pools = {s: _build_pool(block, cfg) for s, block in history.groupby(SORT, sort=False)}
    mean_diameters = _mean_diameters(history)

    stock_by_key = dict(tuple(stock.groupby([AO, SORT], sort=False)))
    history_by_key = dict(tuple(history.groupby([AO, SORT], sort=False)))
    deficit_by_key = dict(tuple(ledger.deficit.groupby([AO, SORT], sort=False)))
    harvested = calibrated.groupby([AO, SORT], sort=False)[VOL].sum()
    if PRODUCED not in deliveries.columns:
        deliveries = deliveries.assign(**{PRODUCED: deliveries[SORT]})
    deliveries, reversals = _split_reversals(deliveries)
    reversals_by_key = dict(tuple(reversals.groupby([AO, PRODUCED], sort=False)))
    billed_by_key = dict(tuple(ledger.billed.groupby([AO, SORT], sort=False)))
    delivered = deliveries.groupby([AO, PRODUCED], sort=False)[VOL].sum()
    physical = deliveries.groupby([AO, PRODUCED], sort=False)[BRUTTO].sum()
    dated_by_key = dict(tuple(deliveries.groupby([AO, PRODUCED], sort=False)))
    split_by_key = {
        key: block.groupby([DEST, SORT], sort=True)[VOL].sum() / block[VOL].sum()
        for key, block in dated_by_key.items()
        if block[VOL].sum() > 0
    }

    empty_stock = stock.iloc[0:0]
    empty_deficit = ledger.deficit.iloc[0:0]
    keys = sorted(set(stock_by_key) | set(deficit_by_key) | set(delivered.index) | set(reversals_by_key))
    empty_billed = ledger.billed.iloc[0:0]

    allocations: list[pd.DataFrame] = []
    corrections: list[pd.DataFrame] = []
    closing_stock: list[pd.DataFrame] = []
    closing_deficit: list[pd.DataFrame] = []
    components: list[Component] = []
    reconciliation: list[dict] = []
    credits: list[pd.DataFrame] = []
    invoiced: list[pd.DataFrame] = []

    def book(key: tuple[str, str], part: Component, shares: pd.Series) -> pd.DataFrame:
        """Record a volume per destination and measured assortment, returning what was booked."""
        booked = []
        for (destination, billed), share in split_by_key[key].items():
            cells = (part.volume * share * shares).rename(VOL).rename_axis([DIA, LEN]).reset_index()
            booked.append(cells.assign(**{AO: key[0], SORT: billed, DEST: destination}))
            components.append(replace(part, sortiment=billed, destination=destination, volume=part.volume * share))
        rows = pd.concat(booked, ignore_index=True)
        allocations.append(rows.assign(**{TIER: part.tier}))
        invoiced.append(rows.assign(**{BILLED: rows[SORT], SORT: key[1]}))
        return rows

    for key in keys:
        block = stock_by_key.get(key, empty_stock)
        owed = deficit_by_key.get(key, empty_deficit)
        opening = float(block[VOL].sum()) - float(harvested.get(key, 0.0))

        # A load reversed after it was invoiced is credited and, as far as it came from the stock, returned to it.
        credited_net = credited_gross = 0.0
        billed_block = billed_by_key.get(key, empty_billed)
        for row in reversals_by_key.get(key, reversals.iloc[0:0]).itertuples(index=False):
            net, gross = -float(getattr(row, VOL)), -float(getattr(row, BRUTTO))
            billed_sort, destination = getattr(row, SORT), getattr(row, DEST)
            here = (billed_block[BILLED] == billed_sort) & (billed_block[DEST] == destination)
            pending_rows = (owed[BILLED] == billed_sort) & (owed[DEST] == destination)
            from_stock, from_deficit, unknown, settled_share = _credit(
                billed_block[here], owed[pending_rows], net, gross
            )
            ratio = net / gross if gross > 0 else 1.0
            if len(from_stock):
                back = from_stock.rename(VOL).rename_axis([DIA, LEN]).reset_index()
                back = back.assign(**{AO: key[0], SORT: key[1], VINTAGE: f"{period}-01", VOL: back[VOL] / ratio, LOGS: np.nan})
                block = merge([block, back[STOCK_COLUMNS]], stock_keys, STOCK_COLUMNS)
            if settled_share > 0:
                owed = pd.concat([owed[~pending_rows], owed[pending_rows].assign(**{VOL: owed.loc[pending_rows, VOL] * (1 - settled_share)})])
                owed = owed[owed[VOL] > 1e-9]
            for part in (from_stock, from_deficit, unknown):
                if len(part):
                    rows = (-part).rename(VOL).rename_axis([DIA, LEN]).reset_index()
                    rows = rows.assign(**{AO: key[0], SORT: billed_sort, DEST: destination})
                    credits.append(rows)
                    if part is not unknown:
                        invoiced.append(rows.assign(**{BILLED: billed_sort, SORT: key[1]}))
            credited_net += net
            credited_gross += gross

        # Harvester data for wood already invoiced provisionally settles that first.
        corrected = 0.0
        if len(owed) and len(block):
            owed_total = float(owed[VOL].sum())
            corrected = min(owed_total, float(block[VOL].sum()))
            taken, block = take(block, corrected)
            actual = taken.groupby([DIA, LEN], sort=False, as_index=False)[VOL].sum()
            fraction = corrected / owed_total
            released = owed.assign(**{VOL: -owed[VOL] * fraction})[[BILLED, DEST, DIA, LEN, VOL]]
            for (billed, destination), unsettled in released.groupby([BILLED, DEST], sort=False):
                earned = actual.assign(**{VOL: actual[VOL] * unsettled[VOL].sum() / released[VOL].sum()})
                changes = pd.concat([earned, unsettled[[DIA, LEN, VOL]]])
                net_change = changes.groupby([DIA, LEN], sort=False, as_index=False)[VOL].sum()
                corrections.append(net_change.assign(**{AO: key[0], SORT: billed, DEST: destination}))
                invoiced.append(net_change.assign(**{AO: key[0], SORT: key[1], BILLED: billed, DEST: destination}))
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
                    part = _history_component(key, billed, history_by_key[key], shares, cfg)
                elif key[1] in pools:
                    destination = work_orders.destinations.get(key[0], split_by_key[key].index[0][0])
                    pool = pools[key[1]]
                    weights = _donor_weights(key, destination, pool, work_orders, mean_diameters, cfg)
                    shares, part = _pool_component(key, billed, pool, weights, cfg)
                else:
                    shares = _unknown_shares()
                    part = _component(key, "S4", billed, shares, float("inf"), False)
                provisional = book(key, part, shares)
                unsettled = provisional.assign(
                    **{VOL: provisional[VOL] / net_share, BILLED: provisional[SORT], SORT: key[1]}
                )
                owed = merge([owed, unsettled[DEFICIT_COLUMNS]], DEFICIT_KEYS, DEFICIT_COLUMNS)

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
                "levererat": net - credited_net,
                "levererat_brutto": volume - credited_gross,
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

    credit = pd.concat(credits, ignore_index=True)[CREDIT_COLUMNS] if credits else pd.DataFrame(columns=CREDIT_COLUMNS)
    billed_total = merge([ledger.billed, *(f[BILLED_COLUMNS] for f in invoiced)], BILLED_KEYS, BILLED_COLUMNS)

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
            merge(closing_deficit, DEFICIT_KEYS, DEFICIT_COLUMNS),
            billed_total[billed_total[VOL].abs() > 1e-9].reset_index(drop=True),
        ),
        work_orders=work_orders,
        credits=credit,
    )
