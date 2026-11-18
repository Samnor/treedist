"""The appendix as a workbook: the Builder that draws a mill's appendix (bilaga.py) as sheets, in the same order,
with the numbers as formulas where they can be.

    <out>/bilagor/<mill>.xlsx   Läs först, the matrix, Källor, Avtalsobjekt, Avverkningsformer, Förklaring, and the rows they
                                are counted from

Every number the appendix shows can be followed here. The volume per source and per contract object is a SUMIFS over the
sheet Fördelning, the month's allocation per contract object, class and source; what the method knows beyond the
allocation (harvest so far, felling days, measures) is given as values, with the appendix's marks as fills.
The codes S1 and S2 stay in a column of their own, since the formulas count by them; the reader's names stand beside
them.
"""

from __future__ import annotations

import pandas as pd

from .appendix import GUIDE_WIDTH, _wrap_across, wrapped_lines
from .bilaga import (
    BASIS,
    FILE_GUIDE,
    NAMES,
    NOTHING_DELIVERED,
    STATE,
    Bilaga,
    beyond_plan,
    certainty_lead,
    coverage,
    differing_stems,
    drifted,
    guide,
    measures_sheet_lead,
    orders_lead,
    origin_lead,
    origin_table,
    overshipped,
    source_name,
)
from .contract import MEASURE, STEM
from .core.allocate import CERTAINTY_TIERS
from .exempel import example_rows
from .schema import AO, SORT, VOL
from .workorders import DIFFERS, DRIFT, MEAN, PROGRESS, SO_FAR

# The sheet Fördelning, as appendix_workbook writes it: A avtalsobjekt, B handelssortiment, C destination,
# D diameterklass, E langdklass, F sakerhetsklass, G volym_m3fub.
ALLOCATION = "Fördelning"
ORIGIN_SHEET = "Anskaffningsform"
ORDER = ["Läs först", None, ORIGIN_SHEET, "Källor", "Avtalsobjekt", "Avverkningsformer", "Förklaring"]


def _fills():
    from openpyxl.styles import Font, PatternFill

    return {"bold": Font(bold=True), "title": Font(bold=True, size=13), "grey": PatternFill("solid", fgColor="EEF1F5"),
            "flag": PatternFill("solid", fgColor="FDF0E1"), "flagged": Font(bold=True)}


