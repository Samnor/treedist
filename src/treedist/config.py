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
    coverage_tolerance: float = 0.03
    draw_policy: str = "proportional"
    design_effect: float = 10.0
    default_log_volume: float = 0.25
    history_concentration: float = 50.0
    pool_concentration_default: float = 20.0
    pool_min_donors: int = 5
    diameter_bias_sd_mm: float = 2.0
    mc_draws: int = 2000
    seed: int = 20261102
    volume_methods: dict[str, VolumeMethod] = field(default_factory=default_volume_methods)

    def __post_init__(self) -> None:
        if self.draw_policy not in ("proportional", "fifo"):
            raise ValueError(f"draw_policy måste vara proportional eller fifo, inte {self.draw_policy!r}")
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

    known = {f.name for f in fields(Config)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"Okända nycklar i {path}: {sorted(unknown)}")

    if "volume_methods" in raw:
        methods = default_volume_methods()
        for name, values in raw["volume_methods"].items():
            methods[name] = VolumeMethod(**values)
        raw["volume_methods"] = methods
    return Config(**raw)
