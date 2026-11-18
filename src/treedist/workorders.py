"""The contract objects behind the month's matrices: which they are, how much each one brought, and how they were classed.

A matrix is the sum of many contract objects' wood. Showing them one by one tells the reader what the matrix stands on:
how many contract objects there were, whether one of them dominates, and how much of each was classed from its own
harvester data.

    <out>/avtalsobjekt.csv   one row per mill, assortment and contract object, with the columns of the page
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .core.allocate import CERTAINTY_TIERS
from .core.pipeline import MonthOutput
from .contract import MEASURE, STEM
from .schema import AO, DEST, DIA, LEN, PRODUCED, SORT, VINTAGE, VOL

TIER = "sakerhetsklass"
# How far along the contract object is: harvested so far, its whole delivery this month to every mill, and what is left.
PROGRESS = ["skordat_hittills_m3fub", "levererat_i_manaden_m3fub", "kvar_i_lager_m3fub"]
# How the harvest changed while it went on: its first and last day, and the volume-weighted mean diameter and length
# class of the first and the second half of its volume, in the order it was felled.
DRIFT = ["forsta_avverkningsdag", "sista_avverkningsdag", "medeldiameter_forsta_halvan_cm", "medeldiameter_andra_halvan_cm",
         "medellangd_forsta_halvan_cm", "medellangd_andra_halvan_cm"]


def _weighted(block: pd.DataFrame, column: str) -> float:
    sized = block.dropna(subset=[column])
    total = float(sized[VOL].sum())
    return float((sized[column] * sized[VOL]).sum() / total) if total > 0 else float("nan")


def drift(history: pd.DataFrame, keys: tuple[str, ...] = (AO, PRODUCED)) -> pd.DataFrame:
    """Per contract object and produced assortment, or per `keys`, from the harvest so far: when it was felled, and whether
    the logs grew thicker or thinner, longer or shorter, as it went on."""
    keys = list(keys)
    dated = history.assign(day=pd.to_datetime(history[VINTAGE]),
                           cm=pd.to_numeric(history[DIA], errors="coerce"),
                           length=pd.to_numeric(history[LEN], errors="coerce"))
    rows = {}
    for key, block in dated.groupby(keys, sort=False):
        block = block.sort_values("day", kind="stable")
        first, last = block["day"].min().date().isoformat(), block["day"].max().date().isoformat()
        halves = [float("nan")] * 4
        if block[VOL].sum() > 0:
            # A row that straddles the middle counts to the half where most of it lies.
            middle = block[VOL].cumsum() - block[VOL] / 2 <= block[VOL].sum() / 2
            early, late = block[middle], block[~middle]
            halves = [_weighted(early, "cm"), _weighted(late, "cm"), _weighted(early, "length"), _weighted(late, "length")]
        rows[key] = [first, last, *halves]
    index = pd.MultiIndex.from_tuples(list(rows), names=keys) if rows else pd.MultiIndex.from_tuples([], names=keys)
    return pd.DataFrame(list(rows.values()), index=index, columns=DRIFT)


# How much of the volume delivered to the mill this month lies in another diameter and length class than the work
# order's whole harvest so far would put it: half the summed difference of the two distributions, 0 when they agree.
# The harvest is that of the assortments the wood was produced as, each by the volume it brought to the row.
DIFFERS = "annan_klass_an_hela_skorden"
# Net volume delivered so far, all assortments and mills, since the ledger began.
SO_FAR = "levererat_hittills_m3fub"


def _composition(lines: pd.DataFrame) -> pd.Series:
    sized = lines[pd.to_numeric(lines[DIA], errors="coerce").notna() & pd.to_numeric(lines[LEN], errors="coerce").notna()]
    summed = sized.groupby([DIA, LEN])[VOL].sum()
    summed = summed[summed > 0]
    return summed / summed.sum() if summed.sum() > 0 else summed


def differs(allocation: pd.DataFrame, history: pd.DataFrame, produced: pd.Series) -> pd.Series:
    """Per mill, assortment and contract object: the share of the month's delivery in another class than the whole harvest.
    `produced` is the net volume the loads brought, per mill, assortment, contract object and produced assortment."""
    whole = {key: _composition(block) for key, block in history.groupby([AO, PRODUCED])}
    by_row = {row: part.droplevel([DEST, SORT, AO]) for row, part in produced.groupby(level=[DEST, SORT, AO])}
    out = {}
    for (mill, sortiment, ao), block in allocation.groupby([DEST, SORT, AO]):
        month = _composition(block)
        parts = [whole[(ao, name)] * volume for name, volume in by_row.get((mill, sortiment, ao), pd.Series(dtype=float)).items()
                 if len(whole.get((ao, name), ()))]
        if not parts or not len(month):
            continue
        harvest = pd.concat(parts, axis=1).fillna(0.0).sum(axis=1)
        both = pd.concat([month, harvest / harvest.sum()], axis=1).fillna(0.0)
        out[(mill, sortiment, ao)] = float((both.iloc[:, 0] - both.iloc[:, 1]).abs().sum() / 2)
    index = pd.MultiIndex.from_tuples(list(out), names=[DEST, SORT, AO]) if out else None
    return pd.Series(list(out.values()), index=index, name=DIFFERS, dtype=float)


def progress(output: MonthOutput) -> pd.DataFrame:
    """Per contract object and produced assortment: harvested so far, delivered this month and still in stock, in m3fub."""
    step = output.step
    harvested = step.ledger.history.groupby([AO, PRODUCED])[VOL].sum().rename(PROGRESS[0])
    columns = {"levererat": PROGRESS[1], "utgaende_lager": PROGRESS[2]}
    if not len(step.reconciliation):
        return harvested.to_frame().assign(**{c: 0.0 for c in PROGRESS[1:]})
    month = step.reconciliation.groupby([AO, PRODUCED])[list(columns)].sum().rename(columns=columns)
    return pd.concat([harvested, month], axis=1).fillna(0.0)


MEAN = "medeldiameter_cm"


def mean_diameter(lines: pd.DataFrame, keys: list[str]) -> pd.Series:
    """Volume-weighted mean diameter class in cm per key, over the lines that have a diameter class."""
    sized = lines.assign(cm=pd.to_numeric(lines[DIA], errors="coerce")).dropna(subset=["cm"])
    sized = sized[sized[VOL] > 0]
    if not len(sized):
        return pd.Series(dtype=float, name=MEAN)
    weighted = (sized["cm"] * sized[VOL]).groupby([sized[k] for k in keys]).sum()
    return (weighted / sized.groupby(keys)[VOL].sum()).rename(MEAN)


def work_orders(output: MonthOutput) -> pd.DataFrame:
    """Per mill, assortment and contract object: delivered m3fub, its share of the mill's month, and m3fub per class."""
    allocation = output.step.allocation
    columns = [DEST, SORT, AO, VOL, "andel_av_sagverket", MEAN, DIFFERS, *CERTAINTY_TIERS, *PROGRESS, SO_FAR, *DRIFT]
    if not len(allocation):
        return pd.DataFrame(columns=columns)
    tiers = allocation.pivot_table(index=[DEST, SORT, AO], columns=TIER, values=VOL, aggfunc="sum", fill_value=0.0)
    tiers = tiers.reindex(columns=list(CERTAINTY_TIERS), fill_value=0.0)
    table = tiers.assign(**{VOL: tiers.sum(axis=1)}).reset_index()
    table = table[table[VOL] > 0.0005]
    mill = table.groupby(DEST)[VOL].transform("sum")
    table["andel_av_sagverket"] = table[VOL] / mill
    row = [DEST, SORT, AO]
    table = table.join(mean_diameter(allocation, row), on=row)
    # A row is the wood as it was measured in, and the harvest is kept by the assortment it was produced as: the row
    # shows the harvest of the assortments its loads were produced as, the same one unless the wood was measured in as
    # another. Each counts by what its loads brought, without the rows that reverse a load.
    history = output.step.ledger.history
    loads = output.deliveries[output.deliveries[VOL] > 0]
    produced = loads.groupby([*row, PRODUCED])[VOL].sum()
    behind = produced.index.to_frame(index=False)
    harvest = behind.join(progress(output), on=[AO, PRODUCED]).groupby(row)[PROGRESS].sum()
    table = table.join(harvest, on=row).fillna({c: 0.0 for c in PROGRESS})
    table = table.join(drift(behind.merge(history, on=[AO, PRODUCED]), tuple(row)), on=row)
    table = table.join(differs(allocation, history, produced), on=row)
    billed = output.step.ledger.billed
    table[SO_FAR] = table[AO].map(billed.groupby(AO)[VOL].sum()) if len(billed) else np.nan
    return table.sort_values([DEST, SORT, VOL], ascending=[True, True, False])[columns].reset_index(drop=True)


