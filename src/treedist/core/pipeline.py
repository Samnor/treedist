"""One month from validated input to matrices and invoice."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ..config import Config
from ..schema import DEST, SORT, VOL
from .allocate import MonthStep, close_month
from .invoice import build_invoice
from .ledger import Ledger
from .matrices import MatrixKey, SortimentMatrices, build_grids, build_matrices


@dataclass
class MonthOutput:
    step: MonthStep
    matrices: dict[MatrixKey, SortimentMatrices]
    invoice: pd.DataFrame
    deliveries: pd.DataFrame


def run_month(
    ledger: Ledger,
    harvest: pd.DataFrame,
    deliveries: pd.DataFrame,
    period: str,
    transport_done: set[str] | frozenset[str],
    cfg: Config,
) -> MonthOutput:
    step = close_month(ledger, harvest, deliveries, period, transport_done, cfg)
    matrices = build_matrices(step, build_grids(step))
    invoice = build_invoice(step)
    _check_invoice_volume(invoice, deliveries)
    return MonthOutput(step, matrices, invoice, deliveries)


def _check_invoice_volume(invoice: pd.DataFrame, deliveries: pd.DataFrame) -> None:
    """The month's lines must hold exactly the delivery measurement, per destination and assortment.

    Reversed loads are part of the measurement, as negative rows, and of the
    invoice, as delivered or credited volume.
    """
    billed = invoice[invoice["radtyp"].isin(["LEVERANS", "KREDITERING"])].groupby([DEST, SORT])["volym_m3fub"].sum()
    measured = deliveries.groupby([DEST, SORT])[VOL].sum()
    difference = billed.reindex(measured.index, fill_value=0.0) - measured
    if (difference.abs() > 0.001).any():
        raise ValueError(f"Bilagans volym avviker från mätningen: {difference.to_dict()}")
