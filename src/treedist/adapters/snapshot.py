"""For a source that only has the cumulative harvest, with no date for when a row was reported.

The contract wants each month's new harvester rows, and each row in exactly one month. Some platforms
only keep the harvest as it stands now, per work order, assortment and class. Reading the whole table
every month counts the same harvest again; filtering on the felling date drops rows reported late.

`new_rows` freezes the cumulative harvest the first time a month is read, in `<folder>/<period>.csv`,
and returns what has grown since the previous month's frozen copy. Later reads of the same month use the
frozen file, so `check` and `run` see the same rows. A decrease is not sent, since a harvester row cannot
be negative; it is written to `<folder>/<period>_avvikelser.csv` for a person to look at.

Use it from a .py adapter, with the cumulative harvest up to the end of the month:

    from treedist.adapters.snapshot import new_rows

    def read(period):
        cumulative = query(... avverkningsdatum before the month's end ...)
        return {"skordning": new_rows(cumulative, period, Path(__file__).parent / "skickat"), ...}

Freeze a month only once its harvest is complete. Delete a month's frozen file only to read that month
again, and only while no later month has been frozen.

Known limit: a row that changes class becomes a new key. Its growth is sent and the old key's decrease
is logged, so that volume counts twice; the deviations file shows how much.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from ..contract import LOGS, VOL
from ..core.ledger import previous_period

# The columns that are added up; every other column is part of the key.
QUANTITIES = (VOL, LOGS)
_TOLERANCE = 1e-9


def new_rows(cumulative: pd.DataFrame, period: str, folder: Path) -> pd.DataFrame:
    """The month's new harvester rows: this month's frozen cumulative harvest minus the previous month's."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    frozen = folder / f"{period}.csv"
    months = sorted(p.stem for p in folder.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].csv"))
    earlier = [m for m in months if m < period]
    expected = previous_period(period)
    # Checked before anything is frozen, so that a refused month leaves no file behind.
    if earlier and earlier[-1] != expected:
        raise ValueError(f"Ögonblicksbilden för {expected} saknas i {folder}; senaste är {earlier[-1]}")
    if not frozen.exists():
        later = [m for m in months if m > period]
        if later:
            raise ValueError(f"{folder} har redan senare ögonblicksbilder {later}; {period} kan inte frysas efter dem")
        cumulative.to_csv(frozen, index=False)
    current = _read(frozen)

    if not earlier:
        # The first month: everything harvested so far is new, as on a cold start.
        return current
    before = _read(folder / f"{expected}.csv")
    if set(before.columns) != set(current.columns):
        raise ValueError(f"Kolumnerna skiljer mellan {expected} och {period} i {folder}: "
                         f"{sorted(set(before.columns) ^ set(current.columns))}")

    keys = [c for c in current.columns if c not in QUANTITIES]
    quantities = [c for c in QUANTITIES if c in current.columns]
    change = _sum(current, keys, quantities).sub(_sum(before, keys, quantities), fill_value=0).reset_index()
    decreases = folder / f"{period}_avvikelser.csv"
    shrunk = change[change[VOL] < -_TOLERANCE]
    if len(shrunk):
        shrunk.to_csv(decreases, index=False)
        print(f"{len(shrunk)} rader har minskat sedan {expected}, {-shrunk[VOL].sum():.3f} m3fub; "
              f"de skickas inte, se {decreases}", file=sys.stderr)
    else:
        decreases.unlink(missing_ok=True)
    return change[change[VOL] > _TOLERANCE][current.columns].reset_index(drop=True)


def _read(path: Path) -> pd.DataFrame:
    # Text, so that ids keep their leading zeros and classes stay as written.
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    for column in QUANTITIES:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column])
    return frame


def _sum(frame: pd.DataFrame, keys: list[str], quantities: list[str]) -> pd.DataFrame:
    return frame.groupby(keys, dropna=False)[quantities].sum()
