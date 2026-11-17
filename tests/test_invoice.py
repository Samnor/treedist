import pandas as pd
import pytest
from conftest import delivery_frame, harvest_frame

from treedist.core.allocate import close_month
from treedist.core.invoice import build_invoice, round_to_total
from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.dev.prices import PriceList, invoice_total_kr, priced


def rule_frame(rows):
    columns = ["handelssortiment", "diameter_min", "diameter_max", "langd_min", "langd_max", "pris_kr_per_m3fub"]
    return pd.DataFrame(rows, columns=columns)


def test_round_to_total_keeps_the_sum():
    volumes = pd.Series([1.0004, 1.0004, 1.0004, 0.9988])
    assert round_to_total(volumes).sum() == 4000


def test_round_to_total_handles_negative_corrections():
    volumes = pd.Series([0.3334, 0.3333, -0.6667])
    assert round_to_total(volumes).sum() == 0


def test_the_lines_hold_the_measured_volume_exactly(cfg):
    harvest = harvest_frame(
        "2026-01",
        [("A", "TALL", "14", "340", 33.3), ("A", "TALL", "20", "340", 33.3), ("A", "TALL", "26", "340", 33.4)],
    )
    deliveries = delivery_frame("2026-01", [("A", "TALL", 77.777)], cfg)
    output = run_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    assert output.invoice["volym_m3fub"].sum() == pytest.approx(77.777, abs=1e-9)


# Prices only judge the method (treedist.dev.prices); the solution itself bills no money.
def test_amounts_use_the_price_of_the_matching_class(cfg, prices):
    harvest = harvest_frame("2026-01", [("A", "TALL", "26", "340", 10.0), ("A", "TALL", "14", "340", 10.0)])
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "TALL", 20.0)], cfg), "2026-01", set(), cfg)
    invoice = priced(build_invoice(step), prices)
    assert list(invoice["diameterklass"]) == ["14", "26"]
    assert list(invoice["belopp_kr"]) == [6000.0, 10005.0]
    assert invoice_total_kr(invoice) == 16005.0


def test_unpriced_product_is_flagged_not_billed(cfg, prices):
    harvest = harvest_frame("2026-01", [("A", "GRAN", "20", "340", 10.0)])
    step = close_month(Ledger.empty(), harvest, delivery_frame("2026-01", [("A", "GRAN", 10.0)], cfg), "2026-01", set(), cfg)
    invoice = priced(build_invoice(step), prices)
    assert not invoice.loc[0, "prissatt"]
    assert invoice.loc[0, "belopp_kr"] == 0.0


def test_late_harvester_data_adds_no_line_to_the_invoice(cfg):
    january = harvest_frame("2026-01", [("A", "TALL", "20", "340", 10.0)])
    first = close_month(Ledger.empty(), january, delivery_frame("2026-01", [("A", "TALL", 20.0)], cfg), "2026-01", set(), cfg)
    assert first.allocation.groupby("sakerhetsklass")["volym_m3fub"].sum().to_dict() == pytest.approx({"S1": 10.0, "S2": 10.0})
    february = harvest_frame("2026-02", [("A", "TALL", "26", "340", 50.0)])
    second = close_month(first.ledger, february, delivery_frame("2026-02", [], cfg), "2026-02", set(), cfg)
    assert build_invoice(second).empty
    # The estimate is compared with the late harvester data for follow-up only: class changes that add up to nothing.
    assert second.corrections["volym_m3fub"].sum() == pytest.approx(0.0)
    assert second.corrections["volym_m3fub"].abs().sum() == pytest.approx(20.0)


def test_catch_all_only_applies_where_nothing_specific_does():
    prices = PriceList.from_frame(rule_frame([("X", 14, 18, None, None, "600"), ("X", None, None, None, None, "100")]))
    assert prices.price_ore("X", "14", "340") == 60000
    assert prices.price_ore("X", "OKÄND", "OKÄND") == 10000
    assert prices.price_ore("Y", "14", "340") is None


def test_range_upper_limit_is_exclusive(prices):
    assert prices.price_ore("TALL", "16", "340") == 60000
    assert prices.price_ore("TALL", "18", "340") == 80000


def test_overlapping_rules_are_rejected():
    prices = PriceList.from_frame(rule_frame([("X", 14, 20, None, None, "600"), ("X", 18, 24, None, None, "700")]))
    with pytest.raises(ValueError, match="överlappande"):
        prices.price_ore("X", "18", "340")


def test_each_destination_gets_its_own_measured_volume(cfg):
    mills = {"A": "X", "B": "Y"}
    harvest = harvest_frame("2026-01", [("A", "TALL", "14", "340", 100.0), ("B", "TALL", "26", "340", 100.0)])
    harvest["producerat_for_mottagningsplats"] = harvest["avtalsobjekt"].map(mills)
    deliveries = delivery_frame("2026-01", [("A", "TALL", 33.333), ("B", "TALL", 22.222)], cfg)
    deliveries["mottagningsplats"] = deliveries["producerat_for_mottagningsplats"] = deliveries["avtalsobjekt"].map(mills)
    output = run_month(Ledger.empty(), harvest, deliveries, "2026-01", set(), cfg)
    billed = output.invoice.groupby("mottagningsplats")["volym_m3fub"].sum()
    assert billed["X"] == pytest.approx(33.333, abs=1e-9)
    assert billed["Y"] == pytest.approx(22.222, abs=1e-9)
    assert set(output.matrices) == {("X", "TALL"), ("Y", "TALL")}


def test_destination_price_replaces_the_general_price():
    frame = rule_frame([("X", 14, None, None, None, "600"), ("X", 14, None, None, None, "700")])
    frame["mottagningsplats"] = [None, "SAG2"]
    prices = PriceList.from_frame(frame)
    assert prices.price_ore("X", "20", "340", "SAG1") == 60000
    assert prices.price_ore("X", "20", "340", "SAG2") == 70000


def test_length_rules_split_a_diameter_class():
    prices = PriceList.from_frame(
        rule_frame([("X", 14, None, None, 400, "560"), ("X", 14, None, 400, None, "600")])
    )
    assert prices.price_ore("X", "20", "370") == 56000
    assert prices.price_ore("X", "20", "430") == 60000
