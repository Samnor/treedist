import sys
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import modell  # noqa: E402

from treedist.config import load_config  # noqa: E402
from treedist.dev.model import Model, load_model  # noqa: E402


def test_a_saved_model_loads_as_the_same_config(tmp_path, monkeypatch):
    monkeypatch.setattr(modell, "MODELS", tmp_path)
    cfg = replace(Model(), oldest_first=False, pool_remaining_share=0.3, intervals=False)
    path = modell.save("prov", cfg, "Ett prov", {"prisfel": 12.3, "prestanda_per_scenario": {"bas": 0.9}})
    assert load_model(path) == cfg
    assert load_config(path) == cfg.method
    meta = tomllib.loads(path.read_text(encoding="utf-8"))["modell"]
    assert meta["delar"] == len(modell.parts(cfg)) and meta["prestanda_per_scenario"] == {"bas": 0.9}


def test_complexity_counts_the_parts_a_model_uses():
    assert len(modell.parts(Model())) == len(modell.PARTS)
    minimal = modell.parts(modell._config(modell.MINIMAL))
    assert minimal == ["liggare", "S2"]


def test_a_model_for_other_code_says_which(tmp_path):
    path = tmp_path / "gammal.toml"
    path.write_text('draw_policy = "dated"\n\n[modell]\nkod = "4a3b0d1"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="4a3b0d1"):
        load_config(path)


def test_every_saved_model_names_every_parameter():
    # A parameter missing from a saved model would take today's default, so the model would change meaning when the
    # code gains a parameter. A model saved before one existed names the value that kept the old behaviour.
    from dataclasses import fields

    from treedist import resources
    from treedist.config import Config

    for name, path in resources.models().items():
        missing = {f.name for f in fields(Config)} - set(tomllib.loads(path.read_text(encoding="utf-8")))
        assert not missing, f"{name} saknar {sorted(missing)}"


def test_a_configuration_file_changes_only_what_it_names_in_a_saved_model(tmp_path):
    from treedist import resources

    base = resources.model("enkel")
    policy = tmp_path / "policy.toml"
    policy.write_text("oldest_first = true\n", encoding="utf-8")
    cfg = load_config(policy, base=base)
    assert cfg == replace(load_config(base), oldest_first=True)
    assert not cfg.stock_per_destination
