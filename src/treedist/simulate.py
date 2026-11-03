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
from .schema import AO, BRUTTO, DEST, DIA, LEN, LOGS, SORT, VOL, WorkOrders

SORTIMENT = ("GRAN_SAG", "TALL_SAG")
DESTINATIONS = ("SAG_KLEN", "SAG_MIX", "SAG_GROV")
LENGTHS_CM = np.arange(340, 551, 30)
DIAMETER_MIN_CM = 10
DIAMETER_MAX_CM = 44
DIAMETER_STEP_CM = 2
TAPER_CM_PER_M = 1.0


# Diameter scale per region, from mean stem volume 0.21/0.32/0.37 m3fub (Biometria 2025).
REGIONS = {"norra": 0.81, "mellan": 1.0, "sodra": 1.075}
# Delivery lag per month harvested. Assumed: slow over the spring thaw, fast in summer because of blue stain.
SEASONAL_LAG = {1: 1.2, 2: 1.2, 3: 1.4, 4: 1.5, 5: 0.7, 6: 0.6, 7: 0.6, 8: 0.6, 9: 0.8, 10: 1.0, 11: 1.0, 12: 1.2}
# Sveaskog delivered 27 % less sawlogs in Q3 2025 than in an average quarter.
SEASONAL_ACTIVITY = {7: 0.73, 8: 0.73, 9: 0.73}


@dataclass(frozen=True)
class SimParams:
    start: str = "2026-01"
    months: int = 8
    work_orders_per_month: int = 10
    seed: int = 7
    work_order_volume: tuple[float, float] = (200.0, 1500.0)
    load_volume: float = 45.0
    harvest_days: tuple[int, int] = (7, 22)
    delivery_days: tuple[int, int] = (7, 22)
    forwarding_days: tuple[int, int] = (2, 7)
    delivery_lag_median_days: float = 14.0
    delivery_lag_sigma: float = 0.6
    loss_rate: float = 0.01
    loss_sd: float = 0.015
    harvester_volume_bias: float = 0.009
    harvester_volume_noise: float = 0.01
    diameter_bias_sd_mm: float = 2.0
    diameter_noise_mm: float = 3.0
    late_report_share: float = 0.10
    no_harvester_data_share: float = 0.10
    stock_measured_share: float = 0.90
    reject_share: float = 0.01
    redirected_share: float = 0.05
    thinning_share: float = 0.20
    landings: tuple[int, int] = (1, 4)
    landing_diameter_sd: float = 0.10


@dataclass
class SimMonth:
    period: str
    harvest: pd.DataFrame
    deliveries: pd.DataFrame
    truth: pd.DataFrame
    closed_aos: set[str]
    work_orders: WorkOrders


def _diameter_class(diameter_cm: np.ndarray) -> np.ndarray:
    clipped = np.clip(diameter_cm, DIAMETER_MIN_CM, DIAMETER_MAX_CM)
    return (np.floor(clipped / DIAMETER_STEP_CM) * DIAMETER_STEP_CM).astype(int)


def _log_volume(diameter_cm: np.ndarray, length_cm: np.ndarray) -> np.ndarray:
    mid_diameter_m = (diameter_cm + TAPER_CM_PER_M * length_cm / 200) / 100
    return np.pi / 4 * mid_diameter_m**2 * length_cm / 100


def _destination_for(rng: np.random.Generator, size: float) -> str:
    """Sawmills are set up for a dimension, so thin stands go to the thin log mill."""
    level = size + rng.normal(0, 0.08)
    return DESTINATIONS[0] if level < 0.85 else DESTINATIONS[2] if level > 1.05 else DESTINATIONS[1]


