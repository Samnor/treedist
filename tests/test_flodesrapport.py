import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from flodesrapport import main  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo"


def test_the_flow_report_follows_the_demo_month_by_month(tmp_path):
    out = tmp_path / "flode.html"
    assert main(["--out", str(out), "--config", str(ROOT / "examples" / "profil_enkel.toml")]) == 0
    report = json.loads(re.search(r"const R = (.*);\n", out.read_text(encoding="utf-8")).group(1))

    assert [m["period"] for m in report["manader"]] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    for month in report["manader"]:
        measured = pd.read_csv(DEMO / f"leverans_{month['period']}.csv")["volym_m3fub"].sum()
        tiers = sum(month["noder"][t]["tal"]["volym"] for t in ("S1", "S2", "S3", "S4"))
        assert abs(month["kpi"]["netto"] - measured) < 1e-3
        assert abs(tiers - measured) < 1e-3
        assert month["kpi"]["facit_prisfel"] is not None
