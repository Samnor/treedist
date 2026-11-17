"""A month cannot quietly repeat or contradict what earlier months sent.

The ledger keeps volumes, not which loads and harvest rows they came from, so these are checked against the files
each run leaves beside it: a load billed again, a harvest sent again, a calibration changed under the stock.
"""

from pathlib import Path

import pandas as pd
import pytest

from treedist.adapters import validate
from treedist.cli import main

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


def demo(period):
    return {name: pd.read_csv(DEMO / f"{name}_{period}.csv", dtype=str) for name in ("produktion", "matning")}


def run(tmp_path, period, harvest=None, deliveries=None, *extra):
    """Run one demo month, with the harvest or deliveries replaced, against the state in tmp_path."""
    files = demo(period)
    for name, frame in (("produktion", harvest), ("matning", deliveries)):
        if frame is not None:
            files[name] = frame
    paths = {}
    for name, frame in files.items():
        paths[name] = tmp_path / "in" / f"{name}_{period}.csv"
        paths[name].parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(paths[name], index=False)
    argv = ["run", "--period", period, "--produktion", str(paths["produktion"]), "--matning", str(paths["matning"]),
            "--avtalsobjekt", str(DEMO / f"avtalsobjekt_{period}.csv"),
            "--state", str(tmp_path / "state"), "--out", str(tmp_path / "out" / period), *extra]
    return main(argv)


def test_a_load_from_an_earlier_month_is_not_billed_again(tmp_path, capsys):
    assert run(tmp_path, "2026-01") == 0
    february = demo("2026-02")["matning"]
    repeated = pd.concat([february, demo("2026-01")["matning"].head(1)], ignore_index=True)
    assert run(tmp_path, "2026-02", None, repeated) == 1
    assert "levererades redan en tidigare månad" in capsys.readouterr().err
    assert not (tmp_path / "state" / "2026-02").exists()


def test_a_load_reversed_and_measured_again_may_come_back(tmp_path):
    assert run(tmp_path, "2026-01") == 0
    load = demo("2026-01")["matning"].head(1)
    reversed_ = load.assign(volym_m3fub="-" + load["volym_m3fub"], brutto_m3fub="-" + load["brutto_m3fub"],
                            leveransdatum="2026-02-03", matdatum="2026-02-03")
    remeasured = load.assign(volym_m3fub="40.0", brutto_m3fub="40.5", leveransdatum="2026-02-03", matdatum="2026-02-03")
    deliveries = pd.concat([demo("2026-02")["matning"], reversed_, remeasured], ignore_index=True)
    assert run(tmp_path, "2026-02", None, deliveries) == 0


def test_a_cumulative_harvest_is_refused(tmp_path, capsys):
    assert run(tmp_path, "2026-01") == 0
    cumulative = pd.concat([demo("2026-01")["produktion"], demo("2026-02")["produktion"]], ignore_index=True)
    # Most of February's export is January's rows again, as a cumulative export of a slow month would be.
    assert run(tmp_path, "2026-02", cumulative.head(len(demo("2026-01")["produktion"]) + 10)) == 1
    assert "kumulativ" in capsys.readouterr().err


def test_a_new_calibration_stops_the_month_unless_accepted(tmp_path, capsys):
    assert run(tmp_path, "2026-01") == 0
    config = tmp_path / "ny.toml"
    config.write_text("harvester_bias = 0.02\n", encoding="utf-8")
    assert run(tmp_path, "2026-02", None, None, "--config", str(config)) == 1
    assert "kalibreringen har ändrats" in capsys.readouterr().err
    assert run(tmp_path, "2026-02", None, None, "--config", str(config), "--tillat-ny-kalibrering") == 0
    assert "harvester_bias" in capsys.readouterr().out


def test_changed_groups_and_parameters_are_pointed_out(tmp_path, capsys):
    assert run(tmp_path, "2026-01") == 0
    capsys.readouterr()
    config = tmp_path / "ny.toml"
    config.write_text("oldest_first = false\n", encoding="utf-8")
    assert run(tmp_path, "2026-02", None, None, "--config", str(config), "--bilaga-langd", "340,400") == 0
    out = capsys.readouterr().out
    assert "OBS: modellens parametrar har ändrats sedan 2026-01: oldest_first" in out
    assert "bilagans grupper har ändrats" in out


def written_off(tmp_path, periods):
    """Run the months, and give an avtalsobjekt written off after the last of them and an assortment it delivered."""
    for period in periods:
        assert run(tmp_path, period) == 0
    closed = pd.read_csv(tmp_path / "state" / periods[-1] / "avslutade.csv", dtype=str)
    ao = sorted(closed.loc[closed["period"] == periods[-1], "avtalsobjekt"])[0]
    # A delivery of an assortment the avtalsobjekt has harvested: one it has not would stop the month.
    delivered = pd.concat([demo(p)["matning"] for p in periods])
    return ao, delivered.loc[delivered["avtalsobjekt"] == ao, "handelssortiment"].iloc[0]


def test_a_written_off_contract_object_that_delivers_again_is_pointed_out(tmp_path, capsys):
    ao, sortiment = written_off(tmp_path, ("2026-01", "2026-02", "2026-03"))
    capsys.readouterr()
    april = demo("2026-04")["matning"]
    late = april.head(1).assign(avtalsobjekt=ao, handelssortiment=sortiment, producerat_handelssortiment=sortiment,
                                leveransnummer="SEN1")
    assert run(tmp_path, "2026-04", None, pd.concat([april, late], ignore_index=True)) == 0
    out = capsys.readouterr().out
    assert f"som skrivits av levererar igen: {ao}" in out
    assert "fördelas som avtalsobjektets hela skörd, en uppskattning" in out


