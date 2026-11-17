"""The appendix to each mill's invoice, in three forms built from the same grid of litres.

    <mill>.md     the matrices as text, volume or percent per cell; written only with --utvecklare
    <mill>.html   a page with only the matrices, length in dm by diameter in cm, percent of the diameter class per cell,
                  made to print as PDF
    <mill>.xlsx   the rows the matrices are built from, with the matrices as formulas over them, for checking

The invoice lines are whole litres, so every sum in every form adds up exactly.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd

from .core.allocate import CERTAINTY_TIERS, TIER_NAMES
from .core.pipeline import MonthOutput
from .excel_values import save as save_with_values
from .schema import AO, DEST, DIA, LEN, PRODUCED, PRODUCED_FOR, SORT, VOL, sorted_groups

APPENDIX_STYLES = ("volym", "andel")

# The matrix's columns unless the run says otherwise: one per centimetre from 13 to 49, with everything below 13 cm
# in one column and everything from 50 cm in another.
DIAMETER_FLOORS = tuple(range(13, 51))


@dataclass(frozen=True)
class AppendixLayout:
    """How an appendix shows the month; nothing here changes a volume.

    `style` sets the cells of the Markdown appendix; the HTML page always shows percent. `diameter` and
    `length` are band floors in cm. Empty keeps the classes as delivered; otherwise each class goes to the
    band it falls in, so 1 cm classes can be shown as 10 cm or product bands. The diameter is one column per
    centimetre with the two ends gathered, unless the run gives other floors.
    """

    style: str = "volym"
    diameter: tuple[int, ...] = DIAMETER_FLOORS
    length: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.style not in APPENDIX_STYLES:
            raise ValueError(f"Okänd bilaga {self.style!r}; tillåtna är {list(APPENDIX_STYLES)}")
        for name, floors in (("diameter", self.diameter), ("längd", self.length)):
            if list(floors) != sorted(set(floors)):
                raise ValueError(f"Bilagans grupper för {name} ska vara stigande gränser i cm: {list(floors)}")

    @property
    def banded(self) -> bool:
        return bool(self.diameter or self.length)


def markdown_table(df: pd.DataFrame) -> str:
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    rule = "|" + "---|" * len(df.columns)
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, rule, *rows])


def _litres(lines: pd.DataFrame) -> pd.Series:
    return (lines[VOL] * 1000).round().astype(np.int64)


def _band(value: str, floors: tuple[int, ...]) -> str:
    try:
        number = float(value)
    except ValueError:
        return value  # A class without a number stays its own row or column.
    if number < floors[0]:
        return f"<{floors[0]}"
    i = bisect_right(floors, number) - 1
    return f"{floors[i]}+" if i == len(floors) - 1 else f"{floors[i]}–{floors[i + 1]}"


def _bands(floors: tuple[int, ...]) -> list[str]:
    return [f"<{floors[0]}", *[f"{a}–{b}" for a, b in zip(floors, floors[1:])], f"{floors[-1]}+"]


def _ordered(labels, floors: tuple[int, ...]) -> list[str]:
    if not floors:
        return sorted_groups(labels)
    present = set(labels)
    return [b for b in _bands(floors) if b in present] + [g for g in sorted_groups(present) if g not in _bands(floors)]


def grid(lines: pd.DataFrame, layout: AppendixLayout) -> pd.DataFrame:
    """Litres with length classes (or bands) as rows and diameter classes as columns, empty ones dropped.

    The labels stay in cm, as in the data; `_shown` turns them into what the reader sees.
    """
    if layout.diameter:
        lines = lines.assign(**{DIA: lines[DIA].map(lambda v: _band(v, layout.diameter))})
    if layout.length:
        lines = lines.assign(**{LEN: lines[LEN].map(lambda v: _band(v, layout.length))})
    litres = lines.assign(_liter=_litres(lines)).pivot_table(
        index=LEN, columns=DIA, values="_liter", aggfunc="sum", fill_value=0
    )
    litres = litres.reindex(index=_ordered(litres.index, layout.length),
                            columns=_ordered(litres.columns, layout.diameter), fill_value=0)
    # Classes with no volume in any cell say nothing; dropping them keeps every sum.
    return litres.loc[(litres != 0).any(axis=1), (litres != 0).any(axis=0)]


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}".replace(".", ",")


def _label(label, per: int) -> str:
    """A class or band in cm as the reader sees it, in units of `per` cm: 10 for length in dm, 1 for diameter.

    A band one unit wide is shown as its floor alone, like a class.
    """
    text = str(label)
    try:
        if text.startswith("<"):
            return "<" + _number(float(text[1:]) / per)
        if text.endswith("+"):
            return _number(float(text[:-1]) / per) + "+"
        if "–" in text:
            low, high = (float(x) for x in text.split("–"))
            return _number(low / per) if high - low == per else f"{_number(low / per)}–{_number(high / per)}"
        return _number(float(text) / per)
    except ValueError:
        return text  # A class without a number.


def _shown(litres: pd.DataFrame) -> pd.DataFrame:
    """The grid with length in dm and diameter in cm, as the appendix shows them."""
    return litres.rename(index=lambda v: _label(v, 10), columns=lambda v: _label(v, 1))


def _blocks(output: MonthOutput, destination: str):
    """Per assortment: this month's delivered lines and the loads of earlier months credited in this one."""
    invoice = output.invoice[output.invoice[DEST] == destination]
    for sortiment, block in invoice.groupby(SORT, sort=True):
        yield sortiment, block[block["radtyp"] == "LEVERANS"], block[block["radtyp"] != "LEVERANS"]


