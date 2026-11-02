"""A synthetic wood flow with a known truth.

Stands are cut into logs, logs are stacked in piles, piles wait on the landing
and leave on trucks. Only what real systems would report is exposed as input:
noisy harvester classes and noisy delivery volumes without classes. The logs
actually delivered each month are kept as the facit to test the method against.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .invoice import PRICE_COLUMNS
from .schema import AO, DIA, LEN, LOGS, SORT, VOL

SORTIMENT = ("GRAN_SAG", "TALL_SAG")
LENGTHS_CM = np.arange(340, 551, 30)
DIAMETER_MIN_CM = 14
DIAMETER_MAX_CM = 44
DIAMETER_STEP_CM = 2
TAPER_CM_PER_M = 1.0


@dataclass(frozen=True)
class SimParams:
    start: str = "2026-01"
    months: int = 8
    work_orders_per_month: int = 10
    seed: int = 7
    work_order_volume: tuple[float, float] = (200.0, 1500.0)
    pile_volume: float = 35.0
    harvest_days: tuple[int, int] = (5, 20)
    forwarding_days: tuple[int, int] = (2, 7)
    delivery_lag_median_days: float = 25.0
    delivery_lag_sigma: float = 0.6
    loss_rate: float = 0.01
    harvester_volume_bias: float = 0.009
    harvester_volume_noise: float = 0.03
    diameter_bias_sd_mm: float = 2.0
    diameter_noise_mm: float = 3.0
    late_report_share: float = 0.10
    stock_measured_share: float = 0.30


@dataclass
class SimMonth:
    period: str
    harvest: pd.DataFrame
    deliveries: pd.DataFrame
    truth: pd.DataFrame
    closed_aos: set[str]


def _diameter_class(diameter_cm: np.ndarray) -> np.ndarray:
    clipped = np.clip(diameter_cm, DIAMETER_MIN_CM, DIAMETER_MAX_CM)
    return (np.floor(clipped / DIAMETER_STEP_CM) * DIAMETER_STEP_CM).astype(int)


def _cut_logs(rng: np.random.Generator, volume: float, sortiment: str) -> pd.DataFrame:
    """Logs of one work order and assortment, in harvest order."""
    mean_diameter = rng.uniform(18, 27) if sortiment == "TALL_SAG" else rng.uniform(17, 26)
    trend = rng.normal(0, 0.15)
    count = max(int(volume / 0.22), 30)

    position = np.sort(rng.uniform(0, 1, count))
    log_diameter = np.log(mean_diameter) + trend * (position - 0.5) + rng.normal(0, 0.18, count)
    diameter = np.clip(np.exp(log_diameter), DIAMETER_MIN_CM, DIAMETER_MAX_CM - 0.1)

    # Thicker logs tend to be bucked longer.
    length_position = (diameter - 14) / 22 * (len(LENGTHS_CM) - 1) + rng.normal(0, 1.5, count)
    length = LENGTHS_CM[np.clip(np.round(length_position).astype(int), 0, len(LENGTHS_CM) - 1)]

    mid_diameter_m = (diameter + TAPER_CM_PER_M * length / 200) / 100
    log_volume = np.pi / 4 * mid_diameter_m**2 * length / 100
    return pd.DataFrame({"position": position, "d": diameter, "l": length, "v": log_volume})


def _month_of(dates: pd.Series) -> pd.Series:
    return dates.dt.strftime("%Y-%m")


def simulate(params: SimParams) -> list[SimMonth]:
    rng = np.random.default_rng(params.seed)
    periods = [str(pd.Period(params.start, freq="M") + i) for i in range(params.months)]
    index_of = {p: i for i, p in enumerate(periods)}

    log_frames = []
    delivery_rows = []
    delivery_counter = 0
    work_order_counter = 0

    for period in periods:
        month_start = pd.Period(period, freq="M").start_time
        for _ in range(params.work_orders_per_month):
            work_order_counter += 1
            ao = f"AO{work_order_counter:05d}"
            start = month_start + pd.Timedelta(days=float(rng.uniform(0, 28)))
            duration = rng.integers(*params.harvest_days)
            bias_mm = rng.normal(0, params.diameter_bias_sd_mm)
            lag_factor = rng.lognormal(0, 0.3)
            draw = rng.random()
            produced = SORTIMENT if draw < 0.2 else (SORTIMENT[0],) if draw < 0.7 else (SORTIMENT[1],)

            for sortiment in produced:
                volume = rng.uniform(*params.work_order_volume)
                logs = _cut_logs(rng, volume, sortiment)
                logs[AO] = ao
                logs[SORT] = sortiment
                logs["harvested"] = start + pd.to_timedelta(logs["position"] * int(duration), unit="D")
                logs["pile"] = (logs["v"].cumsum() // params.pile_volume).astype(int)
                logs["lost"] = rng.random(len(logs)) < params.loss_rate

                logs["true_d"] = _diameter_class(logs["d"].to_numpy())
                measured = logs["d"].to_numpy() + (bias_mm + rng.normal(0, params.diameter_noise_mm, len(logs))) / 10
                logs["measured_d"] = _diameter_class(measured)
                error = 1 + params.harvester_volume_bias + rng.normal(0, params.harvester_volume_noise, len(logs))
                logs["measured_v"] = logs["v"] * error

                late = rng.random() < params.late_report_share
                harvest_month = _month_of(logs["harvested"])
                logs["reported"] = [
                    str(pd.Period(m, freq="M") + (1 if late else 0)) for m in harvest_month
                ]

                ready = logs.groupby("pile")["harvested"].max()
                delivered = {}
                for pile, ready_at in ready.items():
                    forwarding = rng.integers(*params.forwarding_days)
                    lag = rng.lognormal(np.log(params.delivery_lag_median_days), params.delivery_lag_sigma) * lag_factor
                    delivered[pile] = ready_at + pd.Timedelta(days=float(forwarding + lag))
                logs["delivered"] = logs["pile"].map(delivered)

                for pile, block in logs[~logs["lost"]].groupby("pile"):
                    delivery_counter += 1
                    stock_measured = rng.random() < params.stock_measured_share
                    method = "stockmatning" if stock_measured else "travmatning"
                    units = len(block) if stock_measured else 3
                    cv = (0.043 if stock_measured else 0.051) / np.sqrt(units)
                    true_volume = float(block["v"].sum())
                    delivery_rows.append(
                        {
                            "leverans_id": f"L{delivery_counter:07d}",
                            AO: ao,
                            SORT: sortiment,
                            "leveransdatum": delivered[pile].strftime("%Y-%m-%d"),
                            VOL: round(true_volume * (1 + rng.normal(0, cv)), 3),
                            "matmetod": method,
                            "antal_matenheter": units,
                        }
                    )
                log_frames.append(logs)

    logs = pd.concat(log_frames, ignore_index=True)
    deliveries = pd.DataFrame(delivery_rows)
    deliveries["period"] = deliveries["leveransdatum"].str[:7]

    last_delivery = deliveries.groupby(AO)["period"].max()
    months = []
    for period in periods:
        reported = logs[logs["reported"] == period].assign(
            avverkningsdatum=lambda df: _month_of(df["harvested"]) + "-15"
        )
        harvest = (
            reported.groupby([AO, SORT, "measured_d", "l", "avverkningsdatum"], as_index=False)
            .agg(**{VOL: ("measured_v", "sum"), LOGS: ("v", "size")})
            .rename(columns={"measured_d": DIA, "l": LEN})
        )
        harvest[VOL] = harvest[VOL].round(3)

        delivered_logs = logs[(~logs["lost"]) & (_month_of(logs["delivered"]) == period)]
        truth = (
            delivered_logs.groupby([AO, SORT, "true_d", "l"], as_index=False)["v"]
            .sum()
            .rename(columns={"true_d": DIA, "l": LEN, "v": VOL})
        )
        truth[DIA] = truth[DIA].astype(str)
        truth[LEN] = truth[LEN].astype(str)

        months.append(
            SimMonth(
                period=period,
                harvest=harvest.astype({DIA: str, LEN: str}),
                deliveries=deliveries[deliveries["period"] == period].drop(columns="period"),
                truth=truth,
                closed_aos=set(last_delivery[last_delivery == period].index)
                if index_of[period] < len(periods) - 1
                else set(),
            )
        )
    return months


def example_price_list() -> pd.DataFrame:
    """Invented prices at the level of public Swedish price lists from 2025."""
    base = {
        "TALL_SAG": {14: 645, 18: 835, 24: 935, 28: 1045},
        "GRAN_SAG": {14: 645, 18: 1010, 24: 1060, 28: 1160},
    }
    limits = {14: 18, 18: 24, 24: 28, 28: None}
    rows = []
    for sortiment, prices in base.items():
        for diameter, price in prices.items():
            for low, high, adjustment in ((None, 400, -40), (400, None, 0)):
                rows.append(
                    {
                        SORT: sortiment,
                        "diameter_min": diameter,
                        "diameter_max": limits[diameter],
                        "langd_min": low,
                        "langd_max": high,
                        "pris_kr_per_m3fub": price + adjustment,
                    }
                )
    return pd.DataFrame(rows, columns=PRICE_COLUMNS)
