"""How the methods hold up when the simulator's assumptions are changed.

Each scenario changes one assumption judged uncertain in docs/antaganden.md. Run
from the repository root:

    uv run python scripts/sensitivity.py --out docs/kanslighet_resultat.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from compare_methods import evaluate

from treedist.config import Config
from treedist.invoice import PriceList
from treedist.simulate import example_price_list

SCENARIOS = {
    "bas": {},
    "kort lagring, delvis överlapp": {"delivery_lag_median_days": 5.0, "overlap_share": 0.5},
    "leverans under pågående skörd": {"overlap_share": 1.0},
    "lång lagring": {"delivery_lag_median_days": 30.0},
    "destination oberoende av grovlek": {"destination_noise": 1.0},
    "mindre arbetsordrar": {"work_order_volume": (100.0, 600.0), "work_orders_per_month": 20},
    "20 % omdirigerat": {"redirected_share": 0.20},
}
SEEDS = (71, 72, 73, 74)
COLUMNS = ["index_matris", "prisfel", "kum_prisfel", "varde_90", "andel_s1"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("docs/kanslighet_resultat.csv"))
    parser.add_argument("--draws", type=int, default=300)
    args = parser.parse_args()

    cfg = Config(mc_draws=args.draws)
    prices = PriceList.from_frame(example_price_list())
    rows = [row for name, o in SCENARIOS.items() for seed in SEEDS for row in evaluate(name, o, seed, cfg, prices)]
    results = pd.DataFrame(rows)
    summary = results.groupby(["scenario", "metod"], sort=False)[COLUMNS].mean().round(4)
    summary.to_csv(args.out)
    pd.set_option("display.width", 200)
    print(summary.to_string())


if __name__ == "__main__":
    main()
