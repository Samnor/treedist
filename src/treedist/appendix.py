"""The appendix to each mill's invoice, in three forms built from the same grid of litres.

    <mill>.md     the matrices as text, volume or percent per cell
    <mill>.html   a page with only the matrices, percent of the length class per cell, made to print as PDF
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

from . import __version__
from .core.allocate import CERTAINTY_TIERS, TIER_NAMES
from .core.pipeline import MonthOutput
from .schema import AO, DEST, DIA, LEN, SORT, VOL, sorted_groups

APPENDIX_STYLES = ("volym", "andel")


@dataclass(frozen=True)
class AppendixLayout:
    """How an appendix shows the month; nothing here changes a volume.

    `style` sets the cells of the Markdown appendix; the HTML page always shows percent. `diameter` and
    `length` are band floors in cm. Empty keeps the classes as delivered; otherwise each class goes to the
    band it falls in, so 1 cm classes can be shown as 10 cm or product bands.
    """

    style: str = "volym"
    diameter: tuple[int, ...] = ()
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
        return value  # A class without a number, such as OKÄND, stays its own row or column.
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
    """Litres with diameter classes (or bands) as rows and length classes as columns, empty ones dropped."""
    if layout.diameter:
        lines = lines.assign(**{DIA: lines[DIA].map(lambda v: _band(v, layout.diameter))})
    if layout.length:
        lines = lines.assign(**{LEN: lines[LEN].map(lambda v: _band(v, layout.length))})
    litres = lines.assign(_liter=_litres(lines)).pivot_table(
        index=DIA, columns=LEN, values="_liter", aggfunc="sum", fill_value=0
    )
    litres = litres.reindex(index=_ordered(litres.index, layout.diameter),
                            columns=_ordered(litres.columns, layout.length), fill_value=0)
    # Classes with no volume in any cell say nothing; dropping them keeps every sum.
    return litres.loc[(litres != 0).any(axis=1), (litres != 0).any(axis=0)]


def _blocks(output: MonthOutput, destination: str):
    """Per assortment: this month's delivered lines and the changes to earlier months."""
    invoice = output.invoice[output.invoice[DEST] == destination]
    for sortiment, block in invoice.groupby(SORT, sort=True):
        yield sortiment, block[block["radtyp"] == "LEVERANS"], block[block["radtyp"] != "LEVERANS"]


def _tier_sources(output: MonthOutput, destination: str, sortiment: str) -> str:
    m = output.matrices.get((destination, sortiment))
    if m is None or m.delivered.sum() <= 0:
        return ""
    delivered = m.delivered.sum()
    shares = [f"{t} {m.by_tier[t].sum() / delivered:.0%}" for t in CERTAINTY_TIERS if m.by_tier[t].sum() > 0]
    return f"Fördelningens källa: {', '.join(shares)}."


_BANDS_NOTE = "Grupperade klasser är halvöppna: a–b betyder från a till under b cm, a+ betyder a cm och mer och <a under a cm."


# Markdown

def _matrix_markdown(litres: pd.DataFrame, shares: bool) -> str:
    columns = litres.sum(axis=0)
    if shares:
        shown = litres.apply(lambda col: col.map(lambda v: f"{100 * v / col.sum():.1f}" if v and col.sum() > 0 else ""))
    else:
        shown = litres.map(lambda v: f"{v / 1000:.3f}" if v else "")
    shown["Summa"] = (litres.sum(axis=1) / 1000).map(lambda v: f"{v:.3f}")
    shown.loc["Summa"] = [*(columns / 1000).map(lambda v: f"{v:.3f}"), f"{columns.sum() / 1000:.3f}"]
    return markdown_table(shown.rename_axis("diameter, cm").reset_index())