def _cut_logs(rng: np.random.Generator, volume: float, sortiment: str, size: float, landings: int, landing_sd: float) -> pd.DataFrame:
    """Logs of one work order and assortment, in harvest order.

    A stand changes along the harvest, so each landing gets its own diameter
    level. Thinning gives thinner logs than final felling.
    """
    mean_diameter = (23.5 if sortiment == "TALL_SAG" else 22.5) * size
    count = max(int(volume / 0.22), 30)

    position = np.sort(rng.uniform(0, 1, count))
    landing = np.minimum((position * landings).astype(int), landings - 1)
    levels = rng.normal(0, landing_sd, landings)
    log_diameter = np.log(mean_diameter) + levels[landing] + rng.normal(0, 0.18, count)
    diameter = np.clip(np.exp(log_diameter), DIAMETER_MIN_CM, DIAMETER_MAX_CM - 0.1)

    # Thicker logs tend to be bucked longer.
    length_position = (diameter - 12) / 24 * (len(LENGTHS_CM) - 1) + rng.normal(0, 1.5, count)
    length = LENGTHS_CM[np.clip(np.round(length_position).astype(int), 0, len(LENGTHS_CM) - 1)]

    log_volume = _log_volume(diameter, length)
    return pd.DataFrame({"position": position, "landing": landing, "d": diameter, "l": length, "v": log_volume})


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
    groups: dict[str, str] = {}
    destinations: dict[str, str] = {}

    for period in periods:
        month_start = pd.Period(period, freq="M").start_time
        activity = SEASONAL_ACTIVITY.get(month_start.month, 1.0)
        for _ in range(max(int(round(params.work_orders_per_month * activity)), 1)):
            work_order_counter += 1
            ao = f"AO{work_order_counter:05d}"
            start = month_start + pd.Timedelta(days=float(rng.uniform(0, 28)))
            duration = rng.integers(*params.harvest_days)
            bias_mm = rng.normal(0, params.diameter_bias_sd_mm)
            lag_factor = rng.lognormal(0, 0.3) * SEASONAL_LAG[month_start.month]
            region = str(rng.choice(list(REGIONS)))
            scale = REGIONS[region]
            thinning = rng.random() < params.thinning_share
            groups[ao] = f"{region}-{'gallring' if thinning else 'slutavverkning'}"
            size = scale * (0.75 if thinning else 1.0) * rng.uniform(0.81, 1.19)
            destinations[ao] = _destination_for(rng, size)
            draw = rng.random()
            produced = SORTIMENT if draw < 0.2 else (SORTIMENT[0],) if draw < 0.7 else (SORTIMENT[1],)

            for sortiment in produced:
                volume = rng.uniform(*params.work_order_volume) * (0.4 if thinning else 1.0)
                landings = int(rng.integers(params.landings[0], params.landings[1] + 1))
                logs = _cut_logs(rng, volume, sortiment, size, landings, params.landing_diameter_sd)
                logs[AO] = ao
                logs[SORT] = sortiment
                actual = destinations[ao]
                if rng.random() < params.redirected_share:
                    actual = str(rng.choice([d for d in DESTINATIONS if d != actual]))
                logs[DEST] = actual
                logs["harvested"] = (start + pd.to_timedelta(logs["position"] * int(duration), unit="D")).dt.floor("D")
                loss = float(np.clip(rng.normal(params.loss_rate, params.loss_sd), 0.0, 0.2))
                logs["lost"] = rng.random(len(logs)) < loss

                # Each landing is cleared in its own time, in loads taken from it.
                logs["load"] = 0
                for landing, block in logs.groupby("landing"):
                    logs.loc[block.index, "load"] = landing * 100000 + (block["v"].cumsum() // params.load_volume).astype(int)

                logs["true_d"] = _diameter_class(logs["d"].to_numpy())
                measured = logs["d"].to_numpy() + (bias_mm + rng.normal(0, params.diameter_noise_mm, len(logs))) / 10
                logs["measured_d"] = _diameter_class(measured)
                # A harvester computes volume from its own diameters, so a diameter error is also a volume error.
                error = 1 + params.harvester_volume_bias + rng.normal(0, params.harvester_volume_noise, len(logs))
                logs["measured_v"] = _log_volume(measured, logs["l"].to_numpy()) * error

                missing = rng.random() < params.no_harvester_data_share
                late = rng.random() < params.late_report_share
                harvest_month = _month_of(logs["harvested"])
                logs["reported"] = (
                    "" if missing else [str(pd.Period(m, freq="M") + (1 if late else 0)) for m in harvest_month]
                )

                # Delivery is one campaign of 1-3 weeks after the harvest, landing by landing.
                last_harvest = logs["harvested"].max()
                gap = rng.lognormal(np.log(params.delivery_lag_median_days), params.delivery_lag_sigma) * lag_factor
                first_delivery = last_harvest + pd.Timedelta(days=float(rng.integers(*params.forwarding_days) + gap))
                campaign_days = int(rng.integers(*params.delivery_days))
                landing_rank = dict(zip(rng.permutation(landings), range(landings)))
                loads = logs.groupby("load")["landing"].first()
                order = sorted(loads.index, key=lambda load: (landing_rank[loads[load]], load))
                delivered = {}
                for position, load in enumerate(order):
                    progress = (position + rng.uniform(-0.5, 0.5)) / max(len(order) - 1, 1)
                    day = round(float(np.clip(progress, 0, 1)) * campaign_days)
                    delivered[load] = (first_delivery + pd.Timedelta(days=day)).floor("D")
                logs["delivered"] = logs["load"].map(delivered)

                for load, block in logs[~logs["lost"]].groupby("load"):
                    delivery_counter += 1
                    stock_measured = rng.random() < params.stock_measured_share
                    method = "stockmatning" if stock_measured else "travmatning"
                    units = len(block) if stock_measured else 3
                    cv = (0.043 if stock_measured else 0.051) / np.sqrt(units)
                    gross = float(block["v"].sum()) * (1 + rng.normal(0, cv))
                    rejected = rng.uniform(0, 2 * params.reject_share)
                    logs.loc[block.index, "paid_v"] = block["v"] * (1 - rejected)
                    delivery_rows.append(
                        {
                            "leverans_id": f"L{delivery_counter:07d}",
                            AO: ao,
                            SORT: sortiment,
                            "mottagningsplats": actual,
                            "leveransdatum": delivered[load].strftime("%Y-%m-%d"),
                            VOL: round(gross * (1 - rejected), 3),
                            BRUTTO: round(gross, 3),
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
        reported = logs[logs["reported"] == period].assign(avverkningsdatum=lambda df: df["harvested"].dt.strftime("%Y-%m-%d"))
        harvest = (
            reported.groupby([AO, SORT, "measured_d", "l", "avverkningsdatum"], as_index=False)
            .agg(**{VOL: ("measured_v", "sum"), LOGS: ("v", "size")})
            .rename(columns={"measured_d": DIA, "l": LEN})
        )
        harvest[VOL] = harvest[VOL].round(3)

        delivered_logs = logs[(~logs["lost"]) & (_month_of(logs["delivered"]) == period)]
        truth = (
            delivered_logs.groupby([AO, SORT, DEST, "true_d", "l"], as_index=False)["paid_v"]
            .sum()
            .rename(columns={"true_d": DIA, "l": LEN, "paid_v": VOL})
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
                work_orders=WorkOrders(destinations, groups),
            )
        )
    return months


def example_price_list() -> pd.DataFrame:
    """Invented prices at the level of public Swedish price lists from 2025."""
    base = {
        "TALL_SAG": {10: 560, 14: 645, 18: 835, 24: 935, 28: 1045},
        "GRAN_SAG": {10: 560, 14: 645, 18: 1010, 24: 1060, 28: 1160},
    }
    limits = {10: 14, 14: 18, 18: 24, 24: 28, 28: None}
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