ALL = "Alla handelssortiment"


def _together(output: MonthOutput, destination: str) -> tuple[str, pd.DataFrame, pd.DataFrame]:
    """The appendix's one matrix: this month's delivered lines and the loads of earlier months credited in this one,
    all assortments together. Named after the assortment when there is only one."""
    blocks = list(_blocks(output, destination))
    name = blocks[0][0] if len(blocks) == 1 else ALL
    delivered = pd.concat([d for _, d, _ in blocks]) if blocks else output.invoice.iloc[0:0]
    earlier = pd.concat([e for _, _, e in blocks]) if blocks else output.invoice.iloc[0:0]
    return name, delivered, earlier


def _per_sortiment(output: MonthOutput, destination: str) -> list[tuple[str, float]]:
    """Delivered m3fub per assortment, for the line that says what the one matrix holds."""
    return [(sortiment, _litres(delivered).sum() / 1000) for sortiment, delivered, _ in _blocks(output, destination)
            if len(delivered)]


def _title(name: str) -> str:
    return f"Levererad volym per längd- och diameterklass, {name[0].lower() + name[1:] if name == ALL else name}"


def _tier_sources(output: MonthOutput, destination: str, sortiment: str) -> str:
    m = output.matrices.get((destination, sortiment))
    if m is None or m.delivered.sum() <= 0:
        return ""
    delivered = m.delivered.sum()
    shares = [f"{t} {m.by_tier[t].sum() / delivered:.0%}" for t in CERTAINTY_TIERS if m.by_tier[t].sum() > 0]
    return f"Fördelningens källa: {', '.join(shares)}."


_CLASSES_NOTE = "Raderna är stockarnas längd i dm och kolumnerna diametern i cm, med klassens nedre gräns."


def _ends(labels, floors: tuple[int, ...], per: int, what: str, unit: str) -> str:
    """What the open groups at the two ends of an axis hold, for those the matrix shows."""
    if not floors:
        return ""
    low, high = _number(floors[0] / per), _number(floors[-1] / per)
    parts = [f"{what} <{low} är allt under {low} {unit}"] if f"<{floors[0]}" in labels else []
    if f"{floors[-1]}+" in labels:
        parts.append(f"{what} {high}+ är allt från {high} {unit} och uppåt")
    return " och ".join([*parts[:1], *[p[0].lower() + p[1:] for p in parts[1:]]]) + "." if parts else ""


def groups_note(output: MonthOutput, destination: str, layout: AppendixLayout) -> str:
    """The sentence that says what the open columns and rows at the ends of the mill's matrices hold; empty when
    the matrices show none."""
    _, delivered, earlier = _together(output, destination)
    grids = [grid(lines, layout) for lines in (delivered, earlier) if len(lines)]
    columns = {c for g in grids for c in g.columns}
    rows = {r for g in grids for r in g.index}
    return " ".join(part for part in (_ends(columns, layout.diameter, 1, "Kolumnen", "cm"),
                                      _ends(rows, layout.length, 10, "Raden", "dm")) if part)
