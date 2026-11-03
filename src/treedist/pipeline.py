"""One month from validated input to matrices and invoice."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .allocate import MonthStep, close_month
from .config import Config
from .invoice import PriceList, build_invoice
from .ledger import Ledger
from .matrices import SortimentMatrices, build_grids, build_matrices
from .schema import DEST, SORT, VOL, WorkOrders
from .uncertainty import MatrixKey, monte_carlo


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
    prices: PriceList,
    period: str,
    closed_aos: set[str],
    cfg: Config,
    work_orders: WorkOrders | None = None,
) -> MonthOutput:
    step = close_month(ledger, harvest, deliveries, period, closed_aos, cfg, work_orders)
    grids = build_grids(step)
    draws = monte_carlo(step.components, deliveries, grids, cfg)
    matrices = build_matrices(step, grids, draws, prices)
    invoice = build_invoice(step, prices)
    _check_invoice_volume(invoice, deliveries)
    return MonthOutput(step, matrices, invoice, deliveries)


def _check_invoice_volume(invoice: pd.DataFrame, deliveries: pd.DataFrame) -> None:
    """The invoice must bill exactly the delivery measurement, per destination and assortment."""
    billed = invoice[invoice["radtyp"] == "LEVERANS"].groupby([DEST, SORT])["volym_m3fub"].sum()
    measured = deliveries.groupby([DEST, SORT])[VOL].sum()
    difference = billed.reindex(measured.index, fill_value=0.0) - measured
    if (difference.abs() > 0.001).any():
        raise ValueError(f"Fakturerad volym avviker från leveransmätningen: {difference.to_dict()}")