# What the contract objects hold, from the optional table that the method itself never reads.

MEASURE_COLUMNS = [AO, MEASURE, STEM, VOL]


@dataclass(frozen=True)
class Facts:
    """The measures per contract object, with mean stem volume, where the source has them, and the month's measured
    wood that comes from no harvest."""
    measures: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=MEASURE_COLUMNS))
    # The measurement's rows marked utan_avverkning: outside every matrix, and named in the appendix by their volume.
    outside: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=[DEST, SORT, AO, VOL]))

    # Anskaffningsform per avtalsobjekt, where the source has it: shown in the appendix, never read by the method.
    origin: pd.Series = field(default_factory=lambda: pd.Series(dtype=object))

    # The name per mottagningsplats, where the source has it: what the appendix calls the mill.
    mill_names: pd.Series = field(default_factory=lambda: pd.Series(dtype=object))

    def outside_at(self, mill: str) -> pd.Series:
        """Net m3fub measured at the mill this month from no harvest, per measured assortment: the measurement names
        the assortment of such wood too, but nothing gives its diameter and length classes."""
        rows = self.outside[self.outside[DEST] == mill]
        return rows.groupby(SORT)[VOL].sum().sort_values(ascending=False, kind="stable").astype(float)


def _numbers(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index)
    return pd.to_numeric(frame[column].astype(str).str.replace(",", ".", regex=False).str.strip(), errors="coerce")


def measures(frame: pd.DataFrame | None) -> pd.DataFrame:
    """The measures per contract object, with mean stem volume and planned volume where given."""
    if frame is None or not len(frame):
        return pd.DataFrame(columns=MEASURE_COLUMNS)
    return pd.DataFrame({AO: frame[AO].astype(str).str.strip(), MEASURE: frame[MEASURE].astype(str).str.strip(),
                         STEM: _numbers(frame, STEM), VOL: _numbers(frame, VOL)}).reset_index(drop=True)
