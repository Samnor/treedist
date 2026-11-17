import pandas as pd
import pytest

from treedist.config import Config
from treedist.dev.prices import PriceList
from treedist.schema import validate_deliveries, validate_harvest


@pytest.fixture
def cfg():
    """No calibration, so test volumes read directly."""
    return Config(harvester_bias=0.0, handling_loss=0.0)


@pytest.fixture
def model():
    """The same, with the evaluation's Monte Carlo at fewer draws."""
    from treedist.dev.model import Model

    return Model(harvester_bias=0.0, handling_loss=0.0, mc_draws=400)


# The mottagningsplats of a test that has only one.
MILL = "SAG"


def viol3_harvest(df, period):
    """A harvest table with what treedist requires from VIOL 3 filled in where a test leaves it out: wood produced for MILL,
    felled on the month's first day."""
    return df.assign(**{column: value for column, value in (("producerat_for_mottagningsplats", MILL),
                                                            ("avverkningsdatum", f"{period}-01"))
                        if column not in df.columns})


def viol3_deliveries(df, period):
    """A measurement with what treedist requires from VIOL 3 filled in where a test leaves it out: one load per row, driven and
    measured mid-month at MILL, as the assortment produced for it, gross as net."""
    defaults = {
        "leveransnummer": lambda d: [f"{period}-{i}" for i in range(len(d))],
        "producerat_handelssortiment": lambda d: d["handelssortiment"],
        "mottagningsplats": lambda d: MILL,
        "producerat_for_mottagningsplats": lambda d: d["mottagningsplats"],
        "leveransdatum": lambda d: f"{period}-15",
        "matdatum": lambda d: d["leveransdatum"],
        "brutto_m3fub": lambda d: d["volym_m3fub"],
    }
    for column, value in defaults.items():
        if column not in df.columns:
            df = df.assign(**{column: value(df) if len(df) else []})
    return df


def harvest_frame(period, rows):
    """rows: (ao, sortiment, diameter, length, volume)"""
    df = pd.DataFrame(rows, columns=["avtalsobjekt", "producerat_handelssortiment", "diameterklass", "langdklass",
                                     "volym_m3fub"])
    df["antal_stockar"] = (df["volym_m3fub"] / 0.2).round()
    return validate_harvest(viol3_harvest(df, period), period)


def delivery_frame(period, rows, cfg, method="travmatning"):
    """rows: (ao, sortiment, volume)"""
    df = pd.DataFrame(rows, columns=["avtalsobjekt", "handelssortiment", "volym_m3fub"])
    df["matmetod"] = method
    return validate_deliveries(viol3_deliveries(df, period), period)


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


def checked_harvest(df, period):
    """A test's harvest table, validated, with what treedist requires from VIOL 3 filled in."""
    return validate_harvest(viol3_harvest(df, period), period)


def checked_deliveries(df, period):
    """A test's measurement, validated, with what treedist requires from VIOL 3 filled in."""
    return validate_deliveries(viol3_deliveries(df, period), period)
