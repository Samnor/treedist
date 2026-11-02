import pandas as pd
import pytest
from conftest import delivery_frame, harvest_frame

from treedist.allocate import close_month
from treedist.ledger import Ledger, load_for_period
from treedist.schema import sorted_groups, validate_deliveries, validate_harvest


def harvest_row(**overrides):
    row = {
        "arbetsorder": "A",
        "handelssortiment": "TALL",
        "diametergrupp": "14",
        "langdgrupp": "340",
        "volym_m3fub": "1,5",
    }
    return pd.DataFrame([row | overrides])


def delivery_row(**overrides):
    row = {
        "leverans_id": "L1",
        "arbetsorder": "A",
        "handelssortiment": "TALL",
        "leveransdatum": "2026-01-15",
        "volym_m3fub": "30",
    }
    return pd.DataFrame([row | overrides])


def test_swedish_decimal_comma_is_accepted():
    assert validate_harvest(harvest_row(), "2026-01")["volym_m3fub"].iloc[0] == 1.5


def test_numeric_groups_are_normalized_and_sorted():
    harvest = validate_harvest(harvest_row(diametergrupp="14.0"), "2026-01")
    assert harvest["diametergrupp"].iloc[0] == "14"
    assert sorted_groups(["OKÄND", "20", "-", "4", "14"]) == ["4", "14", "20", "-", "OKÄND"]


def test_zero_volume_rows_are_dropped():
    assert validate_harvest(harvest_row(volym_m3fub="0"), "2026-01").empty


def test_missing_column_is_rejected():
    with pytest.raises(ValueError, match="kolumner saknas"):
        validate_harvest(harvest_row().drop(columns="langdgrupp"), "2026-01")


def test_negative_volume_is_rejected():
    with pytest.raises(ValueError, match="negativt"):
        validate_harvest(harvest_row(volym_m3fub="-1"), "2026-01")


def test_harvest_dated_after_period_is_rejected():
    with pytest.raises(ValueError, match="efter perioden"):
        validate_harvest(harvest_row(avverkningsdatum="2026-02-01"), "2026-01")


def test_harvest_month_follows_the_date_not_the_report():
    harvest = validate_harvest(harvest_row(avverkningsdatum="2025-11-20"), "2026-01")
    assert harvest["avverkningsmanad"].iloc[0] == "2025-11"


def test_delivery_outside_period_is_rejected(cfg):
    with pytest.raises(ValueError, match="utanför perioden"):
        validate_deliveries(delivery_row(leveransdatum="2026-02-01"), "2026-01", cfg)


def test_duplicate_delivery_is_rejected(cfg):
    with pytest.raises(ValueError, match="dubblerat"):
        validate_deliveries(pd.concat([delivery_row(), delivery_row()]), "2026-01", cfg)


def test_delivery_with_class_columns_is_rejected(cfg):
    with pytest.raises(ValueError, match="klassinformation"):
        validate_deliveries(delivery_row(diametergrupp="14"), "2026-01", cfg)


def test_several_mills_are_rejected(cfg):
    frame = pd.concat([delivery_row(mottagningsplats="X"), delivery_row(leverans_id="L2", mottagningsplats="Y")])
    with pytest.raises(ValueError, match="mottagningsplatser"):
        validate_deliveries(frame, "2026-01", cfg)


def test_unknown_measurement_method_is_rejected(cfg):
    with pytest.raises(ValueError, match="okänd matmetod"):
        validate_deliveries(delivery_row(matmetod="gissning"), "2026-01", cfg)


def closed_january(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0), ("B", "TALL", "20", "340", 10.0)])
    return close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 30.0)], cfg), "2026-01", set(), cfg)


def test_ledger_survives_a_round_trip(tmp_path, cfg):
    saved = closed_january(cfg).ledger
    saved.save(tmp_path)
    loaded = load_for_period(tmp_path, "2026-02")
    assert loaded.period == "2026-01"
    assert loaded.stock["volym_m3fub"].sum() == pytest.approx(saved.stock["volym_m3fub"].sum())
    assert set(loaded.stock["diametergrupp"]) == {"14", "20"}


def test_rerunning_a_month_reads_the_month_before(tmp_path, cfg):
    closed_january(cfg).ledger.save(tmp_path)
    assert load_for_period(tmp_path, "2026-01").period is None


def test_later_snapshots_block_a_rerun(tmp_path, cfg):
    closed_january(cfg).ledger.save(tmp_path)
    (tmp_path / "2026-02").mkdir()
    with pytest.raises(ValueError, match="senare perioder"):
        load_for_period(tmp_path, "2026-01")


def test_skipped_month_is_rejected(tmp_path, cfg):
    closed_january(cfg).ledger.save(tmp_path)
    with pytest.raises(ValueError, match="saknas i liggaren"):
        load_for_period(tmp_path, "2026-03")


def test_no_state_means_cold_start(tmp_path):
    assert load_for_period(tmp_path / "saknas", "2026-01").period is None
