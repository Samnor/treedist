import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from climb import _step, judge  # noqa: E402


def results(scores):
    return pd.DataFrame({"scenario": ["bas"] * len(scores), "prisfel": scores, "poang": scores})


def test_steps_stay_within_bounds():
    assert _step("donor_destination_weight", 16.0, 1.0, 1) == 32.0
    assert _step("donor_group_weight", 1.0, 1.0, -1) == 1.0
    assert _step("min_forwarding_days", 0, 1.0, -1) == 0
    assert _step("pool_remaining_share", 0.5, 0.5, 1) == 0.575


def test_a_consistent_gain_is_taken():
    base = results([10.0, 12.0, 11.0, 13.0, 9.0, 10.5])
    assert judge(base, results([s - 0.5 for s in base["poang"]]))["battre"]


def test_a_gain_within_the_noise_is_not():
    base = results([10.0, 12.0, 11.0, 13.0, 9.0, 10.5])
    noisy = results([9.0, 12.8, 10.2, 13.9, 8.4, 10.6])
    assert not judge(base, noisy)["battre"]