def appendix_markdown(output: MonthOutput, destination: str, layout: AppendixLayout = AppendixLayout()) -> str:
    """The appendix as text: one matrix per assortment for the month."""
    shares = layout.style == "andel"
    shown_as = (
        "Cellerna är procent av längdklassens levererade volym, så att varje kolumn summerar till 100. Raden och "
        "kolumnen Summa är m3fub under bark, liksom ändringar av tidigare månader."
        if shares
        else "Volymerna är m3fub under bark."
    )
    intro = ("Levererad volym per handelssortiment. Raderna är diameterklasser och kolumnerna längdklasser, båda med "
             "klassens nedre gräns i cm. Volymen är inmätningens; fördelningen på klasser är skattad ur skördarens "
             f"produktionsrapportering. {shown_as}" + (f" {_BANDS_NOTE}" if layout.banded else ""))
    lines = [f"# Bilaga till faktura {output.step.period}, {destination}", "", intro, ""]
    for sortiment, delivered, earlier in _blocks(output, destination):
        lines += [f"## {sortiment}", ""]
        if len(delivered):
            total = _litres(delivered).sum() / 1000
            sources = _tier_sources(output, destination, sortiment)
            lines += [f"Levererat {total:.3f} m3fub. {sources}".rstrip(), "",
                      _matrix_markdown(grid(delivered, layout), shares), ""]
        if len(earlier):
            lines += ["### Ändringar av tidigare månaders leveranser", "",
                      f"Krediterade lass och rättade fördelningar, netto {_litres(earlier).sum() / 1000:.3f} m3fub.", "",
                      _matrix_markdown(grid(earlier, layout), False), ""]
    lines += ["Fördelningens källa:", "", *[f"- {t}: {name}" for t, name in TIER_NAMES.items()], ""]
    return "\n".join(lines)


def appendix_rows(output: MonthOutput, destination: str) -> pd.DataFrame:
    invoice = output.invoice[output.invoice[DEST] == destination]
    return invoice[["radtyp", SORT, DIA, LEN, VOL, *[f"andel_{t}" for t in CERTAINTY_TIERS]]]


# HTML, for print

_CSS = """
@page { size: A4 landscape; margin: 13mm 12mm 12mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: #1c2430; font-size: 9pt; }
header { border-bottom: 1.5pt solid #1c2430; padding-bottom: 6pt; margin-bottom: 10pt; }
.eyebrow { font-size: 8.5pt; letter-spacing: .04em; text-transform: uppercase; color: #5b6573; }
h1 { font-size: 18pt; margin: 2pt 0 4pt; font-weight: 650; }
.lead { margin: 0; color: #3a4452; max-width: 210mm; line-height: 1.4; }
section { break-before: page; }
section:first-of-type { break-before: auto; }
h2 { font-size: 13pt; margin: 0 0 5pt; font-weight: 650; }
.total { font-size: 10pt; font-weight: 400; color: #5b6573; margin-left: 10pt; font-variant-numeric: tabular-nums; }
h3 { font-size: 10pt; margin: 12pt 0 4pt; font-weight: 600; color: #3a4452; }
table { border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { padding: 2pt 4pt; text-align: right; white-space: nowrap; border: 0.4pt solid #d5dae1; }
thead th { background: #eef1f5; font-weight: 600; border-bottom: 0.8pt solid #8c96a3; vertical-align: bottom; }
th.corner { text-align: left; }
th.axis { text-align: center; color: #3a4452; border-bottom: 0.4pt solid #d5dae1; }
tbody th { text-align: left; font-weight: 600; background: #f6f8fa; }
td.sum, th.sum { background: #eef1f5; font-weight: 600; border-left: 0.8pt solid #8c96a3; }
tr.total th, tr.total td { background: #eef1f5; font-weight: 600; color: #1c2430; border-top: 0.8pt solid #8c96a3; }
.changes { break-inside: avoid; }
tr { break-inside: avoid; }
.note { margin-top: 8pt; font-size: 7.5pt; color: #5b6573; line-height: 1.4; max-width: 230mm; }
"""


def _running(destination: str, period: str) -> str:
    """Mill, period and page number in the page margins, so that a loose page still says what it belongs to."""
    words = (destination + " · Bilaga till faktura " + period).replace("\\", "\\\\").replace('"', '\\"')
    box = "font-family: \"Segoe UI\", \"Helvetica Neue\", Arial, sans-serif; font-size: 7.5pt; color: #5b6573;"
    return (f'@page {{ @top-left {{ content: "{words}"; {box} }} '
            f'@bottom-right {{ content: "Sida " counter(page) " av " counter(pages); {box} }} }}'
            "@page :first { @top-left { content: none; } }")


