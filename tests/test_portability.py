"""Moving to new data: the golden demo, the adapters, the contract and `check`."""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from treedist.adapters import load
from treedist.check import FEL, VARNING, check
from treedist.cli import main
from treedist.config import Config
from treedist.contract import CONTRACT_VERSION, TABLES, markdown
from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month
from treedist.schema import DELIVERY_REQUIRED, HARVEST_REQUIRED

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "examples" / "demo"
SOURCE = ROOT / "examples" / "kalla" / "kalla.toml"
GOLDEN = Path(__file__).resolve().parent / "golden"
PERIODS = ["2026-01", "2026-02", "2026-03", "2026-04"]


def demo_files(period):
    return {
        "skordning": DEMO / f"skordning_{period}.csv",
        "leverans": DEMO / f"leverans_{period}.csv",
        "prislista": DEMO / "prislista.csv",
        "arbetsordrar": DEMO / "arbetsordrar.csv",
        "avslutade_ao": DEMO / f"avslutade_ao_{period}.csv",
    }


def run_demo(tmp_path, period, *extra):
    files = [arg for key, path in demo_files(period).items() for arg in (f"--{key.replace('_', '-')}", str(path))]
    out = tmp_path / "out" / period
    assert main(["run", "--period", period, *files, "--state", str(tmp_path / "state"), "--out", str(out), *extra]) == 0
    return out


def assert_same(actual: Path, golden: Path):
    pd.testing.assert_frame_equal(pd.read_csv(actual), pd.read_csv(golden), check_exact=False, rtol=1e-9)


def test_the_demo_gives_the_same_invoices_and_matrices_as_before(tmp_path):
    """Moving the code, or a change meant to keep the method, must not change a single number."""
    outs = [run_demo(tmp_path, period) for period in PERIODS]
    for period, out in zip(PERIODS, outs):
        assert_same(out / "faktura_rader.csv", GOLDEN / f"faktura_rader_{period}.csv")
    assert_same(outs[-1] / "matriser_lang.csv", GOLDEN / "matriser_lang_2026-04.csv")
    assert_same(outs[-1] / "avstamning_ao.csv", GOLDEN / "avstamning_ao_2026-04.csv")


def test_a_mapped_source_gives_the_same_invoice_as_the_canonical_files():
    cfg = Config(intervals=False)
    canonical = load("2026-01", cfg, files=demo_files("2026-01"))
    mapped = load("2026-01", cfg, source=SOURCE)
    pd.testing.assert_frame_equal(mapped.harvest, canonical.harvest)
    pd.testing.assert_frame_equal(mapped.deliveries, canonical.deliveries)
    invoices = [
        run_month(Ledger.empty(), i.harvest, i.deliveries, i.prices, "2026-01", i.closed_aos, cfg, i.work_orders).invoice
        for i in (canonical, mapped)
    ]
    pd.testing.assert_frame_equal(*invoices)


def test_a_python_adapter_is_loaded_from_its_file(tmp_path):
    adapter = tmp_path / "egen.py"
    adapter.write_text(
        "import pandas as pd\n"
        f"DEMO = {str(DEMO)!r}\n"
        "def read(period):\n"
        "    return {\n"
        "        'skordning': pd.read_csv(f'{DEMO}/skordning_{period}.csv'),\n"
        "        'leverans': pd.read_csv(f'{DEMO}/leverans_{period}.csv'),\n"
        "        'prislista': pd.read_csv(f'{DEMO}/prislista.csv'),\n"
        "        'arbetsordrar': pd.read_csv(f'{DEMO}/arbetsordrar.csv'),\n"
        "    }\n"
    )
    inputs = load("2026-01", Config(), source=adapter)
    assert inputs.deliveries["volym_m3fub"].sum() == pytest.approx(
        pd.read_csv(DEMO / "leverans_2026-01.csv")["volym_m3fub"].sum()
    )


def test_the_example_adapter_gives_the_same_tables_as_the_example_mapping():
    cfg = Config(intervals=False)
    mapped, adapted = load("2026-01", cfg, source=SOURCE), load("2026-01", cfg, source=SOURCE.with_suffix(".py"))
    for name in ("harvest", "deliveries"):
        pd.testing.assert_frame_equal(getattr(adapted, name), getattr(mapped, name))
    assert adapted.work_orders == mapped.work_orders and adapted.closed_aos == mapped.closed_aos


def mapping_with(tmp_path, old, new):
    text = SOURCE.read_text(encoding="utf-8").replace(old, new)
    text = text.replace('"export/', f'"{SOURCE.parent}/export/').replace('"../demo/', f'"{DEMO}/')
    path = tmp_path / "kalla.toml"
    path.write_text(text, encoding="utf-8")
    return path


def messages(findings, level):
    return " ".join(f.message for f in findings if f.level == level)


def test_check_passes_the_example_source():
    findings = check("2026-01", Config(), source=SOURCE)
    assert not [f for f in findings if f.level == FEL]
    assert "mm" not in messages(findings, VARNING)