def test_a_delivery_measured_after_the_write_off_is_pointed_out(tmp_path, capsys):
    ao, sortiment = written_off(tmp_path, ("2026-01", "2026-02", "2026-03"))
    capsys.readouterr()
    april = demo("2026-04")["matning"].assign(matdatum=lambda d: d["leveransdatum"])
    # Driven March 28, before the write-off after March, and measured April 2.
    late = april.head(1).assign(avtalsobjekt=ao, handelssortiment=sortiment, producerat_handelssortiment=sortiment,
                                leveransnummer="SEN1",
                                leveransdatum="2026-03-28", matdatum="2026-04-02")
    assert run(tmp_path, "2026-04", None, pd.concat([april, late], ignore_index=True)) == 0
    out = capsys.readouterr().out
    assert f"skrevs av innan alla deras leveranser var inmätta: {ao}" in out
    assert "som skrivits av levererar igen" not in out


def test_check_reports_what_a_run_would_refuse(tmp_path, capsys):
    assert run(tmp_path, "2026-01") == 0
    repeated = pd.concat([demo("2026-02")["matning"], demo("2026-01")["matning"].head(1)], ignore_index=True)
    path = tmp_path / "upprepad.csv"
    repeated.to_csv(path, index=False)
    argv = ["check", "--period", "2026-02", "--produktion", str(DEMO / "produktion_2026-02.csv"), "--matning", str(path),
            "--avtalsobjekt", str(DEMO / "avtalsobjekt_2026-02.csv"), "--state", str(tmp_path / "state")]
    assert main(argv) == 1
    assert "tidigare månader" in capsys.readouterr().out


def test_a_work_order_with_two_different_rows_is_refused():
    raw = {
        "produktion": demo("2026-01")["produktion"],
        "matning": demo("2026-01")["matning"],
        "avtalsobjekt": pd.DataFrame({"avtalsobjekt": ["AO00001", "AO00001"], "transport_avslutad": ["true", "false"]}),
    }
    with pytest.raises(ValueError, match="flera rader som skiljer sig åt"):
        validate(raw, "2026-01")
    raw["avtalsobjekt"] = pd.DataFrame({"avtalsobjekt": ["AO00001", "AO00001"], "transport_avslutad": ["true"] * 2})
    validate(raw, "2026-01")


def test_check_shows_loads_that_reached_the_source_late(tmp_path, capsys):
    # A January load whose volume was missing at January's run comes with February's deliveries, with its own date.
    january = demo("2026-01")["matning"]
    held_back, rest = january.head(1), january.iloc[1:]
    assert run(tmp_path, "2026-01", None, rest) == 0
    late = pd.concat([demo("2026-02")["matning"], held_back], ignore_index=True)
    path = tmp_path / "sen.csv"
    late.to_csv(path, index=False)
    argv = ["check", "--period", "2026-02", "--produktion", str(DEMO / "produktion_2026-02.csv"), "--matning", str(path),
            "--avtalsobjekt", str(DEMO / "avtalsobjekt_2026-02.csv"), "--state", str(tmp_path / "state")]
    assert main(argv) == 0
    shown = capsys.readouterr().out
    # Its measuring date says it belonged to January: it reached the source after January's run.
    assert "1 lass" in shown and "mättes in före perioden (2026-01)" in shown
    assert run(tmp_path, "2026-02", None, late) == 0


def test_check_shows_loads_driven_last_month_and_accounted_for_now(tmp_path, capsys):
    january = demo("2026-01")["matning"]
    held_back, rest = january.head(1), january.iloc[1:]
    assert run(tmp_path, "2026-01", None, rest) == 0
    february = demo("2026-02")["matning"].assign(matdatum=lambda d: d["leveransdatum"])
    late = pd.concat([february, held_back.assign(matdatum="2026-02-02")], ignore_index=True)
    path = tmp_path / "redovisad.csv"
    late.to_csv(path, index=False)
    argv = ["check", "--period", "2026-02", "--produktion", str(DEMO / "produktion_2026-02.csv"), "--matning", str(path),
            "--avtalsobjekt", str(DEMO / "avtalsobjekt_2026-02.csv"), "--state", str(tmp_path / "state")]
    assert main(argv) == 0
    shown = capsys.readouterr().out
    assert "1 lass" in shown and "kördes före perioden (2026-01) och mättes in i perioden" in shown
    assert "kom till källan efter förra körningen" not in shown
    assert run(tmp_path, "2026-02", None, late) == 0


def test_check_with_the_day_method_points_at_loads_driven_before_the_felling(tmp_path, capsys):
    january = demo("2026-01")["matning"].assign(leveransdatum="2026-01-01")
    path = tmp_path / "tidig.csv"
    january.to_csv(path, index=False)
    argv = ["check", "--period", "2026-01", "--produktion", str(DEMO / "produktion_2026-01.csv"), "--matning", str(path),
            "--avtalsobjekt", str(DEMO / "avtalsobjekt_2026-01.csv"), "--state", str(tmp_path / "state"), "--modell", "dag"]
    main(argv)
    shown = capsys.readouterr().out
    assert "dagmetoden:" in shown and "Är avverkningsdatum rapportdagen" in shown
    assert run(tmp_path, "2026-01", None, january, "--modell", "dag") == 0
    out = capsys.readouterr().out
    assert "OBS: dagmetoden:" in out
    pages = list((tmp_path / "out" / "2026-01" / "bilagor").glob("*.html"))
    assert pages and all("Varje dags lass har bara tagit virke" in p.read_text(encoding="utf-8") for p in pages)
