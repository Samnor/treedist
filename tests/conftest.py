import pandas as pd
import pytest

from treedist.config import Config
from treedist.invoice import PriceList
from treedist.schema import validate_deliveries, validate_harvest


@pytest.fixture
def cfg():
    """No calibration, so test volumes read directly."""
    return Config(harvester_bias=0.0, handling_loss=0.0, mc_draws=400)


def harvest_frame(period, rows):
    """rows: (ao, sortiment, diameter, length, volume)"""
    df = pd.DataFrame(rows, columns=["arbetsorder", "handelssortiment", "diametergrupp", "langdgrupp", "volym_m3fub"])
    df["antal_stockar"] = (df["volym_m3fub"] / 0.2).round()
    return validate_harvest(df, period)


def delivery_frame(period, rows, cfg, method="travmatning"):
    """rows: (ao, sortiment, volume)"""
    df = pd.DataFrame(rows, columns=["arbetsorder", "handelssortiment", "volym_m3fub"])
    df["leverans_id"] = [f"{period}-{i}" for i in range(len(df))]
    df["leveransdatum"] = f"{period}-15"
    df["matmetod"] = method
    return validate_deliveries(df, period, cfg)


@pytest.fixture
def prices():
    return PriceList.from_frame(
        pd.DataFrame(
            [
                ("TALL", 14, 18, None, None, "600"),
                ("TALL", 18, 24, None, None, "800"),
                ("TALL", 24, None, None, None, "1000.50"),
            ],
            columns=["handelssortiment", "diameter_min", "diameter_max", "langd_min", "langd_max", "pris_kr_per_m3fub"],
        )
    )
