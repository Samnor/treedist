"""A model as the evaluation sees it: the method's parameters and the Monte Carlo's, in one flat set.

A saved model (modeller/*.toml) keeps both, so that the climb can move any of them. A run reads only the method's
(config.Config); the evaluation runs the month as a run does and then draws, with `evaluate_month`.
"""

from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields, make_dataclass
from pathlib import Path

import pandas as pd

from ..config import Config, load_config
from ..core.ledger import Ledger
from ..core.matrices import build_grids
from ..core.pipeline import MonthOutput, run_month
from .uncertainty import Draws, Uncertainty, load_uncertainty, monte_carlo

_PARTS = (Config, Uncertainty)


def _copy(f):
    if f.default is not MISSING:
        return field(default=f.default)
    return field(default_factory=f.default_factory)


Model = make_dataclass(
    "Model",
    [(f.name, f.type, _copy(f)) for part in _PARTS for f in fields(part)],
    frozen=True,
    namespace={
        "__doc__": "Every parameter of a model, the method's and the Monte Carlo's.",
        "method": property(lambda self: Config(**{f.name: getattr(self, f.name) for f in fields(Config)})),
        "uncertainty": property(lambda self: Uncertainty(**{f.name: getattr(self, f.name) for f in fields(Uncertainty)})),
        # Each part checks its own values.
        "__post_init__": lambda self: (self.method, self.uncertainty) and None,
    },
)


def load_model(path: Path | None) -> Model:
    """Both parts of a configuration file or saved model."""
    method, uncertainty = load_config(path), load_uncertainty(path)
    return Model(**{f.name: getattr(method, f.name) for f in fields(Config)},
                 **{f.name: getattr(uncertainty, f.name) for f in fields(Uncertainty)})


@dataclass
class EvaluatedMonth(MonthOutput):
    """A month as a run gives it, with the evaluation's Monte Carlo draws when the model has intervals."""

    draws: Draws | None = None


def evaluate_month(ledger: Ledger, harvest: pd.DataFrame, deliveries: pd.DataFrame, period: str, transport_done: set[str],
                   model: Model) -> EvaluatedMonth:
    output = run_month(ledger, harvest, deliveries, period, transport_done, model.method)
    u = model.uncertainty
    draws = monte_carlo(output.step.components, deliveries, build_grids(output.step), u) if u.intervals else None
    return EvaluatedMonth(**{f.name: getattr(output, f.name) for f in fields(MonthOutput)}, draws=draws)
