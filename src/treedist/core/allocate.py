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

    A draw is Dirichlet noise with `concentration` around a mean composition
    (none when the concentration is infinite). The mean is `q`, or, for wood
    borrowed from other work orders, the composition of one donor drawn from
    the rows of `donors` with `donor_weights`.
    """

    ao: str
    sortiment: str
    tier: str
    volume: float
    diameters: tuple[str, ...]
    lengths: tuple[str, ...]
    q: np.ndarray
    concentration: float
    donors: np.ndarray | None = None
    donor_weights: np.ndarray | None = None
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
    # Loads reversed after the month they were invoiced in: negative volumes, on the invoice as KREDITERING.
    credits: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=CREDIT_COLUMNS))


def _composition(block: pd.DataFrame) -> pd.Series:
    """Volume shares per (diameter, length)."""
    summed = block.groupby([DIA, LEN], sort=True)[VOL].sum()
    return summed / summed.sum()


def _build_pool(history: pd.DataFrame) -> Pool:
    per_ao = history.pivot_table(index=AO, columns=[DIA, LEN], values=VOL, aggfunc="sum", fill_value=0.0)
    per_ao.columns.names = [DIA, LEN]
    totals = per_ao.sum(axis=1).to_numpy()
    return Pool(per_ao.columns, per_ao.to_numpy() / totals[:, None], totals / totals.sum(), tuple(per_ao.index))


def _concentration(log_count: float, remaining_share: float, cfg: Config) -> float:
    """How precisely a part of a harvest is known when the rest stayed behind.

    Logs travel in piles from one part of the stand, so the effective number of
    independent logs is the count divided by the design effect. What stayed
    behind is the finite population correction: the less of the harvest that
    left, the more the part can differ from the whole. The harvester's classing
    of each log caps the precision at one independent error per log.
    """
    effective = max(log_count / cfg.design_effect, 1.0)
    if not cfg.finite_population:
        return min(effective, float(log_count))
    return min(max(effective / remaining_share - 1, 1.0), float(log_count))


def _draw_fractions(block: pd.DataFrame, dated: pd.DataFrame, volume: float, oldest_first: bool = True) -> np.ndarray:
    """Share of each stock row taken by the month's deliveries.

    Trucks that start while the harvester is still there follow it and take the
    oldest wood first. Otherwise the stock is mixed on the landing, and every
    row gives the same share.
    """
    stock = block[VOL].to_numpy(dtype=float)
    harvested = pd.to_datetime(block[VINTAGE]).to_numpy("datetime64[D]")
    first_delivery = dated["leveransdatum"].to_numpy("datetime64[D]").min()
    if not oldest_first or first_delivery > harvested.max():
        return np.full(len(stock), min(volume / stock.sum(), 1.0))
    dates, date_of = np.unique(harvested, return_inverse=True)
    per_date = np.bincount(date_of, weights=stock, minlength=len(dates))
    taken = np.clip(volume - (np.cumsum(per_date) - per_date), 0.0, per_date)
    return (taken / per_date)[date_of]


def _component(key: tuple[str, str], tier: str, volume: float, shares: pd.Series, concentration: float) -> Component:
    return Component(
        ao=key[0],
        sortiment=key[1],
        tier=tier,
        volume=volume,
        diameters=tuple(shares.index.get_level_values(0)),
        lengths=tuple(shares.index.get_level_values(1)),
        q=shares.to_numpy(dtype=float),
        concentration=concentration,
    )


def _stock_component(
    key: tuple[str, str], taken: pd.DataFrame, volume: float, harvested: float, cfg: Config
) -> Component:
    """A draw from the work order's own stock.

    Sampling uncertainty disappears only if the whole harvest leaves in one
    month. Emptying a stock in a second month does not count: that remainder is
    the harvest minus an uncertain first part.
    """
    shares = _composition(taken)
    logs = taken[LOGS].sum(min_count=1)
    log_count = logs if logs > 0 else volume / cfg.default_log_volume
    remaining_share = max(1 - volume / harvested, 0.0)
    if remaining_share <= 1e-9 and cfg.finite_population:
        return _component(key, "S1", volume, shares, float(log_count))
    return _component(key, "S1", volume, shares, _concentration(log_count, remaining_share, cfg))


def _history_component(key: tuple[str, str], volume: float, shares: pd.Series, cfg: Config) -> Component:
    """More delivered than the stock holds: a part of the stand the harvester data does not show yet."""
    concentration = _concentration(volume / cfg.default_log_volume, cfg.pool_remaining_share, cfg)
    return _component(key, "S2", volume, shares, concentration)


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

    The estimate is the weighted mean of the donors. A Monte Carlo draw is one
    donor, as if the wood came from that stand, and a part of it, since a
    typical share of the unknown harvest, `pool_remaining_share`, stays behind.
    """
    shares = pd.Series(weights @ pool.donors, index=pool.cells)
    shares = shares[shares > 0]
    columns = pool.cells.get_indexer(shares.index)
    concentration = _concentration(volume / cfg.default_log_volume, cfg.pool_remaining_share, cfg)
    part = _component(key, "S3", volume, shares, concentration)
    if not cfg.donor_draws:
        return shares, part
    return shares, replace(part, donors=pool.donors[:, columns], donor_weights=weights)


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

    pools = {s: _build_pool(block) for s, block in history.groupby(SORT, sort=False)}
    mean_diameters = _mean_diameters(history)

    stock_by_key = dict(tuple(stock.groupby([AO, SORT], sort=False)))
    history_by_key = dict(tuple(history.groupby([AO, SORT], sort=False)))
    deficit_by_key = dict(tuple(ledger.deficit.groupby([AO, SORT], sort=False)))
    harvested = calibrated.groupby([AO, SORT], sort=False)[VOL].sum()
    if not cfg.draw_gross:
        deliveries = deliveries.assign(**{BRUTTO: deliveries[VOL]})
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
        covered = min(volume, float(block[VOL].sum()))
        if covered > 0:
            taken, block = split(block, _draw_fractions(block, dated_by_key[key], covered, cfg.oldest_first))
            if net > 0:
                harvested_total = max(float(history_by_key[key][VOL].sum()), covered)
                part = _stock_component(key, taken, covered, harvested_total, cfg)
                book(key, replace(part, volume=covered * net_share), _composition(taken))

        shortfall = max(volume - covered, 0.0)
        if shortfall > 0 and net > 0:
            billed = shortfall * net_share
            if key in history_by_key and cfg.history_fallback:
                shares = _composition(history_by_key[key])
                part = _history_component(key, billed, shares, cfg)
            elif key[1] in pools:
                destination = work_orders.destinations.get(key[0], split_by_key[key].index[0][0])
                pool = pools[key[1]]
                weights = _donor_weights(key, destination, pool, work_orders, mean_diameters, cfg)
                shares, part = _pool_component(key, billed, pool, weights, cfg)
            else:
                shares = _unknown_shares()
                part = _component(key, "S4", billed, shares, float("inf"))
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
