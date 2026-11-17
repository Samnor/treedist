"""The exports already are the canonical CSV files, one per table."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..schema import read_csv


def read(files: dict[str, Path | None]) -> tuple[dict[str, pd.DataFrame], dict[str, Path]]:
    given = {key: path for key, path in files.items() if path is not None}
    return {key: read_csv(path) for key, path in given.items()}, given
