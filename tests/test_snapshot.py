"""A source with only the cumulative harvest: each month sends what has grown, once."""

import pandas as pd
import pytest

from treedist.adapters.snapshot import new_rows


def harvest(rows):
    return pd.DataFrame(rows, columns=["arbetsorder", "handelssortiment", "diametergrupp", "langdgrupp", "volym_m3fub"])


def volumes(frame):
    return {tuple(row[:4]): row[4] for row in frame.itertuples(index=False)}


def test_the_first_month_sends_everything_harvested_so_far(tmp_path):
    sent = new_rows(harvest([("007", "TALL", "20", "430", 10.0)]), "2026-09", tmp_path)
    assert volumes(sent) == {("007", "TALL", "20", "430"): 10.0}
    assert (tmp_path / "2026-09.csv").exists()


def test_the_next_month_sends_only_the_growth_and_logs_decreases(tmp_path):
    new_rows(harvest([("007", "TALL", "20", "430", 10.0), ("008", "TALL", "22", "460", 5.0)]), "2026-09", tmp_path)
    sent = new_rows(harvest([("007", "TALL", "20", "430", 14.0), ("008", "TALL", "22", "460", 4.0),
                             ("009", "GRAN", "18", "400", 3.0)]), "2026-10", tmp_path)
    assert volumes(sent) == {("007", "TALL", "20", "430"): pytest.approx(4.0), ("009", "GRAN", "18", "400"): 3.0}
    logged = pd.read_csv(tmp_path / "2026-10_avvikelser.csv", dtype=str)
    assert logged["arbetsorder"].tolist() == ["008"] and float(logged["volym_m3fub"].iloc[0]) == pytest.approx(-1.0)


def test_a_month_read_again_gives_the_same_rows(tmp_path):
    first = new_rows(harvest([("007", "TALL", "20", "430", 10.0)]), "2026-09", tmp_path)
    again = new_rows(harvest([("007", "TALL", "20", "430", 99.0)]), "2026-09", tmp_path)
    pd.testing.assert_frame_equal(first, again)


def test_a_missing_month_or_a_late_freeze_is_refused(tmp_path):
    new_rows(harvest([("007", "TALL", "20", "430", 10.0)]), "2026-09", tmp_path)
    with pytest.raises(ValueError, match="2026-10 saknas"):
        new_rows(harvest([("007", "TALL", "20", "430", 12.0)]), "2026-11", tmp_path)
    assert not (tmp_path / "2026-11.csv").exists()
    new_rows(harvest([("007", "TALL", "20", "430", 11.0)]), "2026-10", tmp_path)
    with pytest.raises(ValueError, match="senare"):
        new_rows(harvest([("007", "TALL", "20", "430", 8.0)]), "2026-08", tmp_path)