def test_check_notices_millimetres_read_as_centimetres(tmp_path):
    source = mapping_with(tmp_path, "diametergrupp = 0.1   # mm -> cm", "")
    assert "ser ut som mm" in messages(check("2026-01", Config(), source=source), VARNING)


def test_check_notices_the_accounting_date_taken_for_the_transport_date(tmp_path):
    source = mapping_with(tmp_path, 'leveransdatum = "TransportDatum"', 'leveransdatum = "RedovisningDatum"')
    assert "redovisningsdatum" in messages(check("2026-01", Config(), source=source), VARNING)


def test_check_notices_gross_and_net_swapped(tmp_path):
    source = mapping_with(tmp_path, 'volym_m3fub = "NettoFub"\nbrutto_m3fub = "BruttoFub"',
                          'volym_m3fub = "BruttoFub"\nbrutto_m3fub = "NettoFub"')
    assert "nettovolym större än bruttovolym" in messages(check("2026-01", Config(), source=source), FEL)


def test_a_mapping_error_names_what_is_allowed(tmp_path):
    source = mapping_with(tmp_path, 'arbetsorder = "AO_Nr"\nhandelssortiment = "Sortiment"',
                          'ao = "AO_Nr"\nhandelssortiment = "Sortiment"')
    (finding,) = check("2026-01", Config(), source=source)
    assert finding.level == FEL and "tillåtna är" in finding.message and "arbetsorder" in finding.message


def test_the_simple_profile_gives_the_same_invoice_without_intervals():
    inputs = load("2026-01", Config(), files=demo_files("2026-01"))
    outputs = [
        run_month(Ledger.empty(), inputs.harvest, inputs.deliveries, inputs.prices, "2026-01", inputs.closed_aos,
                  Config(intervals=intervals), inputs.work_orders)
        for intervals in (True, False)
    ]
    pd.testing.assert_frame_equal(outputs[0].invoice, outputs[1].invoice)
    assert all(m.p05 is None for m in outputs[1].matrices.values())


def test_a_ledger_from_another_contract_version_is_refused(tmp_path):
    run_demo(tmp_path, "2026-01", "--config", str(ROOT / "examples" / "utan_intervall.toml"))
    version = tmp_path / "state" / "2026-01" / "kontrakt.json"
    assert json.loads(version.read_text())["kontrakt"] == CONTRACT_VERSION
    version.write_text(json.dumps({"kontrakt": CONTRACT_VERSION + 1}))
    with pytest.raises(ValueError, match="kontraktsversion"):
        Ledger.load(tmp_path / "state", "2026-01")


def test_the_contract_is_what_validation_requires():
    assert HARVEST_REQUIRED == ["arbetsorder", "handelssortiment", "diametergrupp", "langdgrupp", "volym_m3fub"]
    assert DELIVERY_REQUIRED == ["arbetsorder", "handelssortiment", "volym_m3fub"]
    text = markdown()
    assert all(f"(`{key}`)" in text for key in TABLES)


def test_check_notices_every_mistake_in_the_catalog_and_warns_about_no_correct_source():
    sys.path.insert(0, str(ROOT / "scripts"))
    from portability_bench import MISTAKES, false_alarms, mistakes

    assert mistakes() == len(MISTAKES)
    assert false_alarms(None) == 0


def test_a_file_in_treedists_own_format_needs_only_its_name(tmp_path):
    text = SOURCE.read_text(encoding="utf-8").replace('"export/', f'"{SOURCE.parent}/export/').replace('"../demo/', f'"{DEMO}/')
    head, _, _ = text.partition("[prislista]")
    path = tmp_path / "kalla.toml"
    path.write_text(head + f'[prislista]\nfil = "{DEMO}/prislista.csv"\n\n[avslutade_ao]\nfil = "{DEMO}/avslutade_ao_{{period}}.csv"\n',
                    encoding="utf-8")
    assert load("2026-01", Config(), source=path).prices.rules == load("2026-01", Config(), source=SOURCE).prices.rules


def test_check_refuses_a_negative_unit_count(tmp_path):
    adapter = tmp_path / "vand.py"
    adapter.write_text(
        "import pandas as pd\n"
        f"DEMO = {str(DEMO)!r}\n"
        "def read(period):\n"
        "    loads = pd.read_csv(f'{DEMO}/leverans_{period}.csv')\n"
        "    back = loads.head(1).assign(volym_m3fub=lambda t: -t.volym_m3fub, brutto_m3fub=lambda t: -t.brutto_m3fub,\n"
        "                                antal_matenheter=lambda t: -t.antal_matenheter)\n"
        "    return {'skordning': pd.read_csv(f'{DEMO}/skordning_{period}.csv'), 'leverans': pd.concat([loads, back]),\n"
        "            'prislista': pd.read_csv(f'{DEMO}/prislista.csv'), 'arbetsordrar': pd.read_csv(f'{DEMO}/arbetsordrar.csv')}\n"
    )
    findings = check("2026-01", Config(intervals=False), source=adapter)
    assert "antal_matenheter är negativt på 1 rader" in messages(findings, FEL)