_BANDS_NOTE = "Grupperade klasser är halvöppna: a–b betyder från a till under b, a+ betyder a och mer och <a under a."


# Markdown

def _matrix_markdown(litres: pd.DataFrame, shares: bool) -> str:
    litres = _shown(litres)
    columns = litres.sum(axis=0)
    if shares:
        shown = litres.apply(lambda col: col.map(lambda v: f"{100 * v / col.sum():.1f}" if v and col.sum() > 0 else ""))
    else:
        shown = litres.map(lambda v: f"{v / 1000:.3f}" if v else "")
    shown["Summa"] = (litres.sum(axis=1) / 1000).map(lambda v: f"{v:.3f}")
    shown.loc["Summa"] = [*(columns / 1000).map(lambda v: f"{v:.3f}"), f"{columns.sum() / 1000:.3f}"]
    return markdown_table(shown.rename_axis("längd, dm").reset_index())


def appendix_markdown(output: MonthOutput, destination: str, layout: AppendixLayout = AppendixLayout()) -> str:
    """The appendix as text: one matrix for all assortments together, and the loads of earlier months credited in this
    one."""
    shares = layout.style == "andel"
    shown_as = (
        "Varje cell är andelen i procent av diameterklassens volym, så varje kolumn summerar till 100. Summorna är i "
        "m3fub, liksom krediterade lass från tidigare månader."
        if shares
        else "Volymerna är i m3fub."
    )
    intro = (f"Levererad volym, alla handelssortiment tillsammans. {_CLASSES_NOTE} Volymen är den inmätta; fördelningen på "
             f"klasser kommer ur skördarens rapportering. {shown_as}" + (f" {_BANDS_NOTE}" if layout.banded else ""))
    lines = [f"# Bilaga till faktura {output.step.period}, {destination}", "", intro, ""]
    name, delivered, earlier = _together(output, destination)
    lines += [f"## {name}", ""]
    if len(delivered):
        parts = ", ".join(f"{sortiment} {volume:.3f}" for sortiment, volume in _per_sortiment(output, destination))
        sources = " ".join(f"{sortiment}: {_tier_sources(output, destination, sortiment)}"
                           for sortiment, _ in _per_sortiment(output, destination)
                           if _tier_sources(output, destination, sortiment))
        lines += [f"Levererat {_litres(delivered).sum() / 1000:.3f} m3fub ({parts}). {sources}".rstrip(), "",
                  _matrix_markdown(grid(delivered, layout), shares), ""]
    if len(earlier):
        lines += ["### Krediterade lass från tidigare månader", "",
                  f"Krediterade lass, netto {_litres(earlier).sum() / 1000:.3f} m3fub.", "",
                  _matrix_markdown(grid(earlier, layout), False), ""]
    lines += ["Fördelningens källa:", "", *[f"- {t}: {name}" for t, name in TIER_NAMES.items()], ""]
    return "\n".join(lines)


def appendix_rows(output: MonthOutput, destination: str) -> pd.DataFrame:
    invoice = output.invoice[output.invoice[DEST] == destination]
    return invoice[["radtyp", SORT, DIA, LEN, VOL, *[f"andel_{t}" for t in CERTAINTY_TIERS]]]


# HTML, for print

def _sv(value: float, decimals: int) -> str:
    """Swedish number: decimal comma, a no-break space between thousands (a narrow one vanishes in small type)."""
    return f"{value:,.{decimals}f}".replace(",", "\u00a0").replace(".", ",")


# With more columns than this the cells are set tighter, and the labels of the first and last column may wrap.
DENSE = 32
# The page inside its margins: 273 mm, in points.
PAGE = 273 * 72 / 25.4


def _em(text: str) -> float:
    """Roughly how wide a cell's text is, in em: 0.6 per character and half of that for a separator."""
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    return sum(0.3 if ch in ",.\u00a0 " else 0.6 for ch in text)


def _font(widths: list[float]) -> str:
    """The type for a matrix whose columns, the first and the last included, need `widths` em for their widest cells.

    The more columns the smaller the type, and smaller still when the widest cells would otherwise reach past an A4
    landscape page: a table that is too wide loses its last columns in print.
    """
    columns = len(widths) - 2
    padding = 2 * (1.5 if columns > DENSE else 4) + 0.5
    largest = 9 if columns <= 16 else 8 if columns <= 24 else 7 if columns <= 32 else 6 if columns <= 42 else 5
    for size in (9, 8, 7, 6, 5.5, 5, 4.5):
        if size <= largest and sum(em * size + padding for em in widths) <= PAGE:
            return f"{size:g}pt"
    return "4pt"