def _sv(value: float, decimals: int) -> str:
    """Swedish number: decimal comma, a no-break space between thousands (a narrow one vanishes in small type)."""
    return f"{value:,.{decimals}f}".replace(",", "\u00a0").replace(".", ",")


def _font(columns: int) -> str:
    # Wide matrices get smaller type so that they fit across an A4 landscape page.
    return "9pt" if columns <= 12 else "8pt" if columns <= 18 else "7pt" if columns <= 26 else "6pt" if columns <= 36 else "5pt"


def _matrix_html(litres: pd.DataFrame, shares: bool) -> str:
    columns = litres.sum(axis=0)
    percent = litres.div(columns.where(columns > 0), axis=1) * 100
    top = float(np.nanmax(percent.to_numpy())) if shares and percent.size else 0.0
    head = "".join(f"<th>{escape(str(c))}</th>" for c in litres.columns)
    rows = []
    for dia in litres.index:
        cells = []
        for length in litres.columns:
            litre, share = litres.at[dia, length], percent.at[dia, length]
            if not litre:
                cells.append("<td></td>")
            elif shares:
                # A light shade by share, so that the shape of each column shows at a glance.
                alpha = 0.06 + 0.5 * share / top if top > 0 and share > 0 else 0
                # Volume too small to show at one decimal is still volume, not zero.
                shown = _sv(share, 1) if share >= 0.05 else "&lt;0,1"
                cells.append(f'<td style="background:rgba(37,99,235,{alpha:.2f})">{shown}</td>')
            else:
                cells.append(f"<td>{_sv(litre / 1000, 3)}</td>")
        rows.append(f"<tr><th>{escape(str(dia))}</th>{''.join(cells)}<td class=\"sum\">{_sv(litres.loc[dia].sum() / 1000, 3)}</td></tr>")
    foot = "".join(f"<td>{_sv(v / 1000, 3)}</td>" for v in columns)
    return (
        # Two header rows name the axes, instead of a corner cell that reads as a riddle.
        f'<table style="font-size:{_font(len(litres.columns))}"><thead>'
        f'<tr><th class="corner" rowspan="2">Diameter, cm</th><th class="axis" colspan="{len(litres.columns)}">Längd, cm</th>'
        f'<th class="sum" rowspan="2">Summa, m3fub</th></tr><tr>{head}</tr></thead><tbody>{"".join(rows)}'
        # The sum row belongs to the body: a footer would be repeated on every page the table spans.
        f'<tr class="total"><th>Summa, m3fub</th>{foot}<td class="sum">{_sv(columns.sum() / 1000, 3)}</td></tr></tbody></table>'
    )


