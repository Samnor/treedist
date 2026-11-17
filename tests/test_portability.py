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
        "produktion": DEMO / f"produktion_{period}.csv",
        "matning": DEMO / f"matning_{period}.csv",
        "avtalsobjekt": DEMO / f"avtalsobjekt_{period}.csv",
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
    outs = [run_demo(tmp_path, period, "--utvecklare") for period in PERIODS]
    for period, out in zip(PERIODS, outs):
        assert_same(out / "faktura_rader.csv", GOLDEN / f"faktura_rader_{period}.csv")
    assert_same(outs[-1] / "utveckling" / "matriser_lang.csv", GOLDEN / "matriser_lang_2026-04.csv")
    assert_same(outs[-1] / "utveckling" / "avstamning_ao.csv", GOLDEN / "avstamning_ao_2026-04.csv")


def test_a_mapped_source_gives_the_same_invoice_as_the_canonical_files():
    cfg = Config()
    canonical = load("2026-01", files=demo_files("2026-01"))
    mapped = load("2026-01", source=SOURCE)
    pd.testing.assert_frame_equal(mapped.harvest, canonical.harvest)
    pd.testing.assert_frame_equal(mapped.deliveries, canonical.deliveries)
    invoices = [
        run_month(Ledger.empty(), i.harvest, i.deliveries, "2026-01", i.transport_done, cfg).invoice
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
        "        'produktion': pd.read_csv(f'{DEMO}/produktion_{period}.csv'),\n"
        "        'matning': pd.read_csv(f'{DEMO}/matning_{period}.csv'),\n"
        "        'avtalsobjekt': pd.read_csv(f'{DEMO}/avtalsobjekt_{period}.csv'),\n"
        "    }\n"
    )
    inputs = load("2026-01", source=adapter)
    assert inputs.deliveries["volym_m3fub"].sum() == pytest.approx(
        pd.read_csv(DEMO / "matning_2026-01.csv")["volym_m3fub"].sum()
    )


def test_the_example_adapter_gives_the_same_tables_as_the_example_mapping():
    mapped, adapted = load("2026-01", source=SOURCE), load("2026-01", source=SOURCE.with_suffix(".py"))
    for name in ("harvest", "deliveries"):
        pd.testing.assert_frame_equal(getattr(adapted, name), getattr(mapped, name))
    # The avtalsobjekt table carries the destined mottagningsplats and the finished transport, translated from J/N.
    assert adapted.transport_done == mapped.transport_done


def mapping_with(tmp_path, old, new):
    text = SOURCE.read_text(encoding="utf-8").replace(old, new)
    # Forward slashes: a Windows path's backslashes are escapes in a TOML string.
    text = text.replace('"export/', f'"{SOURCE.parent.as_posix()}/export/').replace('"../demo/', f'"{DEMO.as_posix()}/')
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
    source = mapping_with(tmp_path, "diameterklass = 0.1   # mm -> cm", "")
    assert "ser ut som mm" in messages(check("2026-01", Config(), source=source), VARNING)


def test_check_notices_the_accounting_date_taken_for_the_transport_date(tmp_path):
    source = mapping_with(tmp_path, 'leveransdatum = "TransportDatum"', 'leveransdatum = "RedovisningDatum"')
    # With the measuring date beside it, an accounting date after the measurement stops the month.
    assert "matdatum före leveransdatum" in messages(check("2026-01", Config(), source=source), FEL)
    # With the measuring date mapped from the accounting date too, the few dates give it away.
    both = mapping_with(tmp_path, 'leveransdatum = "TransportDatum"', 'leveransdatum = "RedovisningDatum"')
    both.write_text(both.read_text(encoding="utf-8").replace('matdatum = "MatDatum"', 'matdatum = "RedovisningDatum"'),
                    encoding="utf-8")
    assert "redovisnings- eller mätdatum" in messages(check("2026-01", Config(), source=both), VARNING)


def test_check_notices_gross_and_net_swapped(tmp_path):
    source = mapping_with(tmp_path, 'volym_m3fub = "NettoFub"\nbrutto_m3fub = "BruttoFub"',
                          'volym_m3fub = "BruttoFub"\nbrutto_m3fub = "NettoFub"')
    assert "nettovolym större än bruttovolym" in messages(check("2026-01", Config(), source=source), FEL)


def test_a_mapping_error_names_what_is_allowed(tmp_path):
    source = mapping_with(tmp_path, 'producerat_handelssortiment = "Sortiment"', 'sortiment = "Sortiment"')
    (finding,) = check("2026-01", Config(), source=source)
    assert finding.level == FEL and "tillåtna är" in finding.message and "avtalsobjekt" in finding.message


def test_the_evaluations_draws_leave_the_month_as_a_run_gives_it():
    from treedist.dev.model import Model, evaluate_month

    inputs = load("2026-01", files=demo_files("2026-01"))
    run = run_month(Ledger.empty(), inputs.harvest, inputs.deliveries, "2026-01", inputs.transport_done, Config())
    evaluated = evaluate_month(Ledger.empty(), inputs.harvest, inputs.deliveries, "2026-01", inputs.transport_done, Model(mc_draws=200))
    pd.testing.assert_frame_equal(run.invoice, evaluated.invoice)
    assert evaluated.draws is not None and not hasattr(run, "draws")


def test_a_ledger_from_another_contract_version_is_refused(tmp_path):
    run_demo(tmp_path, "2026-01", "--config", str(ROOT / "examples" / "utan_intervall.toml"))
    version = tmp_path / "state" / "2026-01" / "kontrakt.json"
    assert json.loads(version.read_text())["kontrakt"] == CONTRACT_VERSION
    version.write_text(json.dumps({"kontrakt": CONTRACT_VERSION + 1}))
    with pytest.raises(ValueError, match="kontraktsversion"):
        Ledger.load(tmp_path / "state", "2026-01")


