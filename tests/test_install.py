"""What someone who installed treedist with pip has: init, selftest and the saved models by name."""

import shutil

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
    # The example and the prototypes each pass check where init puts them, with the demo beside them.
    for example in ("kalla", "kalla_lass", "kalla_koder"):
        findings = check("2026-01", Config(), source=tmp_path / "examples" / example / "kalla.toml")
        assert not [f for f in findings if f.level == FEL], example


def test_init_copies_no_python_caches(tmp_path):
    cache = resources.path("examples") / "kalla" / "__pycache__"
    cache.mkdir(exist_ok=True)
    assert main(["init", str(tmp_path)]) == 0
    assert not list(tmp_path.rglob("__pycache__"))


def test_init_leaves_existing_files_alone(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("egen", encoding="utf-8")
    assert main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "egen"
    assert "Finns redan" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["modeller", "examples", "facit", "AGENTS.md"])
def test_each_resource_is_found(name):
    assert resources.path(name).exists()


@pytest.mark.parametrize("copy", [True, False])
def test_a_selftest_that_differs_says_why_for_a_copy_and_for_an_installed_package(monkeypatch, tmp_path, capsys, copy):
    """Run from a clone or a local copy, a selftest that differs says that the code there changed the numbers; run from
    an installed package, it says that treedist does not count right in this environment."""
    from treedist import cli

    monkeypatch.setattr(cli, "_config", lambda args: Config(harvester_bias=0.02))
    # The demo and its facit where a copy keeps them, or where an installed package does, whichever way the tests
    # themselves run. Copies, not links: a link needs extra rights on Windows.
    places = {"examples": "examples", "facit": "tests/golden"} if copy else {"examples": "examples", "facit": "facit"}
    root = tmp_path / ("kopia" if copy else "_data")
    for name, where in places.items():
        shutil.copytree(resources.path(name), root / where)
    if copy:
        monkeypatch.setattr(resources, "PACKAGED", tmp_path / "inget")
        monkeypatch.setattr(resources, "REPO", root)
    else:
        monkeypatch.setattr(resources, "PACKAGED", root)
    assert main(["selftest"]) == 1
    out = capsys.readouterr().out
    if copy:
        assert "skiljer från facit i den här kopian" in out and "Ändra koden" in out
    else:
        assert "räknar inte som det ska i den här miljön" in out