def appendix_html(output: MonthOutput, destination: str, layout: AppendixLayout = AppendixLayout()) -> str:
    """A page with only the matrices, percent of the length class per cell, for a browser to print as PDF."""
    blocks = list(_blocks(output, destination))
    total = sum(_litres(d).sum() for _, d, _ in blocks) / 1000
    sections = []
    for sortiment, delivered, earlier in blocks:
        parts = [f'<h2>{escape(sortiment)}<span class="total">{_sv(_litres(delivered).sum() / 1000, 3)} m3fub</span></h2>']
        if len(delivered):
            parts.append(_matrix_html(grid(delivered, layout), shares=True))
        if len(earlier):
            parts.append('<div class="changes"><h3>Ändringar av tidigare månaders leveranser, m3fub</h3>'
                         f'{_matrix_html(grid(earlier, layout), shares=False)}</div>')
        sections.append(f"<section>{''.join(parts)}</section>")
    note = ("Cellerna är procent av längdklassens levererade volym, så att varje kolumn summerar till 100. Summa är "
            "m3fub under bark. Klasserna anges med nedre gräns i cm. Volymen är inmätningens; fördelningen på klasser "
            "är skattad ur skördarens produktionsrapportering." + (f" {_BANDS_NOTE}" if layout.banded else ""))
    title = f"Bilaga till faktura {output.step.period}, {destination}"
    return (
        f'<!doctype html>\n<html lang="sv"><head><meta charset="utf-8"><title>{escape(title)}</title>'
        f"<style>{_CSS}{_running(destination, output.step.period)}</style></head><body>\n<header><div class=\"eyebrow\">Bilaga till faktura · {output.step.period}"
        f"</div><h1>{escape(destination)}</h1><p class=\"lead\">Levererad volym {_sv(total, 3)} m3fub under bark i "
        f"{len(blocks)} handelssortiment.</p><p class=\"note\">{escape(note)}</p></header>\n"
        + "\n".join(sections) + f"\n<!-- treedist {__version__} -->\n</body></html>\n"
    )


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
                      harvest: pd.DataFrame | None = None) -> None:
    """The rows behind a mill's appendix, and the matrices as SUMIFS formulas over them."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    step = output.step
    rows = appendix_rows(output, destination).reset_index(drop=True)
    allocation = step.allocation[step.allocation[DEST] == destination]
    changes = pd.concat([step.corrections.assign(radtyp="KORRIGERING"), step.credits.assign(radtyp="KREDITERING")])
    changes = changes[changes[DEST] == destination]
    deliveries = output.deliveries[output.deliveries[DEST] == destination]
    orders = set(deliveries[AO])
    balance = step.reconciliation[step.reconciliation[AO].isin(orders)]

    # Ranges end at the last row: faster than whole columns, in Excel and in other spreadsheets alike.
    def span(sheet: str, letter: str, length: int) -> str:
        return f"'{sheet}'!${letter}$2:${letter}${max(length, 1) + 1}"

    def rows_col(letter: str) -> str:
        return span("Bilagans rader", letter, len(rows))

    book = Workbook()
    guide = book.active
    guide.title = "Läs först"
    bold, grey = Font(bold=True), PatternFill("solid", fgColor="EEF1F5")
    lines = [
        (f"Bilaga till faktura {step.period}, {destination}", Font(bold=True, size=14)),
        ("Den här filen innehåller raderna som bilagans matriser bygger på, så att vem som helst kan kontrollera dem.", None),
        ("", None),
        ("Flikar", bold),
        ("Ett handelssortiment per flik: matrisen i m3fub, räknad med SUMIFS ur fliken Bilagans rader, och under den samma matris som procent av kolumnen.", None),
        ("Bilagans rader: volym per sortiment och klass, i hela liter, med andel per säkerhetsklass. Kolumnen Från fördelningen summerar fliken Fördelning per klass; skillnaden är avrundningen till hela liter.", None),
        ("Fördelning: månadens levererade volym per arbetsorder, klass och säkerhetsklass, före avrundning.", None),
        ("Ändringar: korrigeringar och krediteringar av tidigare månader.", None),
        ("Inmätning: lassen till mottagaren, som volymen bygger på.", None),
        ("Avstämning: lager per arbetsorder: ingående, skördat, levererat och utgående.", None),
        ("Skördardata: månadens skördarrader för arbetsordrarna, om körningen hade dem.", None),
        ("", None),
        ("Säkerhetsklasser", bold),
        *[(f"{t}: {name}", None) for t, name in TIER_NAMES.items()],
        ("", None),
        ("Kontroll: inmätt volym mot bilagan per sortiment (leverans plus kreditering), m3fub", bold),
    ]
    for text, font in lines:
        guide.append([text])
        if font:
            guide.cell(guide.max_row, 1).font = font
    guide.column_dimensions["A"].width = 30
    guide.append(["Handelssortiment", "Inmätning", "Bilagan", "Skillnad"])
    for cell in guide[guide.max_row]:
        cell.font, cell.fill = bold, grey

    sheets = {}
    for sortiment, delivered, _ in _blocks(output, destination):
        name = _SHEET.sub("_", str(sortiment))[:31]
        while name in sheets.values() or name in ("Läs först", "Bilagans rader", "Fördelning", "Ändringar",
                                                    "Inmätning", "Avstämning", "Skördardata"):
            name = name[:28] + "_" + str(len(sheets))
        sheets[sortiment] = name
        r = guide.max_row + 1
        measured = [span("Inmätning", letter, len(deliveries)) for letter in "DB"]
        guide.append([sortiment, f"=SUMIFS({measured[0]},{measured[1]},A{r})",
                      f"=SUMIFS({rows_col('E')},{rows_col('B')},A{r},{rows_col('A')},\"LEVERANS\")"
                      f"+SUMIFS({rows_col('E')},{rows_col('B')},A{r},{rows_col('A')},\"KREDITERING\")",
                      f"=B{r}-C{r}"])
        for cell in guide[r][1:]:
            cell.number_format = "0.000"
    guide.append(["Inmätningens sortiment är det inmätta, som faktureras. Skillnaden ska vara 0,000."])
    for column in "BCD":
        guide.column_dimensions[column].width = 14

    # The matrices, as formulas over the appendix rows.
    for sortiment, delivered, _ in _blocks(output, destination):
        if not len(delivered):
            continue
        sheet = book.create_sheet(sheets[sortiment])
        litres = grid(delivered, layout)
        n_rows, n_cols = len(litres.index), len(litres.columns)
        sheet["A1"], sheet["A1"].font = f"{sortiment}, levererat {step.period}, m3fub", Font(bold=True, size=12)
        sheet["A2"] = "Räknat med SUMIFS ur fliken Bilagans rader. Klasser med nedre gräns i cm."
        header, first = 4, 5
        sheet.cell(header, 1, "Diameter \\ längd, cm")
        for j, length in enumerate(litres.columns, start=2):
            sheet.cell(header, j, _cell(str(length)))
        sum_col = n_cols + 2
        sum_row = first + n_rows
        sheet.cell(header, sum_col, "Summa")
        for i, dia in enumerate(litres.index):
            r = first + i
            sheet.cell(r, 1, _cell(str(dia)))
            for j, length in enumerate(litres.columns, start=2):
                formula = (f"=SUMIFS({rows_col('E')},{rows_col('A')},\"LEVERANS\",{rows_col('B')},{_text(sortiment)}"
                           + _criteria(str(dia), layout.diameter, rows_col("C"))
                           + _criteria(str(length), layout.length, rows_col("D")) + ")")
                sheet.cell(r, j, formula).number_format = "0.000;-0.000;"
            sheet.cell(r, sum_col, f"=SUM(B{r}:{get_column_letter(sum_col - 1)}{r})").number_format = "0.000"
        sheet.cell(sum_row, 1, "Summa")
        for j in range(2, sum_col + 1):
            letter = get_column_letter(j)
            sheet.cell(sum_row, j, f"=SUM({letter}{first}:{letter}{sum_row - 1})").number_format = "0.000"

        # The same matrix as percent of each length class, as on the HTML page.
        top = sum_row + 3
        sheet.cell(top - 1, 1, "Andel av längdklassens volym").font = bold
        sheet.cell(top, 1, "Diameter \\ längd, cm")
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
        sheet.column_dimensions["A"].width = 20
        for j in range(2, sum_col + 1):
            sheet.column_dimensions[get_column_letter(j)].width = 9
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
    _table_sheet(book, "Ändringar", changes[["radtyp", AO, SORT, DIA, LEN, VOL]], {VOL: "0.000000"})
    delivery_columns = [c for c in (AO, SORT, "producerat_handelssortiment", VOL, "brutto_m3fub", "leverans_id",
                                    "leveransdatum", "matmetod") if c in deliveries.columns]
    _table_sheet(book, "Inmätning", deliveries[delivery_columns], {VOL: "0.000", "brutto_m3fub": "0.000"})
    _table_sheet(book, "Avstämning", balance)
    if harvest is not None:
        _table_sheet(book, "Skördardata", harvest[harvest[AO].isin(orders)], {VOL: "0.000"})
    book.save(path)