def test_the_contract_is_what_validation_requires():
    assert HARVEST_REQUIRED == ["avtalsobjekt", "producerat_handelssortiment", "producerat_for_mottagningsplats",
                                "diameterklass", "langdklass", "volym_m3fub", "avverkningsdatum"]
    assert DELIVERY_REQUIRED == ["leveransnummer", "avtalsobjekt", "handelssortiment", "producerat_handelssortiment",
                                 "mottagningsplats", "producerat_for_mottagningsplats", "leveransdatum", "matdatum",
                                 "volym_m3fub", "brutto_m3fub"]
    text = markdown()
    assert all(f"(`{key}`)" in text for key in TABLES)


def test_check_notices_every_mistake_in_the_catalog_and_warns_about_no_correct_source():
    sys.path.insert(0, str(ROOT / "scripts"))
    from portability_bench import MISTAKES, false_alarms, mistakes

    assert mistakes() == len(MISTAKES)
    assert false_alarms(None) == 0


def test_classes_named_by_their_middle_are_noticed_for_classes_of_1_and_2_cm():
    from treedist.check import _midpoints
    from treedist.schema import DIA

    said = lambda classes: [f.message for f in _midpoints(pd.DataFrame({DIA: classes}))]  # noqa: E731
    assert "halva cm (10,5, 11,5, 12,5 …)" in said([10.5, 11.5, 12.5, 14.5])[0]
    assert "udda klasser 2 cm isär" in said([11, 13, 15, 17])[0]
    assert not said([10, 11, 12, 13]) and not said([10, 12, 14]) and not said([10.5, 11, 12.5])


def test_a_file_in_treedists_own_format_needs_only_its_name(tmp_path):
    demo = DEMO.as_posix()
    text = SOURCE.read_text(encoding="utf-8").replace('"export/', f'"{SOURCE.parent.as_posix()}/export/')
    head, _, _ = text.partition("[avtalsobjekt]")
    path = tmp_path / "kalla.toml"
    path.write_text(head + f'[avtalsobjekt]\nfil = "{demo}/avtalsobjekt_2026-02.csv"\n', encoding="utf-8")
    table = pd.read_csv(DEMO / "avtalsobjekt_2026-02.csv", dtype=str)
    done = set(table.loc[table["transport_avslutad"] == "true", "avtalsobjekt"])
    assert done and load("2026-01", source=path).transport_done == done


def test_a_mapping_with_a_price_list_is_told_that_prices_are_not_read(tmp_path):
    path = tmp_path / "kalla.toml"
    path.write_text('[prislista]\nfil = "prislista.csv"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="läser ingen prislista"):
        load("2026-01", source=path)


def test_a_windows_path_in_a_mapping_gets_a_hint(tmp_path):
    path = tmp_path / "kalla.toml"
    path.write_text('[matning]\nfil = "C:\\data\\leverans.csv"\n', encoding="utf-8")
    (finding,) = check("2026-01", Config(), source=path)
    assert finding.level == FEL and "enkla citattecken" in finding.message


def test_a_mapping_saved_with_a_byte_order_mark_is_read(tmp_path):
    source = mapping_with(tmp_path, "", "")
    source.write_text(source.read_text(encoding="utf-8"), encoding="utf-8-sig")
    assert not [f for f in check("2026-01", Config(), source=source) if f.level == FEL]


def test_check_refuses_a_negative_unit_count(tmp_path):
    adapter = tmp_path / "vand.py"
    adapter.write_text(
        "import pandas as pd\n"
        f"DEMO = {str(DEMO)!r}\n"
        "def read(period):\n"
        "    loads = pd.read_csv(f'{DEMO}/matning_{period}.csv')\n"
        "    back = loads.head(1).assign(volym_m3fub=lambda t: -t.volym_m3fub, brutto_m3fub=lambda t: -t.brutto_m3fub,\n"
        "                                antal_matenheter=lambda t: -t.antal_matenheter)\n"
        "    return {'produktion': pd.read_csv(f'{DEMO}/produktion_{period}.csv'), 'matning': pd.concat([loads, back]),\n"
        "            'avtalsobjekt': pd.read_csv(f'{DEMO}/avtalsobjekt_{period}.csv')}\n"
    )
    findings = check("2026-01", Config(), source=adapter)
    assert "antal_matenheter är negativt på 1 rader" in messages(findings, FEL)


def test_check_notices_a_missing_value_written_as_a_key(tmp_path):
    # A data warehouse writes -1 where the harvester gave no mill. Read as an id it is a stock no load takes from.
    harvest = pd.read_csv(DEMO / "produktion_2026-01.csv", dtype=str)
    harvest.loc[harvest.index % 6 == 0, "producerat_for_mottagningsplats"] = "-1"
    harvest.to_csv(tmp_path / "produktion.csv", index=False)
    files = {**demo_files("2026-01"), "produktion": tmp_path / "produktion.csv"}
    said = messages(check("2026-01", Config(), files=files), VARNING)
    assert "producerat_for_mottagningsplats är '-1' på" in said and "17% av volymen" in said
    assert "uppgift som saknas" not in messages(check("2026-01", Config(), files=demo_files("2026-01")), VARNING)


@pytest.mark.parametrize("value, missing", [("-1", True), ("0", True), ("Okänd", True), ("N/A", True), ("-", True),
                                             ("4102", False), ("AO-1", False), ("S0", False), ("10", False)])
def test_only_a_value_that_stands_for_none_is_taken_for_missing(value, missing):
    from treedist.check import NO_VALUE

    assert bool(NO_VALUE.fullmatch(value)) is missing
