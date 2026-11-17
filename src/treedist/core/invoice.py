"""The month's lines per destination, assortment and class, in whole litres.

They are what the appendix shows: delivered volume, then credits of loads reversed after their month. Volumes are
rounded to whole litres so that the lines add up exactly, and the delivered volume equals the delivery
measurement: the distribution moves volume between classes, never in or out of the month.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..schema import DEST, DIA, LEN, SORT, TIER, VOL, group_sort_key
from .allocate import CERTAINTY_TIERS, MonthStep

LINE_COLUMNS = ["radtyp", DEST, SORT, DIA, LEN, "volym_m3fub"]


def round_to_total(volumes: pd.Series) -> pd.Series:
    """Round to whole litres so that the sum equals the rounded total."""
    litres = volumes.to_numpy(dtype=float) * 1000
    floors = np.floor(litres + 1e-6).astype(np.int64)
    remainder = int(round(float(litres.sum()))) - int(floors.sum())
    if remainder != 0:
        by_fraction = np.argsort(floors - litres, kind="stable")
        chosen = by_fraction[:remainder] if remainder > 0 else by_fraction[remainder:]
        floors[chosen] += 1 if remainder > 0 else -1
    return pd.Series(floors, index=volumes.index)


def _lines(volumes: pd.DataFrame, line_type: str) -> pd.DataFrame:
    rows = []
    for (destination, sortiment), block in volumes.groupby([DEST, SORT], sort=True):
        litres = round_to_total(block.set_index([DIA, LEN])[VOL])
        for (diameter, length), amount in litres.items():
            if amount == 0:
                continue
            rows.append({"radtyp": line_type, DEST: destination, SORT: sortiment, DIA: diameter, LEN: length,
                         "volym_liter": int(amount)})
    return pd.DataFrame(rows)


def build_invoice(step: MonthStep) -> pd.DataFrame:
    """The month's lines: delivered products, then credits of loads reversed after their month."""
    delivered = step.allocation.groupby([DEST, SORT, DIA, LEN], as_index=False)[VOL].sum()
    lines = [_lines(delivered, "LEVERANS")]

    if len(step.credits):
        credits = step.credits.groupby([DEST, SORT, DIA, LEN], as_index=False)[VOL].sum()
        lines.append(_lines(credits, "KREDITERING"))

    invoice = pd.concat([part for part in lines if len(part)], ignore_index=True) if any(len(part) for part in lines) else pd.DataFrame()
    if invoice.empty:
        return pd.DataFrame(columns=[*LINE_COLUMNS, *_share_columns()])

    tiers = step.allocation.pivot_table(
        index=[DEST, SORT, DIA, LEN], columns=TIER, values=VOL, aggfunc="sum", fill_value=0.0
    ).reindex(columns=list(CERTAINTY_TIERS), fill_value=0.0)
    shares = tiers.div(tiers.sum(axis=1), axis=0)
    shares.columns = _share_columns()
    invoice = invoice.join(shares, on=[DEST, SORT, DIA, LEN])
    # Credits concern earlier months' deliveries, not this month's sources.
    invoice.loc[invoice["radtyp"] != "LEVERANS", _share_columns()] = float("nan")

    order = invoice.assign(
        _d=invoice[DIA].map(group_sort_key), _l=invoice[LEN].map(group_sort_key), _t=invoice["radtyp"] != "LEVERANS"
    ).sort_values([DEST, "_t", SORT, "_d", "_l"], kind="stable")
    invoice = invoice.loc[order.index].reset_index(drop=True)
    invoice["volym_m3fub"] = invoice["volym_liter"] / 1000
    return invoice[[*LINE_COLUMNS, *_share_columns()]]


def _share_columns() -> list[str]:
    return [f"andel_{t}" for t in CERTAINTY_TIERS]
