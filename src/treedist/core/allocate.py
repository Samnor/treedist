"""Monthly allocation of delivered volume onto diameter × length classes.

The delivery measurement decides how much was delivered per contract object and
assortment. The harvester data decides how that volume is distributed. Each
allocated volume gets a certainty class by where its distribution came from:

    S1  the contract object's own unconsumed harvester stock
    S2  the contract object's harvest history (more delivered than stock)

Every load is assumed to have harvester data for its own contract object and
assortment (docs/antaganden.md). A load without any stops the month: nothing is
borrowed from other contract objects, and nothing is booked on an unknown class.

S2 volume is an estimate, and it stands: the month's appendix is made once, on
the first day of the next month, and no later month changes it. The volume stays
in the ledger's deficit, so that harvester data arriving later is counted off
against it instead of being put in the stock and delivered twice. How the
estimate differed from that harvester data is kept in `MonthStep.corrections`,
for follow-up only: no invoice, matrix or invoiced distribution includes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from ..config import Config
from ..schema import (
    AO,
    BRUTTO,
    DELIVERED,
    DEST,
    DIA,
    LANDING,
    LOAD_ID,
    LEN,
    LOGS,
    NO_DESTINATION,
    PRODUCED,
    PRODUCED_FOR,
    SORT,
    TIER,
    VINTAGE,
    VOL,
)
from .ledger import (
    BILLED_COLUMNS,
    BILLED_KEYS,
    DEFICIT_COLUMNS,
    DEFICIT_KEYS,
    HISTORY_COLUMNS,
    LOAD_COLUMNS,
    LOAD_KEY,
    MONTH,
    STOCK_COLUMNS,
    Ledger,
    merge,
    split,
    take,
)

CERTAINTY_TIERS = ("S1", "S2")
CREDIT_COLUMNS = [AO, SORT, DEST, DIA, LEN, VOL]
TIER_NAMES = {
    "S1": "Skördardata, eget lager",
    "S2": "Skördardata, AO-historik",
}


class BrokenAssumption(ValueError):
    """The month's data breaks an assumption the method rests on (docs/antaganden.md), so the month does not run."""


@dataclass(frozen=True)
class Component:
    """One allocated volume with its composition, and what is known about how precisely.

    A run never draws from it. The evaluation's Monte Carlo (treedist.dev.uncertainty) does, to judge whether the
    method knows its own uncertainty: `basis` is the volume the precision rests on, what left the stock for S1 and
    what was billed beyond the stock for S2; `logs` the logs counted in what left (S1) and `harvested` the work
    order's harvest so far (S1).
    """

    ao: str
    sortiment: str
    tier: str
    volume: float
    diameters: tuple[str, ...]
    lengths: tuple[str, ...]
    q: np.ndarray
    basis: float
    logs: float = float("nan")
    harvested: float = float("nan")
    destination: str = NO_DESTINATION


@dataclass
class MonthStep:
    period: str
    harvest: pd.DataFrame
    allocation: pd.DataFrame
    # How an earlier month's estimate (S2) differed from the harvester data that arrived for it this month: class
    # changes that sum to zero. For follow-up only; nothing here is invoiced.
    corrections: pd.DataFrame
    reconciliation: pd.DataFrame
    components: list[Component]
    ledger: Ledger
    # Loads reversed after the month they were invoiced in: negative volumes, on the invoice as KREDITERING.
    credits: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=CREDIT_COLUMNS))
    # The day method: each day's loads took only wood felled by that day.
    draw_per_day: bool = False
    # The avtalsobjekt whose stock was written off after this month.
    closed: frozenset = frozenset()
    # With the day method, net volume per avtalsobjekt and assortment estimated beyond the stock although wood felled
    # after the loads was still in it at the month's end: what a wrong felling or delivery date would show as.
    felled_after: dict = field(default_factory=dict)


def _composition(block: pd.DataFrame) -> pd.Series:
    """Volume shares per (diameter, length)."""
    summed = block.groupby([DIA, LEN], sort=True)[VOL].sum()
    return summed / summed.sum()


