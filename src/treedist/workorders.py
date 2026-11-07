"""The work orders behind the month's matrices: which they are, how much each one brought, and how they were classed.

A matrix is the sum of many work orders' wood. Showing them one by one tells the reader what the matrix stands on:
how many work orders there were, whether one of them dominates, and how much of each was classed from its own
harvester data.

    <out>/arbetsordrar.csv   one row per mill, assortment and work order, with the columns of the page
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .core.allocate import CERTAINTY_TIERS
from .core.pipeline import MonthOutput
from .contract import EAST, LAT, LON, MEASURE, NORTH, STEM
from .schema import AO, DEST, DIA, LEN, SORT, VINTAGE, VOL

TIER = "sakerhetsklass"
# How far along the work order is: harvested so far, its whole delivery this month to every mill, and what is left.
PROGRESS = ["skordat_hittills_m3fub", "levererat_i_manaden_m3fub", "kvar_i_lager_m3fub"]
# How the harvest changed while it went on: its first and last day, and the volume-weighted mean diameter class of the
# first and the second half of its volume, in the order it was felled.
DRIFT = ["forsta_avverkningsdag", "sista_avverkningsdag", "medeldiameter_forsta_halvan_cm", "medeldiameter_andra_halvan_cm"]


def drift(history: pd.DataFrame) -> pd.DataFrame:
    """Per work order and assortment, from the harvest so far: when it was felled, and whether the logs grew thicker or
    thinner as it went on. Rows without a felling day or a diameter class are left out of the halves."""
    dated = history.assign(day=pd.to_datetime(history[VINTAGE], errors="coerce"),
                           cm=pd.to_numeric(history[DIA], errors="coerce"))
    dated = dated.dropna(subset=["day"])
    rows = {}
    for key, block in dated.groupby([AO, SORT], sort=False):
        block = block.sort_values("day", kind="stable")
        first, last = block["day"].min().date().isoformat(), block["day"].max().date().isoformat()
        sized = block.dropna(subset=["cm"])
        halves = [float("nan"), float("nan")]
        if len(sized) and sized[VOL].sum() > 0:
            # A row that straddles the middle counts to the half where most of it lies.
            middle = sized[VOL].cumsum() - sized[VOL] / 2 <= sized[VOL].sum() / 2
            for i, half in enumerate((sized[middle], sized[~middle])):
                if half[VOL].sum() > 0:
                    halves[i] = float((half["cm"] * half[VOL]).sum() / half[VOL].sum())
        rows[key] = [first, last, *halves]
    index = pd.MultiIndex.from_tuples(list(rows), names=[AO, SORT]) if rows else pd.MultiIndex.from_tuples([], names=[AO, SORT])
    return pd.DataFrame(list(rows.values()), index=index, columns=DRIFT)


def progress(output: MonthOutput) -> pd.DataFrame:
    """Per work order and assortment: harvested so far, delivered this month and still in stock, in m3fub."""
    step = output.step
    harvested = step.ledger.history.groupby([AO, SORT])[VOL].sum().rename(PROGRESS[0])
    columns = {"levererat": PROGRESS[1], "utgaende_lager": PROGRESS[2]}
    if not len(step.reconciliation):
        return harvested.to_frame().assign(**{c: 0.0 for c in PROGRESS[1:]})
    month = step.reconciliation.groupby([AO, SORT])[list(columns)].sum().rename(columns=columns)
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
    """Per mill, assortment and work order: delivered m3fub, its share of the mill's month, and m3fub per class."""
    allocation = output.step.allocation
    columns = [DEST, SORT, AO, VOL, "andel_av_sagverket", MEAN, *CERTAINTY_TIERS, *PROGRESS, *DRIFT]
    if not len(allocation):
        return pd.DataFrame(columns=columns)
    tiers = allocation.pivot_table(index=[DEST, SORT, AO], columns=TIER, values=VOL, aggfunc="sum", fill_value=0.0)
    tiers = tiers.reindex(columns=list(CERTAINTY_TIERS), fill_value=0.0)
    table = tiers.assign(**{VOL: tiers.sum(axis=1)}).reset_index()
    table = table[table[VOL] > 0.0005]
    mill = table.groupby(DEST)[VOL].transform("sum")
    table["andel_av_sagverket"] = table[VOL] / mill
    table = table.join(mean_diameter(allocation, [DEST, SORT, AO]), on=[DEST, SORT, AO])
    table = table.join(progress(output), on=[AO, SORT]).fillna({c: 0.0 for c in PROGRESS})
    table = table.join(drift(output.step.ledger.history), on=[AO, SORT])
    return table.sort_values([DEST, SORT, VOL], ascending=[True, True, False])[columns].reset_index(drop=True)


def _named(part, history: pd.DataFrame) -> list[str] | None:
    """The work orders behind a borrowed component's donor rows, in their order, or None if they cannot be told.

    The method keeps donors as rows of compositions, not names. Its pool is the harvest history of one assortment in
    sorted order; the names are taken from that history only when each donor row is that work order's composition."""
    sortiments = [part.sortiment] + sorted(set(history[SORT]) - {part.sortiment})
    cells = pd.MultiIndex.from_arrays([list(part.diameters), list(part.lengths)])
    for sortiment in sortiments:
        block = history[history[SORT] == sortiment]
        names = sorted(block[AO].unique())
        if len(names) != len(part.donor_weights):
            continue
        per = block.pivot_table(index=AO, columns=[DIA, LEN], values=VOL, aggfunc="sum", fill_value=0.0)
        per = per.div(per.sum(axis=1), axis=0).reindex(index=names, columns=cells, fill_value=0.0)
        if np.allclose(per.to_numpy(), part.donors, atol=1e-9):
            return names
    return None


