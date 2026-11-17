"""Prices for judging the method, never for running it.

treedist bills no money: the appendix shows volume per class. To judge the method, though, an error in a class
that is worth more should weigh more, so the backtest, the climb and the scripts weigh their errors with an example
price list (`simulate.example_price_list`). This module reads such a list and puts prices and amounts on the
month's lines and matrices for them.

Rules cover half-open ranges [min, max) of class floors; blank means open. A rule without limits is a catch-all
that only applies where nothing more specific does. Other overlaps are errors. Rules with a `destination` replace
the general rules for that destination.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import numpy as np
import pandas as pd

from ..schema import DEST, DIA, LEN, SORT

PRICE_COLUMNS = ["handelssortiment", "diameter_min", "diameter_max", "langd_min", "langd_max", "pris_kr_per_m3fub"]


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

    def grid(self, sortiment: str, destination: str, diameters, lengths) -> np.ndarray:
        """Kronor per m3fub on a matrix's axes; 0 where there is no price."""
        return np.array([[(self.price_ore(sortiment, d, length, destination) or 0) / 100 for length in lengths]
                         for d in diameters])


def _amount_ore(litres: int, price_ore: int) -> int:
    """litres × öre/m3 rounded half up, also for negative amounts."""
    numerator = abs(litres) * price_ore
    rounded = (numerator + 500) // 1000
    return rounded if litres >= 0 else -rounded


def priced(invoice: pd.DataFrame, prices: PriceList) -> pd.DataFrame:
    """The month's lines with price, amount and whether the product had a price."""
    if invoice.empty:
        return invoice.assign(pris_kr=pd.Series(dtype=float), belopp_kr=pd.Series(dtype=float),
                              prissatt=pd.Series(dtype=bool))
    ore = [prices.price_ore(s, d, length, dest) for s, d, length, dest in zip(invoice[SORT], invoice[DIA], invoice[LEN],
                                                                     invoice[DEST])]
    litres = (invoice["volym_m3fub"] * 1000).round().astype(int)
    amounts = [None if p is None else _amount_ore(int(v), p) for v, p in zip(litres, ore)]
    return invoice.assign(
        pris_kr=[np.nan if p is None else p / 100 for p in ore],
        belopp_kr=[0.0 if a is None else a / 100 for a in amounts],
        prissatt=[p is not None for p in ore],
    )


def invoice_total_kr(lines: pd.DataFrame) -> float:
    return round(float(lines["belopp_kr"].sum()), 2)


def value_interval(output, destination: str, prices: PriceList) -> tuple[float, float] | None:
    """90 % interval of a destination's delivered value with volumes as measured, from the month's draws."""
    if output.draws is None:
        return None
    values = [
        (fixed * prices.grid(key[1], key[0], output.matrices[key].grid.diameters, output.matrices[key].grid.lengths)
         ).sum(axis=(1, 2))
        for key, fixed in output.draws.fixed.items() if key[0] == destination
    ]
    if not values:
        return None
    low, high = np.quantile(np.sum(values, axis=0), [0.05, 0.95])
    return float(low), float(high)
