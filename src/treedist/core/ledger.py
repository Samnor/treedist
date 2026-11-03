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

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..contract import CONTRACT_VERSION
from ..schema import AO, BILLED, DEST, DIA, LEN, LOGS, SORT, VINTAGE, VOL

# `handelssortiment` is the assortment the harvester produced throughout the
# ledger. A deficit also keeps the assortment it was invoiced as, which differs
# when the mill reclassified the wood, so that its correction lands there.
STOCK_COLUMNS = [AO, SORT, DIA, LEN, VINTAGE, VOL, LOGS]
HISTORY_COLUMNS = [AO, SORT, DIA, LEN, VINTAGE, VOL]
DEFICIT_COLUMNS = [AO, SORT, BILLED, DEST, DIA, LEN, VOL]
DEFICIT_KEYS = DEFICIT_COLUMNS[:-1]

_TEXT_COLUMNS = {c: str for c in (AO, SORT, BILLED, DEST, DIA, LEN, VINTAGE)}
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
        (target / "kontrakt.json").write_text(json.dumps({"kontrakt": CONTRACT_VERSION}) + "\n", encoding="utf-8")
        return target

    @classmethod
    def load(cls, state_dir: Path, period: str) -> Ledger:
        source = state_dir / period
        version_file = source / "kontrakt.json"
        # Snapshots without a version file predate it and are version 1.
        version = json.loads(version_file.read_text(encoding="utf-8"))["kontrakt"] if version_file.exists() else 1
        if version != CONTRACT_VERSION:
            raise ValueError(
                f"Liggaren för {period} har kontraktsversion {version}, koden har {CONTRACT_VERSION}. "
                "Kör om historiken eller migrera liggaren"
            )
        frames = [
            pd.read_csv(source / name, dtype=_TEXT_COLUMNS, keep_default_na=False, na_values=[""])
            for name in ("lager.csv", "historik.csv", "underskott.csv")
        ]
        # Snapshots from before harvest dates were kept and reclassification supported.
        if VINTAGE not in frames[1].columns:
            frames[1][VINTAGE] = f"{period}-01"
        if BILLED not in frames[2].columns:
            frames[2][BILLED] = frames[2][SORT]
        columns = (STOCK_COLUMNS, HISTORY_COLUMNS, DEFICIT_COLUMNS)
        stock, history, deficit = (f[c] if len(f) else _empty(c) for f, c in zip(frames, columns))
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
    """Concatenate and sum volumes per key."""
    frames = [f for f in frames if len(f)]
    if not frames:
        return _empty(columns)
    combined = pd.concat(frames, ignore_index=True)
    grouped = combined.groupby(keys, sort=False)
    summed = grouped[VOL].sum().to_frame()
    if LOGS in columns:
        summed[LOGS] = grouped[LOGS].sum(min_count=1)
    return summed.reset_index()[columns]


def take(block: pd.DataFrame, volume: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Remove `volume` pro rata from a stock block, returning (taken, remaining)."""
    total = block[VOL].sum()
    if volume >= total:
        return block, block.iloc[0:0]
    return split(block, np.full(len(block), volume / total))


def split(block: pd.DataFrame, fraction: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Divide each row of a stock block into (taken, remaining) by `fraction`."""
    taken = block.assign(**{VOL: block[VOL] * fraction, LOGS: block[LOGS] * fraction})
    remaining = block.assign(**{VOL: block[VOL] * (1 - fraction), LOGS: block[LOGS] * (1 - fraction)})
    return taken[taken[VOL] > 0], remaining[remaining[VOL] > 0]
