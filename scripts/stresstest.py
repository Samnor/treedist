"""Saved models on simulations that differ from the ones they were chosen on.

The climb picks parts on four scenarios. A part it dropped may only have looked
useless because the simulator never gave it anything to do. Each stress scenario
turns up one thing reality may hold more of than the simulator does, and every
model runs on the same simulations, on seeds no decision has used.

    uv run python scripts/stresstest.py                          standard, halv, halv-volym and enkel
    uv run python scripts/stresstest.py --modeller standard-2026-11-03 halv-volym
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from climb import CALIBRATION_WEIGHT, MC_DRAWS, MONTHS, NOMINAL, _naive_price_error
from compare_methods import _month_scores, _run_ledger

from treedist.config import load_config
from treedist.core.invoice import PriceList
from treedist.dev.backtest import _score
from treedist.dev.simulate import SimParams, example_price_list, simulate

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "modeller"
OUT = ROOT / "climb" / "stress.json"
SEEDS = (501, 502, 503, 504, 505, 506)
DEFAULT_MODELS = ["standard-2026-11-03", "halv", "halv-volym", "enkel"]

# The simulator's defaults are the base; each scenario turns one thing up.
SCENARIOS = {
    "bas": {},
    "skördaren mäter 5 % för mycket": {"harvester_volume_bias": 0.05},
    "5 % spill vid hantering": {"loss_rate": 0.05, "loss_sd": 0.03},
    "10 % skillnad brutto–netto": {"reject_share": 0.10},
    "lång eftersläpning": {"delivery_lag_median_days": 25.0},
    "40 % rapporteras sent": {"late_report_share": 0.40},
    "25 % omdirigeras": {"redirected_share": 0.25},
    "mest travmätning": {"stock_measured_share": 0.20},
    "klumpiga avlägg": {"landings": (3, 8), "landing_diameter_sd": 0.25},
    "små arbetsordrar": {"work_order_volume": (60.0, 400.0), "work_orders_per_month": 30},
    "stora diameterfel": {"diameter_bias_sd_mm": 6.0},
}


def _job(args: tuple[str, str, int]) -> dict:
    model, scenario, seed = args
    cfg = replace(load_config(MODELS / f"{model}.toml"), mc_draws=MC_DRAWS)
    prices = PriceList.from_frame(example_price_list())
    months = simulate(SimParams(months=MONTHS, seed=seed, **SCENARIOS[scenario]))
    rows = []

    def collect(month, output) -> None:
        scores = _month_scores(output.step.allocation, month.truth, prices)
        covered = [_score(month, m, prices, None) for m in output.matrices.values() if m.delivered.sum() > 0]
        scores["varde_90"] = float(np.mean([c["varde_inom_90"] for c in covered])) if cfg.intervals else np.nan
        rows.append(scores)

    _run_ledger(months, cfg, prices, True, collect)
    month = pd.DataFrame(rows).mean()
    return {
        "modell": model,
        "scenario": scenario,
        "seed": seed,
        "prisfel": float(month["prisfel"]),
        "prisfel_naiv": _naive_price_error(months, prices),
        "varde_90": float(month["varde_90"]),
    }


def table(frame: pd.DataFrame, reference: str) -> pd.DataFrame:
    """Per scenario and model: price error, share of the reference's gain over naive, coverage."""
    mean = frame.groupby(["scenario", "modell"])[["prisfel", "prisfel_naiv", "varde_90"]].mean()
    naive = mean["prisfel_naiv"]
    gain = (naive - mean["prisfel"]).div((naive - mean["prisfel"]).xs(reference, level="modell"), level="scenario")
    out = mean[["prisfel", "varde_90"]].assign(prestanda=gain)
    out["poang"] = out["prisfel"] + CALIBRATION_WEIGHT * (out["varde_90"] - NOMINAL).abs() * 100
    return out.reset_index()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--modeller", nargs="+", default=None, help="namn i modeller/, utan .toml")
    parser.add_argument("--referens", default=None, help="modellen vars vinst är 100 %%; förval den första")
    args = parser.parse_args()

    models = args.modeller or DEFAULT_MODELS
    reference = args.referens or models[0]
    jobs = [(m, s, seed) for m in models for s in SCENARIOS for seed in SEEDS]
    with ProcessPoolExecutor() as pool:
        frame = pd.DataFrame(list(pool.map(_job, jobs)))

    result = table(frame, reference)
    OUT.write_text(json.dumps({"referens": reference, "seeds": SEEDS, "rader": frame.to_dict("records")}, ensure_ascii=False, indent=1))
    order = {name: i for i, name in enumerate(SCENARIOS)}
    result = result.sort_values(["scenario", "modell"], key=lambda c: c.map(order) if c.name == "scenario" else c)
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print(result.round({"prisfel": 2, "varde_90": 3, "prestanda": 3, "poang": 2}).to_string(index=False))


if __name__ == "__main__":
    main()
