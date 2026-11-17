"""Files that ship with treedist: the saved models, the examples, the demo's answer and AGENTS.md.

An installed package has them in treedist/_data (see pyproject.toml). A clone of the
repository reads them where they live, so there is only one copy of each.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PACKAGED = Path(__file__).resolve().parent / "_data"
REPO = Path(__file__).resolve().parents[2]
IN_REPO = {"modeller": "modeller", "examples": "examples", "facit": "tests/golden", "AGENTS.md": "AGENTS.md"}


def path(name: str) -> Path:
    packaged = PACKAGED / name
    return packaged if packaged.exists() else REPO / IN_REPO[name]


def models() -> dict[str, Path]:
    return {p.stem: p for p in sorted(path("modeller").glob("*.toml"))}


def model(name: str) -> Path:
    found = models()
    if name not in found:
        raise ValueError(f"Ingen modell som heter {name}. Finns: {', '.join(found)}")
    return found[name]


def describe(model_path: Path) -> dict:
    """The [modell] table a saved model describes itself with."""
    with open(model_path, "rb") as f:
        return tomllib.load(f).get("modell", {})
