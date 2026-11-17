"""What a TOML mapping can say besides names and units: a column from another file, codes for names, and ids
written another way. Each stops rather than guesses, and says what is allowed."""

from pathlib import Path

import pandas as pd
import pytest

from treedist.adapters import load
from treedist.config import Config
from treedist.core.ledger import Ledger
from treedist.core.pipeline import run_month

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo"
CANONICAL = {"produktion": DEMO / "produktion_2026-01.csv", "matning": DEMO / "matning_2026-01.csv",
             "avtalsobjekt": DEMO / "avtalsobjekt_2026-01.csv"}


@pytest.mark.parametrize("prototype", ["kalla_lass", "kalla_koder"])
def test_each_prototype_gives_the_canonical_tables_and_lines(prototype):
    got, truth = load("2026-01", source=ROOT / "examples" / prototype / "kalla.toml"), load("2026-01", files=CANONICAL)
    for name in ("harvest", "deliveries"):
        expected = getattr(truth, name)
        order = list(expected.columns)
        pd.testing.assert_frame_equal(getattr(got, name)[order].sort_values(order).reset_index(drop=True),
                                      expected.sort_values(order).reset_index(drop=True), check_dtype=False)
    lines = [run_month(Ledger.empty(), i.harvest, i.deliveries, "2026-01", i.transport_done, Config()).invoice
             for i in (got, truth)]
    pd.testing.assert_frame_equal(*lines)


def write(folder: Path, **files: str) -> None:
    for name, text in files.items():
        (folder / name.replace("_csv", ".csv")).write_text(text, encoding="utf-8")


HARVEST = ("avtalsobjekt,producerat_handelssortiment,producerat_for_mottagningsplats,diameterklass,langdklass,volym_m3fub,"
           "avverkningsdatum\nAO00001,TALL,SAG,20,400,10,2026-01-05\nAO00002,GRAN,SAG,24,430,10,2026-01-05\n")
# What treedist requires of every load, the same for every load here.
VIOL3 = ("producerat_handelssortiment,mottagningsplats,producerat_for_mottagningsplats,leveransdatum,matdatum,brutto_m3fub",
         "SAG,SAG,2026-01-20,2026-01-20")


def mapping(tmp_path: Path, leverans: str, **files: str):
    write(tmp_path, skord_csv=HARVEST, **files)
    (tmp_path / "kalla.toml").write_text(f'[produktion]\nfil = "skord.csv"\n\n[matning]\n{leverans}', encoding="utf-8")
    return load("2026-01", source=tmp_path / "kalla.toml")


LOADS = (f"lass,handelssortiment,volym_m3fub,{VIOL3[0]}\n"
         f"L1,TALL,5,TALL,{VIOL3[1]},5\nL2,GRAN,6,GRAN,{VIOL3[1]},6\n")


def test_a_join_brings_a_column_from_another_file(tmp_path):
    got = mapping(tmp_path, 'fil = "lev.csv"\n[[matning.koppla]]\nfil = "ao.csv"\nnyckel = ["lass", "Lass"]\n'
                            '[matning.kolumner]\nleveransnummer = "lass"\navtalsobjekt = "AO"\n',
                  lev_csv=LOADS, ao_csv="Lass,AO\nL1,AO00001\nL2,AO00002\nL2,AO00002\n")
    assert dict(zip(got.deliveries["leveransnummer"], got.deliveries["avtalsobjekt"])) == {"L1": "AO00001", "L2": "AO00002"}


@pytest.mark.parametrize("other, message", [
    ("lass,AO\nL1,AO00001\n", "1 rader i lev.csv har ingen motsvarighet"),
    ("lass,AO\nL1,AO00001\nL2,AO00002\nL2,AO00009\n", "står mer än en gång"),
    ("lass,AO,volym_m3fub\nL1,AO00001,5\nL2,AO00002,6\n", "finns i både"),
    ("Lassnr,AO\nL1,AO00001\nL2,AO00002\n", "nyckeln 'lass' finns inte i ao.csv"),
])
def test_a_join_stops_rather_than_guesses(tmp_path, other, message):
    with pytest.raises(ValueError, match=message):
        mapping(tmp_path, 'fil = "lev.csv"\n[[matning.koppla]]\nfil = "ao.csv"\nnyckel = "lass"\n'
                          '[matning.kolumner]\nleveransnummer = "lass"\navtalsobjekt = "AO"\n', lev_csv=LOADS, ao_csv=other)


CODED = (f"leveransnummer,avtalsobjekt,handelssortiment,volym_m3fub,{VIOL3[0]}\n"
         f"L1,1,110,5,TALL,{VIOL3[1]},5\nL2,AO-2,210,6,GRAN,{VIOL3[1]},6\n")


def test_codes_become_names_from_the_mapping_or_a_file(tmp_path):
    inline = mapping(tmp_path, 'fil = "lev.csv"\n[matning.koder.handelssortiment]\n"110" = "TALL"\n"210" = "GRAN"\n'
                               '[matning.format.avtalsobjekt]\nta_bort = "AO-"\nbredd = 5\nprefix = "AO"\n', lev_csv=CODED)
    assert list(inline.deliveries["handelssortiment"]) == ["TALL", "GRAN"]
    assert list(inline.deliveries["avtalsobjekt"]) == ["AO00001", "AO00002"]
    from_file = mapping(tmp_path, 'fil = "lev.csv"\n[matning.koder.handelssortiment]\nfil = "koder.csv"\nfran = "kod"\n'
                                  'till = "namn"\n[matning.format.avtalsobjekt]\nta_bort = "AO-"\nbredd = 5\nprefix = "AO"\n',
                        lev_csv=CODED, koder_csv="kod,namn\n110,TALL\n210,GRAN\n")
    pd.testing.assert_frame_equal(from_file.deliveries, inline.deliveries)


def test_a_code_without_a_name_stops(tmp_path):
    with pytest.raises(ValueError, match=r"koderna \['210'\] har inget namn"):
        mapping(tmp_path, 'fil = "lev.csv"\n[matning.koder.handelssortiment]\n"110" = "TALL"\n', lev_csv=CODED)


def test_unknown_settings_name_what_is_allowed(tmp_path):
    with pytest.raises(ValueError, match="tillåtna är"):
        mapping(tmp_path, 'fil = "lev.csv"\n[matning.format.avtalsobjekt]\nsuffix = "X"\n', lev_csv=CODED)
