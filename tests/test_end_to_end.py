import json

import pandas as pd
import pytest

from treedist.backtest import run_backtest
from treedist.cli import main
from treedist.config import Config, load_config
from treedist.simulate import SimParams, simulate


def test_simulator_inputs_look_like_real_input():
    months = simulate(SimParams(months=3, work_orders_per_month=4, seed=1))
    assert [m.period for m in months] == ["2026-01", "2026-02", "2026-03"]
    assert "diametergrupp" not in months[1].deliveries.columns
    assert months[1].truth["volym_m3fub"].sum() > 0


def test_harvest_comes_before_delivery_in_the_simulator():
    months = simulate(SimParams(months=4, work_orders_per_month=4, seed=2))
    first = {}
    for month in months:
        for ao in month.deliveries["arbetsorder"]:
            first.setdefault(ao, month.period)
    harvested = {}
    for month in months:
        for row in month.harvest.itertuples():
            harvested[row.arbetsorder] = min(harvested.get(row.arbetsorder, "9999"), row.avverkningsdatum[:7])
    assert all(harvested[ao] <= period for ao, period in first.items() if ao in harvested)


def test_method_beats_ignoring_the_delivery_lag():
    result = run_backtest(SimParams(months=6, seed=3), Config(mc_draws=200))
    assert result.summary["fel_placerad_andel"] < result.summary["fel_placerad_andel_naiv"] / 2
    assert result.summary["prisfel_kr_m3"] < result.summary["prisfel_kr_m3_naiv"]


def test_measured_volume_stays_close_to_delivered_truth():
    result = run_backtest(SimParams(months=5, seed=4), Config(mc_draws=200))
    ratio = result.per_month["levererat_matt"].sum() / result.per_month["levererat_facit"].sum()
    assert ratio == pytest.approx(1.0, abs=0.01)


def run_cli(sim, state, out, period):
    return main(
        [
            "run",
            "--period", period,
            "--skordning", str(sim / f"skordning_{period}.csv"),
            "--leverans", str(sim / f"leverans_{period}.csv"),
            "--prislista", str(sim / "prislista.csv"),
            "--avslutade-ao", str(sim / f"avslutade_ao_{period}.csv"),
            "--arbetsordrar", str(sim / "arbetsordrar.csv"),
            "--state", str(state),
            "--out", str(out / period),
        ]
    )  # fmt: skip


def test_cli_closes_consecutive_months(tmp_path):
    sim, state, out = tmp_path / "sim", tmp_path / "state", tmp_path / "out"
    assert main(["simulate", "--out", str(sim), "--manader", "3", "--seed", "5"]) == 0
    for period in ("2026-01", "2026-02", "2026-03"):
        assert run_cli(sim, state, out, period) == 0

    march = out / "2026-03"
    invoice = pd.read_csv(march / "faktura_rader.csv", dtype={"diametergrupp": str, "langdgrupp": str})
    deliveries = pd.read_csv(sim / "leverans_2026-03.csv")
    delivered = invoice[invoice["radtyp"] == "LEVERANS"]["volym_m3fub"].sum()
    assert delivered == pytest.approx(deliveries["volym_m3fub"].sum(), abs=0.002)

    per_destination = invoice[invoice["radtyp"] == "LEVERANS"].groupby("destination")["volym_m3fub"].sum()
    measured = deliveries.groupby("mottagningsplats")["volym_m3fub"].sum()
    assert per_destination.to_dict() == pytest.approx(measured.to_dict(), abs=0.002)

    folder = next((march / "matriser").glob("*/GRAN_SAG"))
    matrix = pd.read_csv(folder / "levererat.csv", index_col=0)
    tiers = sum(pd.read_csv(folder / f"levererat_{t}.csv", index_col=0) for t in ("S1", "S2", "S3", "S4"))
    assert (matrix - tiers).abs().max().max() < 0.01
    assert len(list((march / "fakturor").glob("*.md"))) == len(per_destination)

    manifest = json.loads((march / "manifest.json").read_text())
    assert manifest["period"] == "2026-03"
    assert len(manifest["indata"]["leverans"]["sha256"]) == 64


def test_cli_rerun_of_latest_month_gives_the_same_invoice(tmp_path):
    sim, state, out = tmp_path / "sim", tmp_path / "state", tmp_path / "out"
    main(["simulate", "--out", str(sim), "--manader", "2", "--seed", "6"])
    run_cli(sim, state, out, "2026-01")
    run_cli(sim, state, out, "2026-02")
    first = (out / "2026-02" / "faktura_rader.csv").read_text()
    assert run_cli(sim, state, out, "2026-02") == 0
    assert (out / "2026-02" / "faktura_rader.csv").read_text() == first


def test_cli_reports_bad_input_without_traceback(tmp_path, capsys):
    sim, state, out = tmp_path / "sim", tmp_path / "state", tmp_path / "out"
    main(["simulate", "--out", str(sim), "--manader", "2", "--seed", "6"])
    bad = pd.read_csv(sim / "leverans_2026-02.csv")
    bad.loc[0, "leveransdatum"] = "2030-01-01"
    bad.to_csv(sim / "leverans_2026-02.csv", index=False)
    assert run_cli(sim, state, out, "2026-02") == 1
    assert "efter perioden" in capsys.readouterr().err
    assert not state.exists()


def test_config_rejects_unknown_keys(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("design_efect = 3\n")
    with pytest.raises(ValueError, match="Okända nycklar"):
        load_config(path)


def test_config_overrides_volume_method(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('design_effect = 3\n[volume_methods.egen]\nunit_cv = 0.1\ndefault_units = 2\nsystematic_sd = 0.01\n')
    cfg = load_config(path)
    assert cfg.design_effect == 3
    assert cfg.volume_methods["egen"].unit_cv == 0.1
    assert "travmatning" in cfg.volume_methods