def _draw_fractions(block: pd.DataFrame, dated: pd.DataFrame | None, volume: float, oldest_first: bool = True,
                    follow: bool | None = None) -> np.ndarray:
    """Share of each stock row taken by the month's deliveries.

    Trucks that start while the harvester is still there follow it and take the
    oldest wood first. Otherwise the stock is mixed on the landing, and every
    row gives the same share. `follow` decides it for the caller; without it, it
    is decided by the first of `dated`'s delivery dates.
    """
    stock = block[VOL].to_numpy(dtype=float)
    harvested = pd.to_datetime(block[VINTAGE]).to_numpy("datetime64[D]")
    if follow is None:
        follow = bool(dated[DELIVERED].to_numpy("datetime64[D]").min() <= harvested.max())
    if not oldest_first or not follow:
        return np.full(len(stock), min(volume / stock.sum(), 1.0))
    dates, date_of = np.unique(harvested, return_inverse=True)
    per_date = np.bincount(date_of, weights=stock, minlength=len(dates))
    taken = np.clip(volume - (np.cumsum(per_date) - per_date), 0.0, per_date)
    return (taken / per_date)[date_of]


def _draw_pile(block: pd.DataFrame, loads: pd.DataFrame, need: pd.Series, oldest_first: bool,
               follow: bool | None = None) -> tuple[dict, pd.DataFrame]:
    """Gross volume `need` per landing from one mottagningsplats' stock: (taken per landing, remaining).

    The loads from a landing first take the wood at it. What that does not cover is taken from the rest of the stock
    together, and shared in proportion to what each landing still lacks: the landing is worked out from the stems'
    coordinates and may be wrong. What the stock cannot cover is not taken.
    """
    taken: dict = {}
    lacking: dict = {}
    for landing, amount in need.items():
        mask = block[LANDING] == landing
        own = block[mask]
        own_volume = float(own[VOL].sum())
        if own_volume > 0:
            got, left = split(own, _draw_fractions(own, loads[loads[LANDING] == landing], min(amount, own_volume),
                                                   oldest_first, follow))
            taken[landing] = [got]
            lacking[landing] = max(amount - own_volume, 0.0)
            block = pd.concat([block[~mask], left])
        else:
            lacking[landing] = amount
    short = sum(lacking.values())
    if short > 1e-12 and len(block):
        common, block = split(block, _draw_fractions(block, loads, short, oldest_first, follow))
        for landing, amount in lacking.items():
            if amount > 0:
                factor = amount / short
                taken.setdefault(landing, []).append(common.assign(**{VOL: common[VOL] * factor,
                                                                      LOGS: common[LOGS] * factor}))
    return {landing: pd.concat(parts, ignore_index=True) for landing, parts in taken.items()}, block


def _draw_stock(block: pd.DataFrame, dated: pd.DataFrame, volume: float, cfg: Config,
                follow: bool | None = None) -> tuple[dict, pd.DataFrame]:
    """Gross volume `volume` from a stock block for the loads in `dated`: (taken per mill, remaining).

    Each load takes the wood of the mottagningsplats it was produced for (VIOL 3: Producerat för mottagningsplats),
    and what it takes is booked at the mill it was measured at. What that stock cannot cover is not taken: it is
    volume beyond the stock, never wood cut for another mottagningsplats. With `stock_without_destination`, wood
    reported without a mottagningsplats is taken before that. Without stock per destination the stock is one pile,
    and what is taken is under None, for every mill.
    """
    if not cfg.stock_per_destination:
        taken, block = split(block, _draw_fractions(block, dated, volume, cfg.oldest_first, follow))
        return {None: taken}, block
    loads = dated if cfg.stock_per_landing else dated.assign(**{LANDING: NO_DESTINATION})
    gross = loads[VOL] / loads[VOL].sum() * volume
    taken_by: dict = {}

    def book(taken: pd.DataFrame, at: pd.DataFrame) -> None:
        """What the loads `at` took, at the mills they were measured at."""
        for mill, share in (at.groupby(DEST, sort=True)[VOL].sum() / at[VOL].sum()).items():
            taken_by.setdefault(mill, []).append(
                taken if share == 1.0 else taken.assign(**{VOL: taken[VOL] * share, LOGS: taken[LOGS] * share}))

    # Gross volume per mottagningsplats and landing that the loads' own pile did not cover.
    short: dict[tuple[str, str], float] = {}
    for pile, own_loads in loads.groupby(PRODUCED_FOR, sort=True):
        mine = block[PRODUCED_FOR] == pile
        need = gross[own_loads.index].groupby(own_loads[LANDING], sort=True).sum()
        drawn, left = _draw_pile(block[mine], own_loads, need, cfg.oldest_first, follow)
        block = pd.concat([block[~mine], left], ignore_index=True)
        for landing, amount in need.items():
            got = float(drawn[landing][VOL].sum()) if landing in drawn else 0.0
            if landing in drawn:
                book(drawn[landing], own_loads[own_loads[LANDING] == landing])
            if pile != NO_DESTINATION and amount - got > 1e-9:
                short[(pile, landing)] = amount - got
    spare = block[PRODUCED_FOR] == NO_DESTINATION
    if cfg.stock_without_destination and short and spare.any():
        # Wood the harvester reported without a mottagningsplats is the avtalsobjekt's own, and was driven to one of
        # them: the loads whose own pile is empty take it, each landing's first.
        lacking = pd.Series(short)
        waiting = loads[[key in short for key in zip(loads[PRODUCED_FOR], loads[LANDING])]]
        drawn, left = _draw_pile(block[spare], waiting, lacking.groupby(level=1, sort=True).sum(), cfg.oldest_first,
                                 follow)
        block = pd.concat([block[~spare], left], ignore_index=True)
        for landing, taken in drawn.items():
            here = lacking.xs(landing, level=1)
            for pile, share in (here / here.sum()).items():
                part = taken if share == 1.0 else taken.assign(**{VOL: taken[VOL] * share, LOGS: taken[LOGS] * share})
                book(part, waiting[(waiting[PRODUCED_FOR] == pile) & (waiting[LANDING] == landing)])
    return {mill: pd.concat(parts, ignore_index=True) for mill, parts in taken_by.items()}, block


