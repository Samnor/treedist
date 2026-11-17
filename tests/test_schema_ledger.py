import pandas as pd
import pytest
from conftest import checked_deliveries, checked_harvest, delivery_frame, harvest_frame, viol3_deliveries, viol3_harvest

from treedist.core.allocate import close_month
from treedist.core.ledger import Ledger, load_for_period
from treedist.schema import sorted_groups


def harvest_row(**overrides):
    row = {
        "avtalsobjekt": "A",
        "producerat_handelssortiment": "TALL",
        "diameterklass": "14",
        "langdklass": "340",
        "volym_m3fub": "1,5",
    }
    return pd.DataFrame([row | overrides])


def delivery_row(**overrides):
    row = {
        "leveransnummer": "L1",
        "avtalsobjekt": "A",
        "handelssortiment": "TALL",
        "leveransdatum": "2026-01-15",
        "volym_m3fub": "30",
    }
    return pd.DataFrame([row | overrides])


def test_swedish_decimal_comma_is_accepted():
    assert checked_harvest(harvest_row(), "2026-01")["volym_m3fub"].iloc[0] == 1.5


def test_numeric_groups_are_normalized_and_sorted():
    harvest = checked_harvest(harvest_row(diameterklass="14.0"), "2026-01")
    assert harvest["diameterklass"].iloc[0] == "14"
    assert sorted_groups(["OKÄND", "20", "-", "4", "14"]) == ["4", "14", "20", "-", "OKÄND"]


def test_zero_volume_rows_are_dropped():
    assert checked_harvest(harvest_row(volym_m3fub="0"), "2026-01").empty


def test_missing_column_is_rejected():
    with pytest.raises(ValueError, match="kolumner saknas"):
        checked_harvest(harvest_row().drop(columns="langdklass"), "2026-01")


def test_negative_volume_is_rejected():
    with pytest.raises(ValueError, match="negativt"):
        checked_harvest(harvest_row(volym_m3fub="-1"), "2026-01")


def test_harvest_dated_after_period_is_rejected():
    with pytest.raises(ValueError, match="efter perioden"):
        checked_harvest(harvest_row(avverkningsdatum="2026-02-01"), "2026-01")


def test_harvest_month_follows_the_date_not_the_report():
    harvest = checked_harvest(harvest_row(avverkningsdatum="2025-11-20"), "2026-01")
    assert harvest["avverkningsdatum"].iloc[0] == "2025-11-20"


def test_delivery_after_period_is_rejected(cfg):
    with pytest.raises(ValueError, match="efter perioden"):
        checked_deliveries(delivery_row(leveransdatum="2026-02-01"), "2026-01")


def test_delivery_transported_before_the_accounting_month_is_kept(cfg):
    out = checked_deliveries(delivery_row(leveransdatum="2025-12-31"), "2026-01")
    assert out["leveransdatum"].iloc[0] == pd.Timestamp("2025-12-31")


def test_a_load_driven_last_month_and_accounted_for_now_keeps_both_dates(cfg):
    out = checked_deliveries(delivery_row(leveransdatum="2025-12-30", matdatum="2026-01-02"), "2026-01")
    assert out["leveransdatum"].iloc[0] == pd.Timestamp("2025-12-30")
    assert out["matdatum"].iloc[0] == pd.Timestamp("2026-01-02")


def test_accounting_before_the_transport_or_after_the_period_is_rejected(cfg):
    with pytest.raises(ValueError, match="matdatum före leveransdatum"):
        checked_deliveries(delivery_row(leveransdatum="2026-01-15", matdatum="2026-01-14"), "2026-01")
    with pytest.raises(ValueError, match="matdatum saknas eller ligger efter perioden"):
        checked_deliveries(delivery_row(leveransdatum="2026-01-30", matdatum="2026-02-02"), "2026-01")


def test_duplicate_delivery_is_rejected(cfg):
    with pytest.raises(ValueError, match="dubblerat"):
        checked_deliveries(pd.concat([delivery_row(), delivery_row()]), "2026-01")


def test_what_the_method_rests_on_from_viol_3_is_required():
    """treedist requires what the method rests on from VIOL 3: every load's id, dates, gross volume and both
    assortments and mottagningsplatser, and every harvested row's date and the mottagningsplats it was produced for.
    Nothing is guessed in their place (docs/kallor.md)."""
    from treedist.schema import validate_deliveries, validate_harvest

    for column in ("leveransnummer", "producerat_handelssortiment", "producerat_for_mottagningsplats", "mottagningsplats",
                   "leveransdatum", "matdatum", "brutto_m3fub"):
        with pytest.raises(ValueError, match=f"kolumner saknas: \\['{column}'\\]"):
            validate_deliveries(viol3_deliveries(delivery_row(), "2026-01").drop(columns=column), "2026-01")
    for column in ("avverkningsdatum", "producerat_for_mottagningsplats"):
        with pytest.raises(ValueError, match=f"kolumner saknas: \\['{column}'\\]"):
            validate_harvest(viol3_harvest(harvest_row(), "2026-01").drop(columns=column), "2026-01")


def test_one_truck_may_carry_several_assortments(cfg):
    mixed = pd.concat([delivery_row(), delivery_row(handelssortiment="GRAN")])
    assert len(checked_deliveries(mixed, "2026-01")) == 2


def test_delivery_with_class_columns_is_rejected(cfg):
    with pytest.raises(ValueError, match="klassinformation"):
        checked_deliveries(delivery_row(diameterklass="14"), "2026-01")


def test_net_above_gross_is_rejected(cfg):
    with pytest.raises(ValueError, match="större än bruttovolym"):
        checked_deliveries(delivery_row(brutto_m3fub="29"), "2026-01")


def test_unknown_measurement_method_is_rejected(cfg):
    with pytest.raises(ValueError, match="okänd matmetod"):
        checked_deliveries(delivery_row(matmetod="gissning"), "2026-01")


def closed_january(cfg):
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0), ("B", "TALL", "20", "340", 10.0)])
    return close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 30.0)], cfg), "2026-01", set(), cfg)


def test_ledger_survives_a_round_trip(tmp_path, cfg):
    saved = closed_january(cfg).ledger
    saved.save(tmp_path)
    loaded = load_for_period(tmp_path, "2026-02")
    assert loaded.period == "2026-01"
    assert loaded.stock["volym_m3fub"].sum() == pytest.approx(saved.stock["volym_m3fub"].sum())
    assert set(loaded.stock["diameterklass"]) == {"14", "20"}


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
