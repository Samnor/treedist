"""Price list and invoice lines.

Amounts are computed in integer litres and öre so that the lines add up exactly.
Delivered volume on the invoice equals the delivery measurement: the
distribution moves value between products, never volume in or out of the bill.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np
import pandas as pd

from .allocate import CERTAINTY_TIERS, MonthStep
from .schema import DEST, DIA, LEN, SORT, TIER, VOL, group_sort_key, read_csv

PRICE_COLUMNS = [SORT, "diameter_min", "diameter_max", "langd_min", "langd_max", "pris_kr_per_m3fub"]


@dataclass(frozen=True)
class PriceRule:
    sortiment: str
    diameter_min: float | None
    diameter_max: float | None
    length_min: float | None
    length_max: float | None
    price_ore: int
    destination: str | None = None

    @property
    def is_catch_all(self) -> bool:
        return all(v is None for v in (self.diameter_min, self.diameter_max, self.length_min, self.length_max))

    def matches(self, diameter: str, length: str) -> bool:
        return _in_range(diameter, self.diameter_min, self.diameter_max) and _in_range(
            length, self.length_min, self.length_max
        )


def _in_range(group: str, low: float | None, high: float | None) -> bool:
    if low is None and high is None:
        return True
    try:
        value = float(group)
    except ValueError:
        return False
    return (low is None or value >= low) and (high is None or value < high)


def _destination(value: object) -> str | None:
    return None if pd.isna(value) or str(value).strip() == "" else str(value).strip()


def _bound(value: object) -> float | None:
    return None if pd.isna(value) or str(value).strip() == "" else float(str(value).replace(",", "."))


class PriceList:
    """Rules cover half-open ranges [min, max) of class floors; blank means open.

    A rule without limits is a catch-all that only applies where nothing more
    specific does. Other overlaps are errors, since the price would be a guess.
    Rules with a `destination` replace the general rules for that destination.
    """

    def __init__(self, rules: list[PriceRule]):
        self.rules: dict[str, list[PriceRule]] = {}
        for rule in rules:
            self.rules.setdefault(rule.sortiment, []).append(rule)

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> PriceList:
        missing = [c for c in PRICE_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Prislista: kolumner saknas: {missing}")
        rules = []
        for row in df.to_dict("records"):
            try:
                price = Decimal(str(row["pris_kr_per_m3fub"]).replace(",", "."))
            except InvalidOperation as error:
                raise ValueError(f"Prislista: ogiltigt pris {row['pris_kr_per_m3fub']!r}") from error
            rules.append(
                PriceRule(
                    str(row[SORT]).strip(),
                    _bound(row["diameter_min"]),
                    _bound(row["diameter_max"]),
                    _bound(row["langd_min"]),
                    _bound(row["langd_max"]),
                    int((price * 100).to_integral_value()),
                    _destination(row.get(DEST)),
                )
            )
        return cls(rules)

    @classmethod
    def read(cls, path: Path) -> PriceList:
        return cls.from_frame(read_csv(path))

    def price_ore(self, sortiment: str, diameter: str, length: str, destination: str | None = None) -> int | None:
        """Price in öre per m3fub, or None if the product has no price."""
        rules = self.rules.get(sortiment, [])
        own = [r for r in rules if r.destination == destination and destination is not None]
        general = [r for r in rules if r.destination is None]
        hits = [r for r in (own or general) if r.matches(diameter, length)]
        specific = [r for r in hits if not r.is_catch_all]
        if len(specific) > 1:
            raise ValueError(f"Prislista: överlappande regler för {sortiment} d={diameter} l={length}")
        chosen = specific or hits
        return chosen[0].price_ore if chosen else None


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


def _lines(volumes: pd.DataFrame, prices: PriceList, line_type: str) -> pd.DataFrame:
    rows = []
    for (destination, sortiment), block in volumes.groupby([DEST, SORT], sort=True):
        litres = round_to_total(block.set_index([DIA, LEN])[VOL])
        for (diameter, length), amount in litres.items():
            if amount == 0:
                continue
            price = prices.price_ore(sortiment, diameter, length, destination)
            value = None if price is None else _amount_ore(int(amount), price)
            rows.append(
                {
                    "radtyp": line_type,
                    DEST: destination,
                    SORT: sortiment,
                    DIA: diameter,
                    LEN: length,
                    "volym_liter": int(amount),
                    "pris_ore": price,
                    "belopp_ore": value,
                }
            )
    return pd.DataFrame(rows)


def _amount_ore(litres: int, price_ore: int) -> int:
    """litres × öre/m3 rounded half up, also for negative amounts."""
    numerator = abs(litres) * price_ore
    rounded = (numerator + 500) // 1000
    return rounded if litres >= 0 else -rounded


def build_invoice(step: MonthStep, prices: PriceList) -> pd.DataFrame:
    """Invoice lines for the month: delivered products, then corrections."""
    delivered = step.allocation.groupby([DEST, SORT, DIA, LEN], as_index=False)[VOL].sum()
    lines = [_lines(delivered, prices, "LEVERANS")]

    if len(step.corrections):
        corrections = step.corrections.groupby([DEST, SORT, DIA, LEN], as_index=False)[VOL].sum()
        corrections = corrections[corrections[VOL].abs() >= 0.0005]
        if len(corrections):
            lines.append(_lines(corrections, prices, "KORRIGERING"))

    invoice = pd.concat([l for l in lines if len(l)], ignore_index=True) if any(len(l) for l in lines) else pd.DataFrame()
    if invoice.empty:
        return pd.DataFrame(
            columns=["radtyp", DEST, SORT, DIA, LEN, "volym_m3fub", "pris_kr", "belopp_kr", "prissatt", *_share_columns()]
        )

    tiers = step.allocation.pivot_table(
        index=[DEST, SORT, DIA, LEN], columns=TIER, values=VOL, aggfunc="sum", fill_value=0.0
    ).reindex(columns=list(CERTAINTY_TIERS), fill_value=0.0)
    shares = tiers.div(tiers.sum(axis=1), axis=0)
    shares.columns = _share_columns()
    invoice = invoice.join(shares, on=[DEST, SORT, DIA, LEN])
    # Corrections concern earlier months' deliveries, not this month's certainty.
    invoice.loc[invoice["radtyp"] != "LEVERANS", _share_columns()] = float("nan")

    order = invoice.assign(
        _d=invoice[DIA].map(group_sort_key), _l=invoice[LEN].map(group_sort_key), _t=invoice["radtyp"] != "LEVERANS"
    ).sort_values([DEST, "_t", SORT, "_d", "_l"], kind="stable")
    invoice = invoice.loc[order.index].reset_index(drop=True)

    invoice["volym_m3fub"] = invoice["volym_liter"] / 1000
    invoice["pris_kr"] = invoice["pris_ore"] / 100
    invoice["prissatt"] = invoice["pris_ore"].notna()
    invoice["belopp_kr"] = invoice["belopp_ore"].fillna(0) / 100
    return invoice[["radtyp", DEST, SORT, DIA, LEN, "volym_m3fub", "pris_kr", "belopp_kr", "prissatt", *_share_columns()]]


def _share_columns() -> list[str]:
    return [f"andel_{t}" for t in CERTAINTY_TIERS]


def invoice_total_kr(invoice: pd.DataFrame) -> float:
    return round(float(invoice["belopp_kr"].sum()), 2)