def _volume(m3: float, decimals: int) -> str:
    """A volume at `decimals`; one that would round to zero but is not says so, instead of showing 0,0."""
    step = 10.0 ** -decimals
    if m3 and abs(m3) < step / 2:
        return ("&lt;" if m3 > 0 else "&gt;-") + _sv(step, decimals)
    return _sv(m3, decimals)


def _matrix_html(litres: pd.DataFrame, shares: bool) -> str:
    litres = _shown(litres)
    columns = litres.sum(axis=0)
    percent = litres.div(columns.where(columns > 0), axis=1) * 100
    top = float(np.nanmax(percent.to_numpy())) if shares and percent.size else 0.0
    decimals = 1 if shares else 3
    # Large column sums read better in thousands, as in the trade's own tables.
    thousands = shares and columns.abs().max() >= 1_000_000
    dense = len(litres.columns) > DENSE
    corner, total, summed = "Längd, dm", f"Summa, {'tusen ' if thousands else ''}m3fub", "Summa, m3fub"
    foot = [_volume(v / (1_000_000 if thousands else 1000), decimals) for v in columns]
    # What each column needs for its widest cell, to choose the type. In a dense table the first and last column's
    # labels wrap, so they need their longest word only.
    widths = [max(_em(str(c)), _em(f)) for c, f in zip(litres.columns, foot)]
    first = max(_em(word) for label in (corner, total) for word in (label.split() if dense else [label]))
    last = max(_em(word) for word in (summed.split() if dense else [summed]))
    rows = []
    for length in litres.index:
        cells = []
        for j, dia in enumerate(litres.columns):
            litre, share = litres.at[length, dia], percent.at[length, dia]
            if not litre:
                cells.append('<td class="none">–</td>')
                continue
            if shares:
                # A light shade by share, so that the shape of each column shows at a glance.
                alpha = 0.06 + 0.5 * share / top if top > 0 and share > 0 else 0
                # Volume too small to show as a whole percent is still volume, not zero.
                shown = _sv(share, 0) if share >= 0.5 or share < 0 else "&lt;1"
                cells.append(f'<td style="background:rgba(37,99,235,{alpha:.2f})">{shown}</td>')
            else:
                shown = _volume(litre / 1000, 3)
                cells.append(f"<td>{shown}</td>")
            widths[j] = max(widths[j], _em(shown))
        row_sum = _volume(litres.loc[length].sum() / 1000, decimals)
        first, last = max(first, _em(str(length))), max(last, _em(row_sum))
        rows.append(f'<tr><th>{escape(str(length))}</th>{"".join(cells)}<td class="sum">{row_sum}</td></tr>')
    grand = _volume(columns.sum() / 1000, decimals)
    table = '<table class="dense"' if dense else "<table"
    head = "".join(f"<th>{escape(str(c))}</th>" for c in litres.columns)
    return (
        # Two header rows name the axes, instead of a corner cell that reads as a riddle.
        f'{table} style="font-size:{_font([first, *widths, max(last, _em(grand))])}">'
        f'<thead><tr><th class="corner" rowspan="2">{corner}</th><th class="axis" colspan="{len(litres.columns)}">'
        f'Diameter, cm</th><th class="sum" rowspan="2">{summed}</th></tr><tr>{head}</tr></thead><tbody>{"".join(rows)}'
        # The sum row belongs to the body: a footer would be repeated on every page the table spans.
        f'<tr class="total"><th>{total}</th>{"".join(f"<td>{v}</td>" for v in foot)}'
        f'<td class="sum">{grand}</td></tr></tbody></table>'
    )


def first_matrix_html(output: MonthOutput, destination: str, layout: AppendixLayout = AppendixLayout()) -> str:
    """The appendix's matrix, all assortments together, as the appendix shows it, so that another page can start
    from the same matrix."""
    name, delivered, _ = _together(output, destination)
    if not len(delivered):
        return ""
    return (f'<h2>{escape(_title(name))}<span class="total">{_sv(_litres(delivered).sum() / 1000, 3)} m3fub</span>'
            f"</h2>{_matrix_html(grid(delivered, layout), shares=True)}")


