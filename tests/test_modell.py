import sys
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import modell  # noqa: E402

from treedist.config import Config, load_config  # noqa: E402


def test_a_saved_model_loads_as_the_same_config(tmp_path, monkeypatch):
    monkeypatch.setattr(modell, "MODELS", tmp_path)
    cfg = replace(Config(), oldest_first=False, donor_group_weight=1.0, intervals=False)
    path = modell.save("prov", cfg, "Ett prov", {"prisfel": 12.3, "prestanda_per_scenario": {"bas": 0.9}})
    assert load_config(path) == cfg
    meta = tomllib.loads(path.read_text(encoding="utf-8"))["modell"]
    assert meta["delar"] == len(modell.parts(cfg)) and meta["prestanda_per_scenario"] == {"bas": 0.9}


def test_complexity_counts_the_parts_a_model_uses():
    assert len(modell.parts(Config())) == len(modell.PARTS)
    minimal = modell.parts(modell._config(modell.MINIMAL))
    assert minimal == ["liggare", "S3", "S4"]


def test_a_model_for_other_code_says_which(tmp_path):
    path = tmp_path / "gammal.toml"
    path.write_text('draw_policy = "dated"\n\n[modell]\nkod = "4a3b0d1"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="4a3b0d1"):
        load_config(path)
