"""The appendix's first words, and what it calls the mill.

The opening is short: the volume, how many avtalsobjekt, how much the stock held and how much is an estimate, and that
the classes are the harvester's. A source that has a name for the mottagningsplats gets it as the heading, with the id
above it; the files are still called by the id.
"""

import re

import pytest
from openpyxl import load_workbook
from test_sankey import appendix, mixed  # noqa: F401  (mixed is a fixture)
from test_sent import demo, run
from test_utan_avverkning import MILL, bought

from treedist.adapters import validate


def opening(page):
    return re.search(r'<header>.*?<p class="lead">(.*?)</p></header>', page, re.S).group(1)


def test_the_opening_says_what_is_estimated_and_where_the_classes_come_from(mixed):  # noqa: F811
    words = opening(appendix(mixed))
    assert words.startswith("Levererad volym 170,000 m3fub i 2 handelssortiment")
    assert "Virket kommer från 3 avtalsobjekt." in words
    assert "ryms i avtalsobjektens eget lager och är fördelad på klasser så som skördaren mätte stockarna" in words
    # The estimate is named as one, with its share, in the words the diagram and the table use.
    assert re.search(r"Resten, 1[23] %, levererades utöver lagret .*\(egen skörd i snitt\), en uppskattning\.", words)
    assert words.endswith("Volym och handelssortiment är mätningens vid sågverket; diameter och längd kommer från "
                          "skördaren.")
    # Short: the order of the appendix's parts is not told here, and nothing names the program.
    assert "Bilagan visar först" not in words and "treedist" not in words
    assert len(re.findall(r"[.;] ", words)) + 1 <= 6


def test_the_opening_says_how_much_of_the_measured_wood_the_matrix_stands_for(tmp_path):
    assert run(tmp_path, "2026-01", None, bought("2026-01")) == 0
    page = (tmp_path / "out" / "2026-01" / "bilagor" / "sag_klen.html").read_text(encoding="utf-8")
    words = opening(page)
    # The volume is named as the matrix's, since more than that was measured in at the mill.
    assert words.startswith("Volym i matrisen 211,278 m3fub. Det är virket från avverkning med skördardata, 84 % av "
                            "de 251,3 m3fub som mättes in vid sågverket under månaden.")
    assert "Resten, 40,0 m3fub, har ingen avverkning i underlaget och står utanför matrisen." in words
    assert "Virket i matrisen kommer från 2 avtalsobjekt. All volym i matrisen ryms" in words
    # Why it stands outside is in the guide, not in the opening.
    assert "inga diameter- och längdklasser" not in words and "inga diameter- och längdklasser" in page


def test_a_mottagningsplats_with_a_name_is_called_by_it_and_keeps_its_id(tmp_path):
    measured = demo("2026-01")["matning"]
    measured = measured.assign(mottagningsplats_namn=measured["mottagningsplats"].map(lambda m: f"Sågen {m.title()}"))
    assert run(tmp_path, "2026-01", None, measured) == 0
    folder = tmp_path / "out" / "2026-01" / "bilagor"
    page = (folder / "sag_klen.html").read_text(encoding="utf-8")
    assert "<h1>Sågen Sag_Klen</h1>" in page and f"· Mottagningsplats {MILL}</div>" in page
    assert "<title>Bilaga till faktura 2026-01, Sågen Sag_Klen</title>" in page
    first = load_workbook(folder / "sag_klen.xlsx")["Läs först"]["A1"].value
    assert first == f"Bilaga till faktura 2026-01, Sågen Sag_Klen (mottagningsplats {MILL})"


def test_without_a_name_the_mottagningsplats_is_called_by_its_id(tmp_path):
    assert run(tmp_path, "2026-01") == 0
    page = (tmp_path / "out" / "2026-01" / "bilagor" / "sag_klen.html").read_text(encoding="utf-8")
    assert f"<h1>{MILL}</h1>" in page and "· Mottagningsplats" not in page
    assert opening(page).startswith("Levererad volym ")


def test_the_guide_explains_only_the_parts_the_page_has(tmp_path):
    """A source without avverkningsformer gets no explanation of them, and the bought wood is named so that a virkesköp
    felled with a harvester is not taken for it."""
    assert run(tmp_path, "2026-01", None, bought("2026-01")) == 0
    page = (tmp_path / "out" / "2026-01" / "bilagor" / "sag_klen.html").read_text(encoding="utf-8")
    guide = page.split("Så läser du bilagan", 1)[1]
    terms = re.findall(r"<dt>([^<]*)", guide)
    assert ("Avverkningsformer och medelstam" in terms) == ("<h3>Avverkningsformer och medelstam</h3>" in page)
    assert "virke köpt färdigavverkat" in guide and "till exempel köpt virke" not in page
    assert "En avtalsobjekt" not in page and "Den största, " not in page


def test_a_mottagningsplats_has_one_name():
    raw = demo("2026-01")
    names = ["Ena namnet", "Andra namnet"] * len(raw["matning"])
    raw["matning"] = raw["matning"].assign(mottagningsplats_namn=names[:len(raw["matning"])])
    with pytest.raises(ValueError, match="flera olika mottagningsplats_namn"):
        validate(raw, "2026-01")
