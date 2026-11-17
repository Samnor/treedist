"""State carried between months.

Wood is delivered weeks after it is harvested, so one month of harvester data
does not describe one month of deliveries. The ledger keeps what has been
harvested but not delivered (`stock`), everything ever harvested per avtalsobjekt
(`history`), and volume delivered beyond the stock (`deficit`), which harvester
data arriving later is counted off against so that it is not delivered twice.
It also keeps what has been invoiced per avtalsobjekt, class and month (`billed`),
the month each leveransnummer was first delivered in (`loads`), so that a delivery
reversed in a later month is credited as its month was invoiced, and the
avtalsobjekt whose transport is finished but whose stock is not yet written off
(`transport_done`).

Each period is saved as its own snapshot, so re-running a month reads the
previous snapshot and cannot double count.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..contract import CONTRACT_VERSION
from ..schema import AO, BRUTTO, DEST, DIA, LANDING, LEN, LOAD_ID, LOGS, PRODUCED, PRODUCED_FOR, SORT, VINTAGE, VOL

# The columns mean what they mean in the contract. The stock and the history are the harvester's wood: the assortment
# it produced, and the mottagningsplats it cut the wood for, or "-" in a saved model that keeps one stock per
# avtalsobjekt. A deficit and what was invoiced keep the produced assortment, whose stock the wood left, and the
# assortment and mottagningsplats it was measured in as and at, which differ when the mill reclassified the wood or
# it was redirected, so that a credit of it lands there.
STOCK_COLUMNS = [AO, PRODUCED, PRODUCED_FOR, LANDING, DIA, LEN, VINTAGE, VOL, LOGS]
HISTORY_COLUMNS = [AO, PRODUCED, PRODUCED_FOR, DIA, LEN, VINTAGE, VOL]
# The month a volume was invoiced in.
MONTH = "period"
# A deficit is the net volume invoiced on an estimated distribution, and the gross volume that left the stock for
# it, which the harvester data that settles it must cover.
DEFICIT_KEYS = [AO, PRODUCED, SORT, DEST, MONTH, DIA, LEN]
DEFICIT_COLUMNS = [*DEFICIT_KEYS, VOL, BRUTTO]
# Net volume invoiced, deliveries less credits, on the same keys as the deficit.
BILLED_KEYS = DEFICIT_KEYS
BILLED_COLUMNS = [*BILLED_KEYS, VOL]
# A delivery: its leveransnummer, avtalsobjekt, measured and produced assortment, and the month it was first
# delivered in.
LOAD_KEY = [LOAD_ID, AO, SORT, PRODUCED]
LOAD_COLUMNS = [*LOAD_KEY, MONTH]
# The quantities `merge` adds up; everything else in a frame is its key.
_QUANTITIES = (VOL, BRUTTO, LOGS)

_TEXT_COLUMNS = {c: str for c in (AO, SORT, DEST, LANDING, DIA, LEN, VINTAGE, MONTH, PRODUCED, PRODUCED_FOR, LOAD_ID)}
FILES = {"stock": "lager.csv", "history": "historik.csv", "deficit": "underskott.csv", "billed": "fakturerat.csv",
         "loads": "lass.csv"}
TRANSPORT_DONE = "transport_avslutad.csv"
_PERIOD_DIR = re.compile(r"^\d{4}-\d{2}$")


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=float if c in _QUANTITIES else object) for c in columns})


@dataclass
class Ledger:
    period: str | None
    stock: pd.DataFrame
    history: pd.DataFrame
    deficit: pd.DataFrame
    billed: pd.DataFrame = field(default_factory=lambda: _empty(BILLED_COLUMNS))
    loads: pd.DataFrame = field(default_factory=lambda: _empty(LOAD_COLUMNS))
    transport_done: frozenset[str] = frozenset()

    @classmethod
    def empty(cls) -> Ledger:
        return cls(None, _empty(STOCK_COLUMNS), _empty(HISTORY_COLUMNS), _empty(DEFICIT_COLUMNS))

    def save(self, state_dir: Path) -> Path:
        target = state_dir / str(self.period)
        target.mkdir(parents=True, exist_ok=True)
        for name, file in FILES.items():
            getattr(self, name).to_csv(target / file, index=False)
        pd.DataFrame({AO: sorted(self.transport_done)}).to_csv(target / TRANSPORT_DONE, index=False)
        (target / "kontrakt.json").write_text(json.dumps({"kontrakt": CONTRACT_VERSION}) + "\n", encoding="utf-8")
        return target

    @classmethod
    def load(cls, state_dir: Path, period: str) -> Ledger:
        source = state_dir / period
        version_file = source / "kontrakt.json"
        version = json.loads(version_file.read_text(encoding="utf-8"))["kontrakt"] if version_file.exists() else 1
        if version != CONTRACT_VERSION:
            raise ValueError(
                f"Liggaren för {period} har kontraktsversion {version}, koden har {CONTRACT_VERSION}. Kör om "
                "historiken från den första månaden med en tom liggare"
            )
        columns = {"stock": STOCK_COLUMNS, "history": HISTORY_COLUMNS, "deficit": DEFICIT_COLUMNS,
                   "billed": BILLED_COLUMNS, "loads": LOAD_COLUMNS}
        frames = {}
        for name, file in FILES.items():
            frame = pd.read_csv(source / file, dtype=_TEXT_COLUMNS, keep_default_na=False, na_values=[""])
            frames[name] = frame[columns[name]] if len(frame) else _empty(columns[name])
        done = pd.read_csv(source / TRANSPORT_DONE, dtype=str, keep_default_na=False)
        return cls(period, **frames, transport_done=frozenset(done[AO]))


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
    if BRUTTO in columns:
        summed[BRUTTO] = grouped[BRUTTO].sum()
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