def _start(book, name: str, title: str, lead: str, header: list[str], widths: dict[str, float] | None = None):
    """A sheet with the appendix's title and words above a table whose header is on row 4."""
    from openpyxl.styles import Alignment

    style = _fills()
    sheet = book.create_sheet(name)
    sheet["A1"], sheet["A1"].font = title, style["title"]
    sheet["A2"] = lead
    sheet["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(len(header), 6))
    for j, text in enumerate(header, start=1):
        cell = sheet.cell(4, j, text)
        cell.font, cell.fill = style["bold"], style["grey"]
        cell.alignment = Alignment(wrap_text=True, vertical="bottom")
    sheet.row_dimensions[4].height = 42
    for letter, width in (widths or {}).items():
        sheet.column_dimensions[letter].width = width
    sheet.freeze_panes = "A5"
    return sheet


# Plain text fits about this many more characters than the column's width, which counts digits.
PLAIN = 1.1


def _lines(text: str, width: float) -> int:
    return wrapped_lines(text, width * PLAIN)


# Bold text is about this much wider than the column's characters.
BOLD = 1.15


def _shown(cell) -> int:
    """About how many characters a cell's value takes on screen."""
    value, fmt = cell.value, cell.number_format
    if value is None:
        return 0
    if isinstance(value, str) and value.startswith("="):
        return 6 if "%" in fmt else 10
    if isinstance(value, (int, float)):
        if "%" in fmt:
            return 7
        decimals = len(fmt.split(".")[1]) if "." in fmt else 0
        return len(f"{value:,.{decimals}f}") + 1
    return len(str(value)) + 1


def _fit(sheet, header_row: int = 4) -> None:
    """Widths for the columns the sheet did not set, from the header's longest word and the values; then the header
    and the words above it as tall as their wrapped lines, so no word is broken or cut."""
    from openpyxl.utils import get_column_letter

    header = [c.value for c in sheet[header_row] if c.value is not None]
    widths = []
    for j, title in enumerate(header, start=1):
        letter = get_column_letter(j)
        word = max((len(w) for w in str(title).split()), default=0) * BOLD + 2
        if letter in sheet.column_dimensions and sheet.column_dimensions[letter].width:
            width = max(sheet.column_dimensions[letter].width, word)
            sheet.column_dimensions[letter].width = width
        else:
            values = max((_shown(row[0]) for row in sheet.iter_rows(min_row=header_row + 1, min_col=j, max_col=j)),
                         default=0)
            # Wide enough that no header needs more than three lines.
            width = min(max(word, values, 8, len(str(title)) * BOLD / 3 + 2), 40)
            sheet.column_dimensions[letter].width = width
        widths.append(width)
    lines = max((_lines(t, (w - 1) / BOLD) for t, w in zip(header, widths)), default=1)
    sheet.row_dimensions[header_row].height = 15 * lines + 4
    lead = sheet["A2"].value
    if lead:
        span = sum(widths) + 9 * max(0, 6 - len(widths))
        sheet.row_dimensions[2].height = 15 * _lines(lead, span) + 4


def _mark(cell) -> None:
    style = _fills()
    cell.fill, cell.font = style["flag"], style["flagged"]


def add_sheets(book, b: Bilaga, allocated_rows: int) -> None:
    """Add the appendix's own sheets to the workbook and put every sheet in the appendix's order."""
    span = lambda letter: f"'{ALLOCATION}'!${letter}$2:${letter}${max(allocated_rows, 1) + 1}"  # noqa: E731
    volume, order_col, sort_col, tier_col = span("G"), span("A"), span("B"), span("F")
    _sources(book, b, volume, sort_col, tier_col)
    _orders(book, b, volume, order_col, sort_col, tier_col)
    _measures(book, b.measures)
    matrix = book.worksheets[1].title  # the matrix sheet appendix_workbook made right after Läs först
    _guide(book, matrix, b.output.step.draw_per_day, coverage(b), bool(len(b.origins)))
    # The control on the first sheet compares the matrix with the loads it was built from; these say what those leave
    # out, and where the sheet of anskaffningsformer is.
    notes = [coverage(b)] if coverage(b) else []
    if len(b.origins):
        _origins(book, b)
        notes.append(f"{ORIGIN_SHEET}: all volym som mättes in vid sågverket under månaden per anskaffningsform, med "
                     "volymen utanför matrisen.")
    first = book["Läs först"]
    if b.name:
        first["A1"] = f"Bilaga till faktura {b.period}, {b.name} (mottagningsplats {b.mill})"
    for i, text in enumerate(notes):
        if i == 0:
            first.append([""])
        first.append([text])
        _wrap_across(first, first.max_row, 4, GUIDE_WIDTH)

    names = [s.title for s in book.worksheets]
    wanted = [n if n is not None else matrix for n in ORDER]
    ordered = [n for n in wanted if n in names] + [n for n in names if n not in wanted]
    book._sheets = [book[n] for n in ordered]


def _origins(book, b: Bilaga) -> None:
    """Where the mill's measured wood comes from, per anskaffningsform, and what became of it: the page's table, with
    the sums as formulas."""
    from openpyxl.utils import get_column_letter

    table = origin_table(b.origins)
    header = ["Anskaffningsform", *[f"{source_name(t)}, m3fub" for t in table.columns], "Summa, m3fub", "Andel"]
    sheet = _start(book, ORIGIN_SHEET, "Varifrån virket kommer", origin_lead(b.origins, table=True),
                   header, {"A": 30})
    style = _fills()
    first, last = 5, 4 + len(table)
    sum_col = get_column_letter(len(table.columns) + 2)
    last_source = get_column_letter(len(table.columns) + 1)
    for i, origin in enumerate(table.index, start=first):
        sheet.cell(i, 1, str(origin))
        for j, tier in enumerate(table.columns, start=2):
            sheet.cell(i, j, round(float(table.at[origin, tier]), 3)).number_format = "0.0"
        sheet.cell(i, len(table.columns) + 2, f"=SUM(B{i}:{last_source}{i})").number_format = "0.0"
        sheet.cell(i, len(table.columns) + 3, f"={sum_col}{i}/{sum_col}${last + 1}").number_format = "0 %"
    total = last + 1
    sheet.cell(total, 1, "Summa")
    for j in range(2, len(table.columns) + 3):
        letter = get_column_letter(j)
        sheet.cell(total, j, f"=SUM({letter}{first}:{letter}{last})").number_format = "0.0"
    sheet.cell(total, len(table.columns) + 3, f"={sum_col}{total}/{sum_col}${total}").number_format = "0 %"
    for cell in sheet[total]:
        cell.font, cell.fill = style["bold"], style["grey"]
    _fit(sheet)


def _sources(book, b: Bilaga, volume, sort_col, tier_col) -> None:
    volumes = b.volumes
    sortiments = [str(s) for s in volumes.index]
    header = ["Fördelningens källa", "Kod", "Mätt eller uppskattad", "Bygger på", *[f"{s}, m3fub" for s in sortiments],
              "Summa, m3fub", "Andel av matrisen"]
    sheet = _start(book, "Källor", "Hur matrisen togs fram", certainty_lead(volumes, b.mill, table=True), header,
                   {"A": 24, "B": 6, "C": 22, "D": 60})
    from openpyxl.styles import Alignment
    from openpyxl.utils import get_column_letter

    first, last = 5, 4 + len(CERTAINTY_TIERS)
    sum_col = get_column_letter(5 + len(sortiments))
    for i, tier in enumerate(CERTAINTY_TIERS):
        r = first + i
        sheet.cell(r, 1, NAMES[tier])
        sheet.cell(r, 2, tier)
        sheet.cell(r, 3, STATE[tier])
        built_on = sheet.cell(r, 4, BASIS[tier])
        built_on.alignment = Alignment(wrap_text=True, vertical="top")
        for j in (1, 2, 3):
            sheet.cell(r, j).alignment = Alignment(vertical="top")
        sheet.row_dimensions[r].height = 15 * _lines(built_on.value, 58) + 2
        for j, sortiment in enumerate(sortiments, start=5):
            sheet.cell(r, j, f'=SUMIFS({volume},{tier_col},$B{r},{sort_col},"{sortiment}")').number_format = "0.0"
        sheet.cell(r, 5 + len(sortiments), f"=SUM(E{r}:{get_column_letter(4 + len(sortiments))}{r})" if sortiments
                   else 0).number_format = "0.0"
        sheet.cell(r, 6 + len(sortiments), f"=IF(SUM(${sum_col}${first}:${sum_col}${last})=0,0,"
                   f"{sum_col}{r}/SUM(${sum_col}${first}:${sum_col}${last}))").number_format = "0%"
    total = last + 1
    sheet.cell(total, 1, "Summa").font = _fills()["bold"]
    for j in range(5, 7 + len(sortiments)):
        letter = get_column_letter(j)
        sheet.cell(total, j, f"=SUM({letter}{first}:{letter}{last})").number_format = "0%" if j == 6 + len(
            sortiments) else "0.0"
    _fit(sheet)
    note = sheet.cell(total + 2, 1, "Volymen är den inmätta, i m3fub. Summan per sortiment är matrisens.")
    note.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.merge_cells(start_row=total + 2, start_column=1, end_row=total + 2, end_column=4)
    sheet.row_dimensions[total + 2].height = 15 * _lines(note.value, 24 + 6 + 22 + 60) + 2


def _orders(book, b: Bilaga, volume, order_col, sort_col, tier_col) -> None:
    rows, planned = b.rows, b.planned
    header = ["Avtalsobjekt", "Sortiment", "m3fub till sågverket", "Andel av matrisen", "Medeldiameter, cm",
              "Annan klass än hela skörden", *[f"{NAMES[t]}, andel" for t in CERTAINTY_TIERS],
              "Skördat hittills, m3fub", "Levererat i månaden, m3fub", "Levererat i månaden, andel av skördat", "Kvar i lager, m3fub",
              "Levererat hittills, m3fub", "Planerad volym, m3fub", "Levererat hittills, andel av planerad volym",
              "Första avverkningsdag", "Sista avverkningsdag", "Medeldiameter första halvan, cm",
              "Medeldiameter andra halvan, cm", "Medellängd första halvan, dm", "Medellängd andra halvan, dm"]
    lead = orders_lead(rows, b.mean, planned) if len(rows) else NOTHING_DELIVERED
    sheet = _start(book, "Avtalsobjekt", "Avtalsobjekten bakom matrisen", lead, header, {"A": 13, "B": 13})
    first = 5
    last = first + max(len(rows), 1) - 1
    # A avtalsobjekt, B sortiment, C m3fub, D andel, E medeldiameter, F annan klass, G–H the sources, I skördat,
    # J levererat, K levererat av skördat, L kvar, M levererat hittills, N planerad, O levererat av planerad, P–Q felling
    # days, R–U the halves.
    assert len(CERTAINTY_TIERS) == 2
    for i, row in rows.iterrows():
        r = first + i
        whole = float(planned.get(row[AO], float("nan"))) if len(planned) else float("nan")
        values = [row[AO], row[SORT],
                  f'=SUMIFS({volume},{order_col},$A{r},{sort_col},$B{r})',
                  f"=C{r}/SUM($C${first}:$C${last})",
                  None if pd.isna(row[MEAN]) else round(float(row[MEAN]), 2),
                  None if pd.isna(row[DIFFERS]) else float(row[DIFFERS]),
                  *[f'=IF(C{r}=0,0,SUMIFS({volume},{order_col},$A{r},{sort_col},$B{r},{tier_col},"{t}")/C{r})'
                    for t in CERTAINTY_TIERS],
                  float(row[PROGRESS[0]]), float(row[PROGRESS[1]]),
                  f'=IF(I{r}=0,"",J{r}/I{r})', float(row[PROGRESS[2]]),
                  None if pd.isna(row[SO_FAR]) else float(row[SO_FAR]),
                  None if pd.isna(whole) else whole,
                  f'=IF(OR(M{r}="",N{r}="",N{r}=0),"",M{r}/N{r})',
                  *[row[c] if isinstance(row[c], str) else None for c in DRIFT[:2]],
                  *[None if pd.isna(row[c]) else round(float(row[c]) / (10 if k >= 2 else 1), 2)
                    for k, c in enumerate(DRIFT[2:])]]
        for j, value in enumerate(values, start=1):
            sheet.cell(r, j, value)
        for letter, fmt in (("C", "0.0"), ("D", "0%"), ("E", "0.0"), ("F", "0%"), ("G", "0%"), ("H", "0%"), ("I", "0.0"),
                            ("J", "0.0"), ("K", "0%"), ("L", "0.0"), ("M", "0.0"), ("N", "0"), ("O", "0%"), ("R", "0.0"),
                            ("S", "0.0"), ("T", "0.0"), ("U", "0.0")):
            sheet[f"{letter}{r}"].number_format = fmt
        # The appendix's marks.
        if overshipped(row):
            _mark(sheet[f"K{r}"])
        if len(planned) and beyond_plan(row, planned):
            _mark(sheet[f"O{r}"])
        if drifted(row):
            for letter in "RSTU":
                _mark(sheet[f"{letter}{r}"])
    sheet.auto_filter.ref = f"A4:U{last}"
    _fit(sheet)


def _measures(book, held: pd.DataFrame) -> None:
    differing = differing_stems(held)
    sheet = _start(book, "Avverkningsformer", "Avverkningsformer och medelstam", measures_sheet_lead(held),
                   ["Avtalsobjekt", "Avverkningsform", "Medelstam, m3fub", "Planerad volym, m3fub"], {"A": 13, "B": 18})
    for i, row in enumerate(held.itertuples(index=False), start=5):
        ao = getattr(row, AO)
        sheet.cell(i, 1, ao)
        sheet.cell(i, 2, getattr(row, MEASURE))
        stem = getattr(row, STEM)
        cell = sheet.cell(i, 3, None if pd.isna(stem) else float(stem))
        cell.number_format = "0.00"
        if str(ao) in differing:
            _mark(cell)
        planned = getattr(row, VOL)
        sheet.cell(i, 4, None if pd.isna(planned) else float(planned)).number_format = "0"
    _fit(sheet)


def _guide(book, matrix: str, per_day: bool = False, coverage: str = "", origins: bool = False) -> None:
    from openpyxl.styles import Alignment

    sheet = _start(book, "Förklaring", "Så läser du filen",
                   "Vad flikarna och kolumnerna betyder, och sist ett exempel på hur volym utöver lagret fördelas. "
                   "Diagrammen finns bara i bilagan.",
                   ["Del", "Förklaring"], {"A": 30, "B": 110})
    # The matrix sheet is named after the assortment when the mill has only one, so its row takes the sheet's name.
    parts = [(matrix if key == "matrix_sheet" else term, key) for term, key in FILE_GUIDE]
    for i, (term, text) in enumerate([*guide(parts, per_day, coverage, origins), *example_rows()], start=5):
        sheet.cell(i, 1, term).font = _fills()["bold"]
        cell = sheet.cell(i, 2, text)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.cell(i, 1).alignment = Alignment(wrap_text=True, vertical="top")
        sheet.row_dimensions[i].height = 15 * _lines(text, 110) + 2
    _fit(sheet)
