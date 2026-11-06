"""How good the approximated distributions turned out, measured on the corrections that settle them.

S2, S3 and S4 are provisional. Their volume stays owed in the ledger, and when harvester data for the work order
arrives, that month's correction replaces the provisional classes with the harvested ones. The share of the settled
volume that changed class is how wrong the approximation was, measured on real data rather than on the simulator:
0 % means the provisional classes were the harvested ones, 100 % that none of the volume was in its right class.

The ledger's deficit does not record which class its volume came from, and the method may not change. So this
module keeps a record beside it, per work order and assortment, of the open provisional volume per class:

    state/<period>/preliminart.csv   open provisional m3fub per work order, assortment and class
    state/<period>/rattelser.csv     settled and moved m3fub per class, summed since the record began

A work order's deficit is settled as one, so when it holds more than one class, each class gets its share of the
settled volume and the same share of it moved. Provisional volume owed before the record began is followed as
`FORE` and not shown per class.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .core.ledger import Ledger, previous_period
from .core.pipeline import MonthOutput
from .schema import AO, SORT, VOL

TIER = "sakerhetsklass"
PROVISIONAL = ("S2", "S3", "S4")
BEFORE = "FORE"  # Provisional volume owed before this record began, whatever its class.
OPEN_COLUMNS = [AO, SORT, TIER, VOL]
TOTAL_COLUMNS = [TIER, "avraknat_m3fub", "flyttat_m3fub"]


@dataclass(frozen=True)
class Quality:
    open: pd.DataFrame    # OPEN_COLUMNS, m3fub still provisional after the month
    month: pd.DataFrame   # TOTAL_COLUMNS, this month's corrections
    totals: pd.DataFrame  # TOTAL_COLUMNS, every correction since the record began
    since: str            # the first month of the record

    def by_tier(self) -> pd.DataFrame:
        """Per provisional class: settled and moved m3fub since `since`, the share moved, and what is still open."""
        totals = self.totals.set_index(TIER).reindex(PROVISIONAL, fill_value=0.0)
        settled, moved = totals["avraknat_m3fub"], totals["flyttat_m3fub"]
        return pd.DataFrame({
            "avraknat_m3fub": settled,
            "flyttat_m3fub": moved,
            "andel_flyttad": (moved / settled).where(settled > 0.0005),
            "oppet_m3fub": self.open.groupby(TIER)[VOL].sum().reindex(PROVISIONAL, fill_value=0.0),
        }).rename_axis(TIER)

    def save(self, state: Path, period: str) -> None:
        target = state / period
        target.mkdir(parents=True, exist_ok=True)
        self.open.to_csv(target / "preliminart.csv", index=False)
        # One row per class even before anything is settled, so that the first month of the record is kept.
        tiers = sorted(set(PROVISIONAL) | set(self.totals[TIER]))
        totals = self.totals.set_index(TIER).reindex(tiers, fill_value=0.0).rename_axis(TIER).reset_index()
        totals.assign(sedan=self.since).to_csv(target / "rattelser.csv", index=False)


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=float if c.endswith("m3fub") or c == VOL else str) for c in columns})


def load(state: Path, period: str) -> tuple[pd.DataFrame, pd.DataFrame, str] | None:
    """The record as the month before `period` left it, or None if it was not kept then."""
    source = state / previous_period(period)
    if not (source / "preliminart.csv").exists():
        return None
    text = {AO: str, SORT: str, TIER: str, "sedan": str}
    open_ = pd.read_csv(source / "preliminart.csv", dtype=text)
    totals = pd.read_csv(source / "rattelser.csv", dtype=text)
    since = str(totals["sedan"].iloc[0]) if len(totals) else period
    return open_[OPEN_COLUMNS], totals[TOTAL_COLUMNS], since


def _per_key(frame: pd.DataFrame, column: str = VOL) -> pd.Series:
    if not len(frame):
        return pd.Series(dtype=float)
    return frame.groupby([AO, SORT])[column].sum()


def update(opening: Ledger, output: MonthOutput, previous: tuple[pd.DataFrame, pd.DataFrame, str] | None) -> Quality:
    """Carry the record through the month: settle what the corrections settled, then add the new provisional volume."""
    step = output.step
    if previous is None:
        # No record yet: what is already owed is followed, but its class is unknown.
        owed = _per_key(opening.deficit)
        open_ = pd.DataFrame({AO: [k[0] for k in owed.index], SORT: [k[1] for k in owed.index], TIER: BEFORE,
                              VOL: owed.to_numpy()}) if len(owed) else _empty(OPEN_COLUMNS)
        totals, since = _empty(TOTAL_COLUMNS), step.period
    else:
        open_, totals, since = previous

    opening_owed = _per_key(opening.deficit)
    corrected = _per_key(step.reconciliation, "korrigerat") if len(step.reconciliation) else pd.Series(dtype=float)
    corrections = step.corrections
    # A correction moves volume from the provisional classes to the harvested ones; what it adds to some classes it
    # takes from others, so the positive part is the volume that changed class.
    moved = _per_key(corrections.assign(**{VOL: corrections[VOL].clip(lower=0)})) if len(corrections) else pd.Series(dtype=float)
    closing_owed = _per_key(step.ledger.deficit)

    rows, month = [], {}
    for row in open_.itertuples(index=False):
        key, volume, tier = (getattr(row, AO), getattr(row, SORT)), float(getattr(row, VOL)), getattr(row, TIER)
        owed = float(opening_owed.get(key, 0.0))
        fixed = float(corrected.get(key, 0.0))
        fraction = min(fixed / owed, 1.0) if owed > 0 else 0.0
        share_moved = min(float(moved.get(key, 0.0)) / fixed, 1.0) if fixed > 0 else 0.0
        settled = volume * fraction
        if settled > 0:
            done = month.setdefault(tier, [0.0, 0.0])
            done[0] += settled
            done[1] += settled * share_moved
        # A work order closed with volume still owed has it written off: it is no longer open, nor settled.
        if float(closing_owed.get(key, 0.0)) > 1e-9:
            rows.append({AO: key[0], SORT: key[1], TIER: tier, VOL: volume - settled})

    new = step.allocation[step.allocation[TIER].isin(PROVISIONAL)]
    added = new.groupby([AO, SORT, TIER], as_index=False)[VOL].sum() if len(new) else _empty(OPEN_COLUMNS)
    carried = pd.DataFrame(rows, columns=OPEN_COLUMNS)
    combined = pd.concat([f for f in (carried, added[OPEN_COLUMNS]) if len(f)] or [_empty(OPEN_COLUMNS)], ignore_index=True)
    closing = combined.groupby([AO, SORT, TIER], as_index=False)[VOL].sum() if len(combined) else combined
    closing = closing[closing[VOL] > 1e-9].reset_index(drop=True)

    this_month = pd.DataFrame([{TIER: t, "avraknat_m3fub": s, "flyttat_m3fub": m} for t, (s, m) in month.items()],
                              columns=TOTAL_COLUMNS)
    both = pd.concat([f for f in (totals, this_month) if len(f)] or [_empty(TOTAL_COLUMNS)], ignore_index=True)
    summed = both.groupby(TIER, as_index=False)[["avraknat_m3fub", "flyttat_m3fub"]].sum() if len(both) else both
    return Quality(closing[OPEN_COLUMNS], this_month, summed[TOTAL_COLUMNS], since)
