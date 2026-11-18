"""The method's parameters. See docs/metod.md for where each default comes from.

A saved model (modeller/*.toml) also holds the parameters of the evaluation's Monte Carlo, which a run never draws;
`load_config` reads past them, and treedist.dev.model reads them.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    harvester_bias: float = 0.009
    handling_loss: float = 0.01
    # Switches that keep a saved simpler model reachable; see modeller/.
    oldest_first: bool = True
    draw_gross: bool = True
    # A delivery draws the wood the harvester cut for the mill it was produced for (VIOL 3: Producerat för
    # mottagningsplats), and never another mill's.
    stock_per_destination: bool = True
    # Harvest reported without the mottagningsplats it was produced for, which hpr leaves optional, is a pile of its
    # own that every load of the avtalsobjekt draws once its own pile is empty. Off, no load draws it, and what the
    # own pile cannot cover is volume beyond the stock.
    stock_without_destination: bool = True
    # A load first draws the wood at its start place, the landing (VIOL 3), when both sources give it.
    stock_per_landing: bool = True
    # The day method: each day's loads take only wood felled by that day, and what it cannot cover is volume beyond
    # the stock (S2). Off, the month's loads take the month's stock together.
    draw_per_day: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.harvester_bias < 1 or not 0 <= self.handling_loss < 1:
            raise ValueError("harvester_bias och handling_loss måste ligga i [0, 1)")

    @property
    def calibration(self) -> float:
        """Factor from harvester-measured volume to expected volume at the mill."""
        return (1 - self.harvester_bias) * (1 - self.handling_loss)


# Parameters of the sources that borrowed a distribution from other contract objects (S3) or booked it on an unknown class
# (S4). Every load now has its own harvester data or stops the month (docs/antaganden.md), so they decide nothing.
REMOVED = frozenset({
    "donor_destination_weight", "donor_group_weight", "donor_sibling_cm", "pool_min_pairs", "pool_per_destination",
    "history_fallback", "donor_draws",
})
# Former switches whose one remaining behaviour is this value: only S1 and S2, and an estimate that stands on the
# invoice. A file that says so is read as before; one that asks for the opposite stops.
ALWAYS = {"own_harvest_only": True, "correction_on_invoice": False, "credit_per_load": True}


def _evaluation_keys() -> set[str]:
    from .dev.uncertainty import Uncertainty

    return {f.name for f in fields(Uncertainty)}


def read_toml(path: Path) -> tuple[dict, dict]:
    """A configuration file's parameters and its [modell] table, which describes a saved model."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    return raw, raw.pop("modell", {})


def load_config(path: Path | None, base: Path | None = None) -> Config:
    """The parameters in `path`, over those of the saved model `base` when given, over the defaults."""
    known = {f.name for f in fields(Config)}
    values: dict = {}
    for source in (base, path):
        if source is None:
            continue
        raw, model = read_toml(source)
        removed = sorted(set(raw) & REMOVED)
        if removed:
            raise ValueError(
                f"{source} anger {removed}, som inte finns längre: fördelningen kommer alltid ur avtalsobjektets egen "
                "skördardata (S1 och S2), och ett lass utan stoppar månaden. Ta bort raderna ur filen")
        for key, value in ALWAYS.items():
            given = raw.pop(key, value)
            if given != value:
                raise ValueError(
                    f"{source} anger {key} = {str(given).lower()}, som inte går att välja längre: "
                    "fördelningen kommer alltid ur avtalsobjektets egen skördardata (S1 och S2), och en uppskattning "
                    "står kvar på bilagan. Ta bort raden ur filen")
        unknown = set(raw) - known - _evaluation_keys()
        if unknown:
            hint = f". Modellen sparades med kod {model['kod']}; kör den i en checkout av den" if "kod" in model else ""
            raise ValueError(f"Okända nycklar i {source}: {sorted(unknown)}{hint}")
        values.update({k: v for k, v in raw.items() if k in known})
    return Config(**values)
