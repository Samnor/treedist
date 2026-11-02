"""State carried between months.

Wood is delivered weeks after it is harvested, so one month of harvester data
does not describe one month of deliveries. The ledger keeps what has been
harvested but not delivered (`stock`), everything ever harvested per work order
(`history`), and delivered volume that had no harvester data behind it yet
(`deficit`), whose provisional distribution is corrected once data arrives.

Each period is saved as its own snapshot, so re-running a month reads the
previous snapshot and cannot double count.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .schema import AO, DIA, LEN, LOGS, SORT, VINTAGE, VOL

STOCK_COLUMNS = [AO, SORT, DIA, LEN, VINTAGE, VOL, LOGS]
HISTORY_COLUMNS = [AO, SORT, DIA, LEN, VOL]
DEFICIT_COLUMNS = [AO, SORT, DIA, LEN, VOL]

_TEXT_COLUMNS = {c: str for c in (AO, SORT, DIA, LEN, VINTAGE)}
_PERIOD_DIR = re.compile(r"^\d{4}-\d{2}$")


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=float if c in (VOL, LOGS) else object) for c in columns})


@dataclass
class Ledger:
    period: str | None
    stock: pd.DataFrame
    history: pd.DataFrame
    deficit: pd.DataFrame

    @classmethod
    def empty(cls) -> Ledger:
        return cls(None, _empty(STOCK_COLUMNS), _empty(HISTORY_COLUMNS), _empty(DEFICIT_COLUMNS))

    def save(self, state_dir: Path) -> Path:
        target = state_dir / str(self.period)
        target.mkdir(parents=True, exist_ok=True)
        self.stock.to_csv(target / "lager.csv", index=False)
        self.history.to_csv(target / "historik.csv", index=False)
        self.deficit.to_csv(target / "underskott.csv", index=False)
        return target

    @classmethod
    def load(cls, state_dir: Path, period: str) -> Ledger:
        source = state_dir / period
        frames = [
            pd.read_csv(source / name, dtype=_TEXT_COLUMNS, keep_default_na=False, na_values=[""])
            for name in ("lager.csv", "historik.csv", "underskott.csv")
        ]
        columns = (STOCK_COLUMNS, HISTORY_COLUMNS, DEFICIT_COLUMNS)
        stock, history, deficit = (f if len(f) else _empty(c) for f, c in zip(frames, columns))
        return cls(period, stock, history, deficit)


def previous_period(period: str) -> str:
    return str(pd.Period(period, freq="M") - 1)


def load_for_period(state_dir: Path, period: str) -> Ledger:
    """The closing ledger of the month before `period`, or empty on a cold start."""
    snapshots = sorted(p.name for p in state_dir.iterdir() if _PERIOD_DIR.match(p.name)) if state_dir.exists() else []

    later = [s for s in snapshots if s > period]
    if later:
        raise ValueError(f"Liggaren har redan senare perioder ({later}); ta bort dem innan {period} körs om")

    earlier = [s for s in snapshots if s < period]
    if not earlier:
        return Ledger.empty()
    expected = previous_period(period)
    if earlier[-1] != expected:
        raise ValueError(f"Period {expected} saknas i liggaren; senaste är {earlier[-1]}")
    return Ledger.load(state_dir, expected)


def merge(frames: list[pd.DataFrame], keys: list[str], columns: list[str]) -> pd.DataFrame:
    """Concatenate and sum volumes per key. NaN log counts stay NaN."""
    frames = [f for f in frames if len(f)]
    if not frames:
        return _empty(columns)
    combined = pd.concat(frames, ignore_index=True)
    aggregations = {VOL: "sum"}
    if LOGS in columns:
        aggregations[LOGS] = lambda s: s.sum(min_count=len(s))
    summed = combined.groupby(keys, sort=False, as_index=False).agg(aggregations)
    return summed[columns]


def take(block: pd.DataFrame, volume: float, policy: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Remove `volume` from a stock block, returning (taken, remaining).

    Harvester data cannot say which logs left the landing. `proportional` takes
    the same share of every class. `fifo` empties the oldest harvest month
    first and is proportional within a month.
    """
    total = block[VOL].sum()
    if volume >= total:
        return block, block.iloc[0:0]

    if policy == "proportional":
        fraction = pd.Series(volume / total, index=block.index)
    else:
        per_vintage = block.groupby(VINTAGE, sort=True)[VOL].sum()
        fractions = {}
        left = volume
        for vintage, amount in per_vintage.items():
            used = min(left, amount)
            fractions[vintage] = used / amount
            left -= used
        fraction = block[VINTAGE].map(fractions).astype(float)

    taken = block.assign(**{VOL: block[VOL] * fraction, LOGS: block[LOGS] * fraction})
    remaining = block.assign(**{VOL: block[VOL] * (1 - fraction), LOGS: block[LOGS] * (1 - fraction)})
    return taken[taken[VOL] > 0], remaining[remaining[VOL] > 0]