def donors(output: MonthOutput) -> pd.DataFrame:
    """Per mill and work order whose distribution was borrowed (S3): every work order it was borrowed from, with its
    weight. A component whose donors cannot be named for certain is left out rather than shown with wrong names."""
    columns = [DEST, AO, SORT, VOL, "givare", "vikt"]
    history = output.step.ledger.history
    rows = []
    for part in output.step.components:
        if part.tier != "S3" or part.donor_weights is None or part.donors is None:
            continue
        names = _named(part, history)
        if names is None:
            continue
        # Weighted by volume, so that two parts of the same work order add up to one set of weights.
        rows += [{DEST: part.destination, AO: part.ao, SORT: part.sortiment, "givare": name,
                  "vikt": float(weight) * part.volume, VOL: part.volume}
                 for name, weight in zip(names, part.donor_weights) if weight > 0]
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows)
    keys = [DEST, AO, SORT]
    table = frame.groupby([*keys, "givare"], as_index=False)["vikt"].sum()
    volume = frame.groupby([*keys, "givare"])[VOL].sum().groupby(keys).max().rename(VOL)
    table = table.join(volume, on=keys)
    table["vikt"] = table["vikt"] / table.groupby(keys)["vikt"].transform("sum")
    return table.sort_values([DEST, AO, SORT, "vikt"], ascending=[True, True, True, False])[columns].reset_index(drop=True)


# Where the work orders are and what they hold, from the optional columns and table that the method itself never reads.

SITE_COLUMNS = [AO, NORTH, EAST]
MEASURE_COLUMNS = [AO, MEASURE, STEM, VOL]


@dataclass(frozen=True)
class Facts:
    """Position in SWEREF 99 TM per work order, and its measures with mean stem volume, where the source has them."""
    sites: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=SITE_COLUMNS))
    measures: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=MEASURE_COLUMNS))


def _numbers(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index)
    return pd.to_numeric(frame[column].astype(str).str.replace(",", ".", regex=False).str.strip(), errors="coerce")


def sweref99tm(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 latitude and longitude in degrees to SWEREF 99 TM north and east in metres (Gauss–Krüger, GRS80, central
    meridian 15°, scale 0.9996, false easting 500 000), after Lantmäteriet's formulas."""
    a, f, k0, central, false_east = 6378137.0, 1 / 298.257222101, 0.9996, math.radians(15.0), 500000.0
    e2 = f * (2 - f)
    n = f / (2 - f)
    a_roof = a / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    big_a, big_b = e2, (5 * e2 ** 2 - e2 ** 3) / 6
    big_c, big_d = (104 * e2 ** 3 - 45 * e2 ** 4) / 120, 1237 * e2 ** 4 / 1260
    phi, delta = math.radians(lat), math.radians(lon) - central
    s_ = math.sin(phi)
    phi_star = phi - s_ * math.cos(phi) * (big_a + big_b * s_ ** 2 + big_c * s_ ** 4 + big_d * s_ ** 6)
    xi = math.atan(math.tan(phi_star) / math.cos(delta))
    eta = math.atanh(math.cos(phi_star) * math.sin(delta))
    betas = (n / 2 - 2 * n ** 2 / 3 + 5 * n ** 3 / 16 + 41 * n ** 4 / 180,
             13 * n ** 2 / 48 - 3 * n ** 3 / 5 + 557 * n ** 4 / 1440,
             61 * n ** 3 / 240 - 103 * n ** 4 / 140,
             49561 * n ** 4 / 161280)
    north = k0 * a_roof * (xi + sum(b * math.sin(2 * i * xi) * math.cosh(2 * i * eta) for i, b in enumerate(betas, 1)))
    east = k0 * a_roof * (eta + sum(b * math.cos(2 * i * xi) * math.sinh(2 * i * eta) for i, b in enumerate(betas, 1)))
    return north, east + false_east


def sites(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Position per work order in SWEREF 99 TM metres: as given, or from WGS84 latitude and longitude. Work orders
    without a position are left out."""
    if frame is None or not len(frame):
        return pd.DataFrame(columns=SITE_COLUMNS)
    north, east = _numbers(frame, NORTH), _numbers(frame, EAST)
    lat, lon = _numbers(frame, LAT), _numbers(frame, LON)
    for i in frame.index:
        if (pd.isna(north[i]) or pd.isna(east[i])) and not (pd.isna(lat[i]) or pd.isna(lon[i])):
            north[i], east[i] = sweref99tm(float(lat[i]), float(lon[i]))
    out = pd.DataFrame({AO: frame[AO].astype(str).str.strip(), NORTH: north, EAST: east}).dropna()
    return out.drop_duplicates(AO).reset_index(drop=True)


def measures(frame: pd.DataFrame | None) -> pd.DataFrame:
    """The measures per work order, with mean stem volume and planned volume where given."""
    if frame is None or not len(frame):
        return pd.DataFrame(columns=MEASURE_COLUMNS)
    return pd.DataFrame({AO: frame[AO].astype(str).str.strip(), MEASURE: frame[MEASURE].astype(str).str.strip(),
                         STEM: _numbers(frame, STEM), VOL: _numbers(frame, VOL)}).reset_index(drop=True)