def _beyond(taken_by: dict, loads: pd.DataFrame, volume: float, cfg: Config) -> dict:
    """Gross volume per mill that the stock did not cover, of `volume` for `loads`; under None when the stock is one
    pile."""
    shares = loads.groupby(DEST)[VOL].sum() / loads[VOL].sum() if cfg.stock_per_destination else pd.Series({None: 1.0})
    got = {mill: float(taken[VOL].sum()) for mill, taken in taken_by.items()}
    return {mill: volume * share - got.get(mill, 0.0) for mill, share in shares.items()
            if volume * share - got.get(mill, 0.0) > 1e-12}


def _draw_by_day(block: pd.DataFrame, dated: pd.DataFrame, split_here: pd.Series, net: float, volume: float,
                 cfg: Config) -> tuple[dict, dict, pd.DataFrame]:
    """The day method: (gross taken per mill, gross beyond the stock per mill, remaining stock).

    In the order the loads were driven, each day's loads take only the wood felled by that day. What that wood cannot
    cover is beyond the stock. Days with the same wood felled by them draw together, so that the order of loads
    between two fellings does not matter, and a month whose wood was all felled by its first load draws as the month
    method does. Whether the trucks follow the harvester, and so take the oldest wood first, is decided once for the
    month, as the month method decides it. The mill is None when the stock is one pile.
    """
    net_share = net / volume
    # Each mill's loads, scaled so that its month matches its net volume after reversals netted within the month.
    target = split_here.groupby(level=0).sum() * net
    factor = (target / dated.groupby(DEST)[VOL].sum()).fillna(0.0)
    loads = dated.assign(**{VOL: dated[VOL] * dated[DEST].map(factor).fillna(0.0)})
    loads = loads[loads[VOL] > 1e-12]
    days = loads[DELIVERED].to_numpy("datetime64[D]")
    fellings = np.unique(pd.to_datetime(block[VINTAGE]).to_numpy("datetime64[D]"))
    follow = bool(len(fellings)) and bool(days.min() <= fellings.max())
    # The number of felling days by each delivery day: days with the same number have the same wood to take from.
    window = np.searchsorted(fellings, days, side="right")
    taken_by: dict = {}
    beyond: dict = {}
    for w in np.unique(window):
        today = loads[window == w]
        gross = float(today[VOL].sum()) / net_share
        last = days[window == w].max()
        ready = (pd.to_datetime(block[VINTAGE]).to_numpy("datetime64[D]") <= last)
        available, later = block[ready], block[~ready]
        drawn: dict = {}
        if len(available):
            drawn, available = _draw_stock(available, today, gross, cfg, follow)
            for mill, taken in drawn.items():
                taken_by.setdefault(mill, []).append(taken)
            block = pd.concat([available, later], ignore_index=True)
        for mill, short in _beyond(drawn, today, gross, cfg).items():
            beyond[mill] = beyond.get(mill, 0.0) + short
    taken_by = {mill: pd.concat(parts, ignore_index=True) for mill, parts in taken_by.items()}
    return {mill: taken for mill, taken in taken_by.items() if taken[VOL].sum() > 1e-12}, beyond, block