def changes_matrix_html(output: MonthOutput, destination: str, layout: AppendixLayout = AppendixLayout()) -> str:
    """The loads of earlier months credited in this one, all assortments together, in m3fub."""
    _, _, earlier = _together(output, destination)
    if not len(earlier):
        return ""
    return ('<div class="changes"><h3>Krediterade lass från tidigare månader, m3fub</h3>'
            f"{_matrix_html(grid(earlier, layout), shares=False)}</div>")


def appendix_lead(output: MonthOutput, destination: str) -> str:
    """The delivered volume, and per assortment when there are several, as the appendix opens with it."""
    _, delivered, _ = _together(output, destination)
    per_sortiment = _per_sortiment(output, destination)
    held = (f" i {len(per_sortiment)} handelssortiment: "
            + ", ".join(f"{sortiment} {_sv(volume, 3)}" for sortiment, volume in per_sortiment)
            + " m3fub" if len(per_sortiment) > 1 else "")
    return f"Levererad volym {_sv(_litres(delivered).sum() / 1000, 3)} m3fub{held}."


# The names the appendix shows for the sources, beside the codes the rows use.
READER_NAMES = {"S1": "Eget lager", "S2": "Egen skörd i snitt"}


def matrix_note(output: MonthOutput, destination: str, layout: AppendixLayout = AppendixLayout()) -> str:
    """How to read the matrix, as the page says it under the matrix."""
    return " ".join(part for part in (
        "Varje cell är andelen i procent av diameterklassens volym, så varje kolumn summerar till 100. Ett streck "
        "betyder ingen volym, och <1 mindre än en halv procent.", _CLASSES_NOTE,
        groups_note(output, destination, layout), "Summorna är i m3fub.") if part)


# Excel, for checking

_SHEET = re.compile(r"[\[\]:*?/\\]")


def _cell(value):
    """A class as a number where it is one, so that Excel's SUMIFS can compare and band it."""
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return value
        return int(number) if number.is_integer() else number
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().date()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return None if pd.isna(value) else value


def _text(value: str) -> str:
    """A string literal in an Excel formula."""
    return '"' + str(value).replace('"', '""') + '"'


def _criteria(label: str, floors: tuple[int, ...], column: str) -> str:
    """SUMIFS criteria for one row or column of the matrix, on the class column `column`."""
    if floors and label.startswith("<"):
        return f',{column},"<{label[1:]}"'
    if floors and label.endswith("+"):
        return f',{column},">={label[:-1]}"'
    if floors and "–" in label:
        low, high = label.split("–")
        return f',{column},">={low}",{column},"<{high}"'
    value = _cell(label)
    return f",{column},{value}" if not isinstance(value, str) else f",{column},{_text(value)}"


# Läs först's columns A to D, in characters: 30 + 3 × 14.
GUIDE_WIDTH = 72


def wrapped_lines(text: str, width: float) -> int:
    """How many lines a text takes when wrapped at whole words in a cell `width` characters wide."""
    width = max(int(width), 1)
    lines, used = 1, 0
    for word in str(text).split():
        if used == 0:
            used = len(word)
        elif used + 1 + len(word) <= width:
            used += 1 + len(word)
        else:
            lines, used = lines + 1, len(word)
        while used > width:  # a word longer than the cell breaks across lines
            lines, used = lines + 1, used - width
    return lines


def _wrap_across(sheet, row: int, last_column: int, width: float) -> None:
    """A long text on one row, wrapped inside the columns up to `last_column`, so it neither spills nor is cut in print."""
    from openpyxl.styles import Alignment

    cell = sheet.cell(row, 1)
    if not cell.value:
        return
    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_column)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    lines = wrapped_lines(cell.value, width * 1.1)  # plain text fits more characters than the width's digits
    if lines > 1:
        sheet.row_dimensions[row].height = 15 * lines + 2


