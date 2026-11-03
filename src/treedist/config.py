"""Model parameters. See docs/metod.md for where each default comes from."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass(frozen=True)
class VolumeMethod:
    """Error model for one delivery measurement method.

    `unit_cv` is the relative SD of one control unit (a log or a pile), so a
    delivery of n units has CV unit_cv / sqrt(n). `systematic_sd` is shared by
    all deliveries measured with the method in a month.
    """

    unit_cv: float
    default_units: float
    systematic_sd: float


def default_volume_methods() -> dict[str, VolumeMethod]:
    return {
        "stockmatning": VolumeMethod(0.043, 150, 0.0005),
        "travmatning": VolumeMethod(0.051, 3, 0.0015),
        "vagning": VolumeMethod(0.069, 3, 0.005),
        "skordarmatning": VolumeMethod(0.050, 150, 0.005),
        "okand": VolumeMethod(0.080, 1, 0.02),
    }


@dataclass(frozen=True)
class Config:
    harvester_bias: float = 0.009
    handling_loss: float = 0.01
    donor_destination_weight: float = 16.0
    donor_group_weight: float = 4.0
    donor_sibling_cm: float = 1.5
    pool_min_pairs: int = 3
    design_effect: float = 200.0
    default_log_volume: float = 0.25
    pool_remaining_share: float = 0.5
    # Switches that keep a saved simpler model reachable; see modeller/.
    oldest_first: bool = True
    draw_gross: bool = True
    history_fallback: bool = True
    finite_population: bool = True
    donor_draws: bool = True
    volume_error: bool = True
    log_counts: bool = True
    intervals: bool = True
    mc_draws: int = 2000
    seed: int = 20261102
    volume_methods: dict[str, VolumeMethod] = field(default_factory=default_volume_methods)

    def __post_init__(self) -> None:
        if not 0 <= self.harvester_bias < 1 or not 0 <= self.handling_loss < 1:
            raise ValueError("harvester_bias och handling_loss måste ligga i [0, 1)")
        if self.mc_draws < 100:
            raise ValueError("mc_draws måste vara minst 100")

    @property
    def calibration(self) -> float:
        """Factor from harvester-measured volume to expected volume at the mill."""
        return (1 - self.harvester_bias) * (1 - self.handling_loss)


def load_config(path: Path | None) -> Config:
    if path is None:
        return Config()
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # A saved model describes itself in [modell]; only its parameters configure the run.
    model = raw.pop("modell", {})
    known = {f.name for f in fields(Config)}
    unknown = set(raw) - known
    if unknown:
        hint = f". Modellen sparades med kod {model['kod']}; kör den i en checkout av den" if "kod" in model else ""
        raise ValueError(f"Okända nycklar i {path}: {sorted(unknown)}{hint}")

    if "volume_methods" in raw:
        methods = default_volume_methods()
        for name, values in raw["volume_methods"].items():
            methods[name] = VolumeMethod(**values)
        raw["volume_methods"] = methods
    return Config(**raw)