def _settle_by_date(block: pd.DataFrame, volume: float, month: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`volume` counted off a stock block for wood that left beyond the stock by `month`: (taken, remaining).

    That wood was felled by then, so it is taken from the wood felled by the month's end first, pro rata as the month
    method takes it, and only what that does not cover from later wood, oldest first.
    """
    early = (pd.to_datetime(block[VINTAGE]) <= pd.Period(month, freq="M").end_time).to_numpy()
    first, rest = block[early], block[~early]
    taken, first = take(first, min(volume, float(first[VOL].sum())))
    more = volume - float(taken[VOL].sum())
    if more > 1e-12 and len(rest):
        extra, rest = split(rest, _draw_fractions(rest, None, more, True, follow=True))
        taken = pd.concat([taken, extra], ignore_index=True)
    return taken, pd.concat([first, rest], ignore_index=True)


def _component(key: tuple[str, str], tier: str, volume: float, shares: pd.Series, **known) -> Component:
    return Component(
        ao=key[0],
        sortiment=key[1],
        tier=tier,
        volume=volume,
        diameters=tuple(shares.index.get_level_values(0)),
        lengths=tuple(shares.index.get_level_values(1)),
        q=shares.to_numpy(dtype=float),
        basis=volume,
        **known,
    )


def _split_reversals(deliveries: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Net reversals against their load within the month: (deliveries, reversals of earlier months).

    A load is the same delivery id, contract object, assortments and destination. What a load's negative rows do
    not cancel in the month reverses a load invoiced earlier, and stays as one negative row. Net and gross are netted
    each for itself: a load remeasured to another net volume with the same gross volume changes what is invoiced,
    and moves no wood.
    """
    reversing = (deliveries[VOL] < 0) | (deliveries[BRUTTO] < 0)
    if not reversing.any():
        return deliveries, deliveries.iloc[0:0]
    load = [LOAD_ID, AO, SORT, PRODUCED, DEST]
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
            kept.append(scaled[(scaled[VOL] > 1e-12) | (scaled[BRUTTO] > 1e-12)])
        elif net < 0:
            reversed_.append(block[block[VOL] < 0].head(1).assign(**{VOL: net, BRUTTO: min(gross, 0.0)}))
    remaining = pd.concat(kept, ignore_index=True)
    reversals = pd.concat(reversed_, ignore_index=True) if reversed_ else deliveries.iloc[0:0]
    return remaining, reversals


def _credit(
    invoiced: pd.DataFrame, pending: pd.DataFrame, net: float
) -> tuple[pd.Series, pd.Series, float, float]:
    """How a reversed load is credited: (from stock, from the estimate, m3fub never invoiced, share of the deficit
    settled).

    The load is credited with the distribution `invoiced`, that of the month its
    leveransnummer was delivered in. The part still estimated is taken from
    the deficit in the same proportion as the deficit is of what was invoiced;
    the rest returns to the stock. Both are per month and class, so that what
    is left invoiced per month stays right. What is reversed beyond what was
    ever invoiced has no distribution to credit, and is returned as a volume.
    """
    billed = invoiced.groupby([MONTH, DIA, LEN], sort=False)[VOL].sum().clip(lower=0.0)
    owed = pending.groupby([MONTH, DIA, LEN], sort=False)[VOL].sum()
    total = float(billed.sum())
    amount = min(net, total)
    estimated = amount * min(float(owed.sum()) / total, 1.0) if total > 0 else 0.0
    settled_shares = billed.sub(owed, fill_value=0.0).clip(lower=0.0)
    if settled_shares.sum() <= 0:
        settled_shares = billed
    settled = amount - estimated
    from_stock = settled_shares / settled_shares.sum() * settled if settled > 0 else billed.iloc[0:0]
    from_deficit = owed / owed.sum() * estimated if estimated > 0 else billed.iloc[0:0]
    settled_share = estimated / float(owed.sum()) if estimated > 0 else 0.0
    return from_stock, from_deficit, max(net - amount, 0.0), settled_share


def close_month(
    ledger: Ledger,
    harvest: pd.DataFrame,
    deliveries: pd.DataFrame,
    period: str,
    transport_done: set[str] | frozenset[str],
    cfg: Config,
) -> MonthStep:
    """Roll the ledger through one month and allocate its deliveries.

    `transport_done` are the avtalsobjekt whose transport the month's table says is finished. Their stock is written
    off after the first month, this one or a later, in which no delivery of theirs was measured, so that a delivery
    driven before the transport finished and measured after it still takes the stock.

    A contract object's stock is one pile per mottagningsplats the wood was produced
    for. A load takes its own pile and is booked at the mottagningsplats it was
    measured at. Volume the mill measured in as another assortment than the
    harvester produced leaves the produced assortment's stock and is booked on the
    assortment it was measured as.

    A load without harvester data for its contract object and assortment, a reversal
    whose leveransnummer the ledger does not hold, and a reversal of more than was
    invoiced for its load's month, stop the month.
    """
    if ledger.period is not None and ledger.period >= period:
        raise ValueError(f"Liggaren är redan stängd för {ledger.period}, kan inte stänga {period}")
    # Finished transport is written off once a month passes without a measured delivery; until then it waits.
    waiting = set(ledger.transport_done) | set(transport_done)
    closed_aos = waiting - set(deliveries[AO])

    calibrated = harvest.assign(**{VOL: harvest[VOL] * cfg.calibration})
    if not cfg.stock_per_destination:
        calibrated = calibrated.assign(**{PRODUCED_FOR: NO_DESTINATION})
    if not cfg.stock_per_landing:
        calibrated = calibrated.assign(**{LANDING: NO_DESTINATION})
    stock_keys = [AO, PRODUCED, PRODUCED_FOR, LANDING, DIA, LEN, VINTAGE]
    history_keys = [AO, PRODUCED, PRODUCED_FOR, DIA, LEN, VINTAGE]
    stock = merge([ledger.stock, calibrated[STOCK_COLUMNS]], stock_keys, STOCK_COLUMNS)
    history = merge([ledger.history, calibrated[HISTORY_COLUMNS]], history_keys, HISTORY_COLUMNS)

    stock_by_key = dict(tuple(stock.groupby([AO, PRODUCED], sort=False)))
    history_by_key = dict(tuple(history.groupby([AO, PRODUCED], sort=False)))
    deficit_by_key = dict(tuple(ledger.deficit.groupby([AO, PRODUCED], sort=False)))
    harvested = calibrated.groupby([AO, PRODUCED], sort=False)[VOL].sum()
    if not cfg.draw_gross:
        deliveries = deliveries.assign(**{BRUTTO: deliveries[VOL]})
    # The month each load was first delivered in, so that a load reversed later is credited as its month was invoiced.
    first_month = ledger.loads.set_index(LOAD_KEY)[MONTH].to_dict()
    new_loads = deliveries.loc[deliveries[VOL] > 0, LOAD_KEY].astype(str).drop_duplicates().assign(**{MONTH: period})
    deliveries, reversals = _split_reversals(deliveries)
    reversals_by_key = dict(tuple(reversals.groupby([AO, PRODUCED], sort=False)))
    billed_by_key = dict(tuple(ledger.billed.groupby([AO, PRODUCED], sort=False)))
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
    # Net volume per contract object and assortment that has no harvester data of its own, and per reversed load that
    # was never invoiced: either stops the month.
    without_harvest: dict[tuple[str, str], float] = {}
    never_invoiced: dict[tuple[str, str, str], float] = {}
    # Net volume per reversed leveransnummer and contract object that the ledger holds no load for: it stops the month.
    unknown_loads: dict[tuple[str, str], float] = {}
    closing_stock: list[pd.DataFrame] = []
    closing_deficit: list[pd.DataFrame] = []
    components: list[Component] = []
    reconciliation: list[dict] = []
    credits: list[pd.DataFrame] = []
    invoiced: list[pd.DataFrame] = []
    felled_after: dict[tuple[str, str], float] = {}

    def settle(key: tuple[str, str], owed: pd.DataFrame, block: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float]:
        """Count wood delivered beyond the stock off the stock: (owed, remaining stock, gross volume counted off).

        The harvester data covers gross volume, as the stock does. What was invoiced stands; the difference between
        it and the harvested classes is only kept for follow-up. The day method counts it off the wood felled by the
        month it left in first.
        """
        if not (len(owed) and len(block)):
            return owed, block, 0.0
        owed_total = float(owed[BRUTTO].sum())
        corrected = min(owed_total, float(block[VOL].sum()))
        if cfg.draw_per_day:
            taken, block = _settle_by_date(block, corrected, str(owed[MONTH].max()))
        else:
            taken, block = take(block, corrected)
        actual = taken.groupby([DIA, LEN], sort=False, as_index=False)[VOL].sum()
        harvested_shares = actual[VOL] / actual[VOL].sum()
        fraction = corrected / owed_total
        released = owed.assign(**{VOL: -owed[VOL] * fraction})[[SORT, DEST, MONTH, DIA, LEN, VOL]]

        def change(unsettled: pd.DataFrame) -> pd.DataFrame:
            earned = actual.assign(**{VOL: harvested_shares * -unsettled[VOL].sum()})
            changes = pd.concat([earned, unsettled[[DIA, LEN, VOL]]])
            return changes.groupby([DIA, LEN], sort=False, as_index=False)[VOL].sum()

        for (billed, destination), unsettled in released.groupby([SORT, DEST], sort=False):
            corrections.append(change(unsettled).assign(**{AO: key[0], SORT: billed, DEST: destination}))
        owed = owed.assign(**{VOL: owed[VOL] * (1 - fraction), BRUTTO: owed[BRUTTO] * (1 - fraction)})
        return owed[owed[BRUTTO] > 1e-9], block, corrected

    def book(key: tuple[str, str], part: Component, shares: pd.Series, only: str | None = None) -> pd.DataFrame:
        """Record a volume per destination and measured assortment, returning what was booked.

        With `only`, the volume is that destination's and is split over its measured assortments alone.
        """
        booked = []
        split_here = split_by_key[key]
        if only is not None:
            split_here = split_here[split_here.index.get_level_values(0) == only]
            split_here = split_here / split_here.sum()
        for (destination, billed), share in split_here.items():
            cells = (part.volume * share * shares).rename(VOL).rename_axis([DIA, LEN]).reset_index()
            booked.append(cells.assign(**{AO: key[0], SORT: billed, DEST: destination, MONTH: period}))
            components.append(replace(part, sortiment=billed, destination=destination, volume=part.volume * share))
        rows = pd.concat(booked, ignore_index=True)
        allocations.append(rows.assign(**{TIER: part.tier}))
        invoiced.append(rows.assign(**{PRODUCED: key[1]}))
        return rows

    for key in keys:
        block = stock_by_key.get(key, empty_stock)
        owed = deficit_by_key.get(key, empty_deficit)
        opening = float(block[VOL].sum()) - float(harvested.get(key, 0.0))

        # A load reversed after it was invoiced is credited and, as far as its wood came back, returned to the stock.
        credited_net = credited_gross = 0.0
        billed_block = billed_by_key.get(key, empty_billed)
        for row in reversals_by_key.get(key, reversals.iloc[0:0]).itertuples(index=False):
            net, gross = -float(getattr(row, VOL)), -float(getattr(row, BRUTTO))
            billed_sort, destination = getattr(row, SORT), getattr(row, DEST)
            # A correction carries the leveransnummer of the load it reverses (VIOL 3), and that tells the month the
            # load was invoiced in.
            load_id = str(getattr(row, LOAD_ID))
            month = first_month.get((load_id, key[0], billed_sort, key[1]))
            if month is None:
                # No load of that number is in the ledger; the month stops below.
                unknown_loads[(load_id, key[0])] = unknown_loads.get((load_id, key[0]), 0.0) + net
                continue
            here = ((billed_block[SORT] == billed_sort) & (billed_block[DEST] == destination)
                    & (billed_block[MONTH] == month))
            pending_rows = (owed[SORT] == billed_sort) & (owed[DEST] == destination) & (owed[MONTH] == month)
            from_stock, from_deficit, excess, settled_share = _credit(billed_block[here], owed[pending_rows], net)
            if excess > 1e-9:
                # Nothing was invoiced that this could reverse; the month stops below.
                load = (key[0], billed_sort, destination)
                never_invoiced[load] = never_invoiced.get(load, 0.0) + excess
            # The gross volume that came back per credited net volume: none when only the net volume was remeasured.
            gross_per_net = gross / net
            # Wood returns to a stock only where the harvester reported some: a ledger from a version that borrowed
            # distributions can hold invoiced volume that is no harvested wood to deliver again.
            if len(from_stock) and gross > 0 and key in history_by_key:
                back = from_stock.groupby(level=[DIA, LEN], sort=False).sum().rename(VOL).reset_index()
                # The wood returns to the pile it left: the mottagningsplats it was produced for.
                mill = getattr(row, PRODUCED_FOR) if cfg.stock_per_destination else NO_DESTINATION
                back = back.assign(**{AO: key[0], PRODUCED: key[1], PRODUCED_FOR: mill, LANDING: NO_DESTINATION,
                                      VINTAGE: f"{period}-01",
                                      VOL: back[VOL] * gross_per_net, LOGS: np.nan})
                block = merge([block, back[STOCK_COLUMNS]], stock_keys, STOCK_COLUMNS)
            if settled_share > 0:
                # The estimate is credited by its net volume; the gross volume it still has to be counted off against
                # goes down only by what came back.
                owed_gross = float(owed.loc[pending_rows, BRUTTO].sum())
                gross_share = min(float(from_deficit.sum()) * gross_per_net / owed_gross, 1.0) if owed_gross > 0 else 0.0
                owed = pd.concat([owed[~pending_rows], owed[pending_rows].assign(
                    **{VOL: owed.loc[pending_rows, VOL] * (1 - settled_share),
                       BRUTTO: owed.loc[pending_rows, BRUTTO] * (1 - gross_share)})])
                owed = owed[owed[BRUTTO] > 1e-9]
            for part in (from_stock, from_deficit):
                if len(part):
                    per_class = (-part).groupby(level=[DIA, LEN], sort=False).sum().rename(VOL).reset_index()
                    credits.append(per_class.assign(**{AO: key[0], SORT: billed_sort, DEST: destination}))
                    rows = (-part).rename(VOL).reset_index()
                    invoiced.append(rows.assign(**{AO: key[0], PRODUCED: key[1], SORT: billed_sort, DEST: destination}))
            credited_net += net
            credited_gross += gross

        # Harvester data for wood already delivered beyond the stock is counted off against that first, so that it
        # is not delivered again.
        owed, block, corrected = settle(key, owed, block)

        # Gross volume left the stock. Net volume is what is measured for payment.
        net = float(delivered.get(key, 0.0))
        volume = float(physical.get(key, 0.0))
        net_share = net / volume if volume > 0 else 1.0
        # S1 per mill, or under None for every mill when the stock is one pile, and the gross volume beyond the stock.
        taken_by: dict = {}
        if cfg.draw_per_day and volume > 0 and net > 0:
            taken_by, beyond, block = _draw_by_day(block, dated_by_key[key], split_by_key[key], net, volume, cfg)
        else:
            covered = min(volume, float(block[VOL].sum()))
            beyond = {}
            if net > 0 and volume > 0:
                if covered > 0:
                    taken_by, block = _draw_stock(block, dated_by_key[key], volume, cfg)
                beyond = _beyond(taken_by, dated_by_key[key], volume, cfg)
            elif covered > 0:
                # Rejected wood left the stock, but nothing is invoiced for it.
                taken, block = split(block, _draw_fractions(block, dated_by_key[key], covered, cfg.oldest_first))
                taken_by = {None: taken}
        covered = sum(float(taken[VOL].sum()) for taken in taken_by.values())
        if net > 0 and taken_by:
            harvested_total = max(float(history_by_key[key][VOL].sum()) if key in history_by_key else 0.0, covered)
            for for_mill, taken in taken_by.items():
                got = float(taken[VOL].sum())
                part = _component(key, "S1", got, _composition(taken), logs=float(taken[LOGS].sum(min_count=1)),
                                  harvested=harvested_total)
                book(key, replace(part, volume=got * net_share), _composition(taken), only=for_mill)

        for for_mill, shortfall in beyond.items():
            if shortfall <= 0 or net <= 0:
                continue
            billed = shortfall * net_share
            if key not in history_by_key:
                # The assumption says this cannot happen; the month stops below.
                without_harvest[key] = without_harvest.get(key, 0.0) + billed
            else:
                # More left than the stock held: the rest is distributed as the contract object's whole harvest so far.
                shares = _composition(history_by_key[key])
                estimated = book(key, _component(key, "S2", billed, shares), shares, only=for_mill)
                unsettled = estimated.assign(**{BRUTTO: estimated[VOL] / net_share, PRODUCED: key[1]})
                owed = merge([owed, unsettled[DEFICIT_COLUMNS]], DEFICIT_KEYS, DEFICIT_COLUMNS)

        if net > 0 and volume <= 0:
            # Net volume and no gross volume: loads remeasured to a higher net volume, of which no wood left now. It
            # is distributed as the contract object's whole harvest, and leaves nothing to count off later.
            if key not in history_by_key:
                without_harvest[key] = without_harvest.get(key, 0.0) + net
            else:
                shares = _composition(history_by_key[key])
                book(key, _component(key, "S2", net, shares), shares)

        # A closed contract object gets no more harvester data: its stock is written off, and so is what was delivered
        # beyond it. Both are recorded, so that neither disappears unseen.
        if cfg.draw_per_day and beyond:
            estimated_gross = sum(beyond.values())
            if estimated_gross > 1e-9 and net > 0:
                late_wood = min(estimated_gross, float(block[VOL].sum()))
                if late_wood > 1e-9:
                    felled_after[key] = late_wood * net_share
        written_off = deficit_written_off = 0.0
        # A written-off avtalsobjekt had no delivery this month, so the deficit was already counted off its stock above.
        if key[0] in closed_aos:
            written_off = float(block[VOL].sum())
            deficit_written_off = float(owed[BRUTTO].sum())
            block = empty_stock
            owed = empty_deficit

        closing_stock.append(block)
        closing_deficit.append(owed)
        reconciliation.append(
            {
                AO: key[0],
                PRODUCED: key[1],
                "ingaende_lager": opening,
                "skordat_kalibrerat": float(harvested.get(key, 0.0)),
                "levererat": net - credited_net,
                "levererat_brutto": volume - credited_gross,
                "tackning_s1": covered / volume if volume > 0 else np.nan,
                "avraknat": corrected,
                "utgaende_lager": float(block[VOL].sum()),
                "underskott": float(owed[BRUTTO].sum()),
                "avskrivet": written_off,
                "avskrivet_underskott": deficit_written_off,
            }
        )

    if without_harvest:
        listed = ", ".join(f"{ao} {sortiment} {volume:.1f}" for (ao, sortiment), volume in list(without_harvest.items())[:8])
        more = f" och {len(without_harvest) - 8} till" if len(without_harvest) > 8 else ""
        new = (" Liggaren är ny: den första månaden behöver all skördardata som rapporterats till och med månaden, "
               "också för virke som fälldes tidigare." if ledger.period is None else "")
        raise BrokenAssumption(
            f"{len(without_harvest)} avtalsobjekt och sortiment saknar egen skördardata, "
            f"{sum(without_harvest.values()):.1f} m3fub: {listed}{more}. Varje lass antas ha skördardata för sitt "
            "avtalsobjekt och sitt sortiment (docs/antaganden.md). Kontrollera att id och sortiment skrivs likadant i "
            "produktion och mätning, att skördardatan har kommit in och att virket kommer från skördare."
            f"{new} Månaden körs inte")
    if unknown_loads:
        listed = ", ".join(f"{load} ({ao}) {volume:.1f}" for (load, ao), volume in list(unknown_loads.items())[:8])
        more = f" och {len(unknown_loads) - 8} till" if len(unknown_loads) > 8 else ""
        raise BrokenAssumption(
            f"{len(unknown_loads)} vända lass har ett leveransnummer som inte finns i liggaren, "
            f"{sum(unknown_loads.values()):.1f} m3fub: {listed}{more}. En korrigering antas ha samma leveransnummer "
            "som lasset den vänder, och lasset antas finnas i liggaren (docs/antaganden.md). Redovisades lasset före "
            "liggarens första månad, ta inte med raden som vänder det: lasset har aldrig tagits ur liggarens lager. "
            "Börja liggaren minst sex månader före den första månad som faktureras. Skrivs leveransnumret likadant "
            "på båda raderna? Månaden körs inte")
    if never_invoiced:
        listed = ", ".join(f"{ao} {sortiment} till {destination} {volume:.1f}"
                           for (ao, sortiment, destination), volume in list(never_invoiced.items())[:8])
        more = f" och {len(never_invoiced) - 8} till" if len(never_invoiced) > 8 else ""
        raise BrokenAssumption(
            f"{len(never_invoiced)} vända lass har mer volym än som fakturerats för avtalsobjektet och sortimentet, "
            f"{sum(never_invoiced.values()):.1f} m3fub: {listed}{more}. Ett lass som vänds antas ha fakturerats i "
            "liggaren (docs/antaganden.md), på samma avtalsobjekt, sortiment och mottagningsplats som raden som "
            "vänder det. Månaden körs inte")

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
            pd.concat([ledger.loads, new_loads], ignore_index=True).drop_duplicates(LOAD_KEY, keep="first")[
                LOAD_COLUMNS].reset_index(drop=True),
            frozenset(waiting - closed_aos),
        ),
        credits=credit,
        draw_per_day=cfg.draw_per_day,
        felled_after=felled_after,
        closed=frozenset(closed_aos),
    )