def _printable(sheet, label: str) -> None:
    """A4 landscape, as wide as the page, with the table's header on every page and the sheet named in the footer."""
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.orientation = "landscape"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
    frozen = sheet.freeze_panes
    if frozen:
        header = int("".join(ch for ch in frozen if ch.isdigit())) - 1
        if header >= 1:
            sheet.print_title_rows = f"{header}:{header}"
    sheet.oddFooter.left.text = "Bilaga " + label.replace("&", "&&")
    sheet.oddFooter.center.text = "&A"
    sheet.oddFooter.right.text = "Sida &P av &N"


def _table_sheet(book, name: str, frame: pd.DataFrame, number_formats: dict[str, str] | None = None):
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    sheet = book.create_sheet(name)
    sheet.append(list(frame.columns))
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in frame.itertuples(index=False):
        sheet.append([_cell(v) for v in row])
    for i, column in enumerate(frame.columns, start=1):
        letter = get_column_letter(i)
        sheet.column_dimensions[letter].width = max(10, min(28, len(str(column)) + 2))
        for fmt_column, fmt in (number_formats or {}).items():
            if column == fmt_column:
                for cell in sheet[letter][1:]:
                    cell.number_format = fmt
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    return sheet


def appendix_workbook(path: Path, output: MonthOutput, destination: str, layout: AppendixLayout = AppendixLayout(),
                      harvest: pd.DataFrame | None = None, extra=None) -> None:
    """The rows behind a mill's appendix, and the matrices as SUMIFS formulas over them. `extra(book, rows)` adds the
    appendix's own sheets, given the number of rows in Fördelning, before the workbook is saved."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    step = output.step
    rows = appendix_rows(output, destination).reset_index(drop=True)
    allocation = step.allocation[step.allocation[DEST] == destination]
    changes = step.credits.assign(radtyp="KREDITERING")
    changes = changes[changes[DEST] == destination]
    deliveries = output.deliveries[output.deliveries[DEST] == destination]
    orders = set(deliveries[AO])
    # The harvester's wood, in the reconciliation and in the harvest rows, is shown under the names the workbook has
    # always had: the produced assortment as handelssortiment, the one it was produced for as mottagningsplats.
    balance = step.reconciliation[step.reconciliation[AO].isin(orders)].rename(columns={PRODUCED: SORT})

    # Ranges end at the last row: faster than whole columns, in Excel and in other spreadsheets alike.
    def span(sheet: str, letter: str, length: int) -> str:
        return f"'{sheet}'!${letter}$2:${letter}${max(length, 1) + 1}"

    def rows_col(letter: str) -> str:
        return span("Bilagans rader", letter, len(rows))

    book = Workbook()
    guide = book.active
    guide.title = "Läs först"
    matrix_sheet = _SHEET.sub("_", str(_together(output, destination)[0]))[:31]
    bold, grey = Font(bold=True), PatternFill("solid", fgColor="EEF1F5")
    lines = [
        (f"Bilaga till faktura {step.period}, {destination}", Font(bold=True, size=14)),
        ("Filen innehåller bilagans siffror och raderna de räknas ur, så att de går att kontrollera.", None),
        ("", None),
        ("Flikar", bold),
        ("Flikarna följer bilagan: först matrisen, sedan hur den togs fram, avtalsobjekten bakom den och en förklaring. Sist kommer raderna som allt räknas ur.", None) if extra else ("", None),
        (f"{matrix_sheet}: matrisen i m3fub, med längd i dm som rader och diameter i cm som kolumner, räknad med SUMIFS ur fliken Bilagans rader. Under den står samma matris som procent av diameterklassens volym.", None),
        *([("Källor: hur matrisen togs fram, med volymen per källa och sortiment räknad med SUMIFS ur fliken Fördelning.", None),
           ("Avtalsobjekt: avtalsobjekten bakom matrisen. Volym, andel och källor räknas med SUMIFS ur fliken Fördelning; skörd, leverans och avverkningsdagar är värden. Tonade celler är bilagans markeringar.", None),
           ("Avverkningsformer: avverkningsformerna i avtalsobjekten, med medelstam och planerad volym, när underlaget har dem.", None),
           ("Förklaring: vad flikarna och kolumnerna betyder, och ett exempel på hur volym utöver lagret fördelas. Diagrammen finns bara i bilagan.", None)] if extra else []),
        ("Bilagans rader: volym per sortiment och klass, i hela liter, med andel per källa (S1 och S2). Kolumnen Från fördelningen summerar fliken Fördelning per klass; skillnaden är avrundningen till hela liter.", None),
        ("Fördelning: månadens levererade volym per avtalsobjekt, klass och källa (kolumnen sakerhetsklass), före avrundning.", None),
        ("Krediteringar: lass från tidigare månader som krediterats denna månad.", None),
        ("Mätning: månadens lass till sågverket, som volymen bygger på.", None),
        ("Avstämning: lagret per avtalsobjekt, med ingående lager, skördat, levererat och utgående lager.", None),
        ("Skördardata: månadens skördarrader för avtalsobjekten, när de finns.", None),
        ("", None),
        ("Fördelningens källor, med koderna som raderna och formlerna använder", bold),
        *[(f"{t}: {name}", None) for t, name in (READER_NAMES if extra else TIER_NAMES).items()],
        ("", None),
        ("Kontroll: inmätt volym mot bilagan per sortiment (leverans plus kreditering), m3fub", bold),
    ]
    for text, font in lines:
        guide.append([text])
        if font:
            guide.cell(guide.max_row, 1).font = font
        if text and guide.max_row > 1:
            _wrap_across(guide, guide.max_row, 4, GUIDE_WIDTH)
    guide.column_dimensions["A"].width = 30
    guide.append(["Handelssortiment", "Mätning", "Bilagan", "Skillnad"])
    for cell in guide[guide.max_row]:
        cell.font, cell.fill = bold, grey

    sheets = {}
    for sortiment, delivered, _ in _blocks(output, destination):
        name = _SHEET.sub("_", str(sortiment))[:31]
        while name in sheets.values() or name in ("Läs först", "Bilagans rader", "Fördelning", "Krediteringar",
                                                    "Mätning", "Avstämning", "Skördardata", ALL):
            name = name[:28] + "_" + str(len(sheets))
        sheets[sortiment] = name
        r = guide.max_row + 1
        measured = [span("Mätning", letter, len(deliveries)) for letter in "DB"]
        guide.append([sortiment, f"=SUMIFS({measured[0]},{measured[1]},A{r})",
                      f"=SUMIFS({rows_col('E')},{rows_col('B')},A{r},{rows_col('A')},\"LEVERANS\")"
                      f"+SUMIFS({rows_col('E')},{rows_col('B')},A{r},{rows_col('A')},\"KREDITERING\")",
                      f"=B{r}-C{r}"])
        for cell in guide[r][1:]:
            cell.number_format = "0.000"
    guide.append(["Sortimentet är det inmätta, som faktureras. Skillnaden ska vara 0,000."])
    _wrap_across(guide, guide.max_row, 4, GUIDE_WIDTH)
    for column in "BCD":
        guide.column_dimensions[column].width = 14

    # The matrix, as formulas over the appendix rows: all assortments together, as on the page.
    name, delivered, _ = _together(output, destination)
    sortiment = None if name == ALL else name
    for delivered in ([delivered] if len(delivered) else []):
        sheet = book.create_sheet(ALL if sortiment is None else sheets[sortiment])
        litres = grid(delivered, layout)
        n_rows, n_cols = len(litres.index), len(litres.columns)
        sheet["A1"], sheet["A1"].font = f"{_title(name)}, {step.period}, m3fub", Font(bold=True, size=12)
        sheet["A2"] = " ".join(part for part in (
            "Räknat med SUMIFS ur fliken Bilagans rader, där längden står i cm. Rubrikerna visar längden i dm "
            "och diametern i cm, med klassens nedre gräns.", groups_note(output, destination, layout)) if part)
        header, first = 4, 5
        sheet.cell(header, 1, "Längd, dm \\ diameter, cm")
        for j, dia in enumerate(litres.columns, start=2):
            sheet.cell(header, j, _cell(_label(dia, 1)))
        sum_col = n_cols + 2
        sum_row = first + n_rows
        sheet.cell(header, sum_col, "Summa")
        assortment = "" if sortiment is None else f",{rows_col('B')},{_text(sortiment)}"
        for i, length in enumerate(litres.index):
            r = first + i
            sheet.cell(r, 1, _cell(_label(length, 10)))
            for j, dia in enumerate(litres.columns, start=2):
                formula = (f"=SUMIFS({rows_col('E')},{rows_col('A')},\"LEVERANS\"{assortment}"
                           + _criteria(str(length), layout.length, rows_col("D"))
                           + _criteria(str(dia), layout.diameter, rows_col("C")) + ")")
                sheet.cell(r, j, formula).number_format = "0.000;-0.000;"
            sheet.cell(r, sum_col, f"=SUM(B{r}:{get_column_letter(sum_col - 1)}{r})").number_format = "0.000"
        sheet.cell(sum_row, 1, "Summa")
        for j in range(2, sum_col + 1):
            letter = get_column_letter(j)
            sheet.cell(sum_row, j, f"=SUM({letter}{first}:{letter}{sum_row - 1})").number_format = "0.000"

        # The same matrix as percent of each diameter class, as on the HTML page.
        top = sum_row + 3
        sheet.cell(top - 1, 1, "Andel av diameterklassens volym").font = bold
        sheet.cell(top, 1, "Längd, dm \\ diameter, cm")
        for j in range(2, sum_col):
            sheet.cell(top, j, f"={get_column_letter(j)}{header}")
        for i in range(n_rows):
            sheet.cell(top + 1 + i, 1, f"=A{first + i}")
            for j in range(2, sum_col):
                letter = get_column_letter(j)
                sheet.cell(top + 1 + i, j, f"=IF({letter}${sum_row}=0,\"\",{letter}{first + i}/{letter}${sum_row})"
                           ).number_format = "0.0%;-0.0%;"
        for r in (header, top):
            for cell in sheet[r]:
                cell.font, cell.fill = bold, grey
                cell.alignment = Alignment(horizontal="center")
        for cell in sheet[sum_row]:
            cell.font, cell.fill = bold, grey
        for r in range(first, sum_row):
            sheet.cell(r, sum_col).font = bold
            sheet.cell(r, 1).font = bold
        sheet.column_dimensions["A"].width = 26
        for j in range(2, sum_col + 1):
            sheet.column_dimensions[get_column_letter(j)].width = 9
        _wrap_across(sheet, 2, sum_col, 26 + 9 * (sum_col - 1))
        sheet.freeze_panes = sheet.cell(first, 2)

    rows_sheet = _table_sheet(book, "Bilagans rader", rows, {VOL: "0.000"})
    rows_sheet.cell(1, 10, "Från fördelningen").font = bold
    rows_sheet.cell(1, 11, "Skillnad").font = bold
    for r in range(2, len(rows) + 2):
        alloc = [span("Fördelning", letter, len(allocation)) for letter in "GBDE"]
        rows_sheet.cell(r, 10, f"=IF(A{r}=\"LEVERANS\",SUMIFS({alloc[0]},{alloc[1]},B{r},{alloc[2]},C{r},{alloc[3]},D{r}),\"\")"
                        ).number_format = "0.000000"
        rows_sheet.cell(r, 11, f"=IF(A{r}=\"LEVERANS\",E{r}-J{r},\"\")").number_format = "0.000000"
    for i in range(6, 10):
        for cell in rows_sheet[get_column_letter(i)][1:]:
            cell.number_format = "0%"
    rows_sheet.auto_filter.ref = f"A1:K{len(rows) + 1}"
    _table_sheet(book, "Fördelning", allocation[[AO, SORT, DEST, DIA, LEN, "sakerhetsklass", VOL]], {VOL: "0.000000"})
    _table_sheet(book, "Krediteringar", changes[["radtyp", AO, SORT, DIA, LEN, VOL]], {VOL: "0.000000"})
    delivery_columns = [c for c in (AO, SORT, "producerat_handelssortiment", VOL, "brutto_m3fub", "leveransnummer",
                                    "leveransdatum", "matdatum", "matmetod") if c in deliveries.columns]
    _table_sheet(book, "Mätning", deliveries[delivery_columns], {VOL: "0.000", "brutto_m3fub": "0.000"})
    _table_sheet(book, "Avstämning", balance)
    if harvest is not None:
        _table_sheet(book, "Skördardata", harvest[harvest[AO].isin(orders)].rename(
            columns={PRODUCED: SORT, PRODUCED_FOR: DEST}), {VOL: "0.000"})
    if extra is not None:
        extra(book, len(allocation))
    for sheet in book.worksheets:
        _printable(sheet, f"{step.period}, {destination}")
    # With each formula's value beside it, so that a preview shows the numbers before Excel computes them.
    save_with_values(book, path)
