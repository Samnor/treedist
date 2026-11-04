"""What someone who installed treedist with pip has: init, selftest and the saved models by name."""

import pytest

from treedist import resources
from treedist.check import FEL, check
from treedist.cli import main
from treedist.config import Config, load_config


def test_selftest_passes(capsys):
    assert main(["selftest"]) == 0
    assert capsys.readouterr().out.startswith("OK")


def test_every_saved_model_loads_by_name():
    assert "halv-volym" in resources.models()
    for name in resources.models():
        assert isinstance(load_config(resources.model(name)), Config)


def test_a_month_runs_with_a_model_by_name(tmp_path):
    source = resources.path("examples") / "kalla" / "kalla.toml"
    argv = ["run", "--period", "2026-01", "--kalla", str(source), "--state", str(tmp_path / "state"), "--out", str(tmp_path / "out")]
    assert main(argv + ["--modell", "halv-volym"]) == 0


def test_an_unknown_model_names_the_known_ones(capsys):
    assert main(["backtest", "--manader", "3", "--modell", "finns-inte"]) == 1
    assert "halv-volym" in capsys.readouterr().err


def test_a_model_and_a_config_together_are_refused(capsys):
    assert main(["backtest", "--manader", "3", "--modell", "halv", "--config", "x.toml"]) == 1
    assert "inte båda" in capsys.readouterr().err


def test_init_gives_agents_md_and_an_example_that_passes_check(tmp_path):
    assert main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == resources.path("AGENTS.md").read_text(encoding="utf-8")
    findings = check("2026-01", Config(), source=tmp_path / "examples" / "kalla" / "kalla.toml")
    assert not [f for f in findings if f.level == FEL]


def test_init_leaves_existing_files_alone(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("egen", encoding="utf-8")
    assert main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "egen"
    assert "Finns redan" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["modeller", "examples", "facit", "AGENTS.md"])
def test_each_resource_is_found(name):
    assert resources.path(name).exists()
