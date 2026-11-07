"""The appendix to each mill's invoice, in three forms built from the same grid of litres.

    <mill>.md     the matrices as text, volume or percent per cell
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
        return text  # A class without a number, such as OKÄND.


def _shown(litres: pd.DataFrame) -> pd.DataFrame:
    """The grid with length in dm and diameter in cm, as the appendix shows them."""
    return litres.rename(index=lambda v: _label(v, 10), columns=lambda v: _label(v, 1))


def _blocks(output: MonthOutput, destination: str):
    """Per assortment: this month's delivered lines and the changes to earlier months."""
    invoice = output.invoice[output.invoice[DEST] == destination]
    for sortiment, block in invoice.groupby(SORT, sort=True):
        yield sortiment, block[block["radtyp"] == "LEVERANS"], block[block["radtyp"] != "LEVERANS"]


ALL = "Alla handelssortiment"


def _together(output: MonthOutput, destination: str) -> tuple[str, pd.DataFrame, pd.DataFrame]:
    """The appendix's one matrix: this month's delivered lines and the changes to earlier months, all assortments
    together. Named after the assortment when there is only one."""
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
    return f"Stockarnas längd per dm och diameter per cm, {name[0].lower() + name[1:] if name == ALL else name}"


def _tier_sources(output: MonthOutput, destination: str, sortiment: str) -> str:
    m = output.matrices.get((destination, sortiment))
    if m is None or m.delivered.sum() <= 0:
        return ""
    delivered = m.delivered.sum()
    shares = [f"{t} {m.by_tier[t].sum() / delivered:.0%}" for t in CERTAINTY_TIERS if m.by_tier[t].sum() > 0]
    return f"Fördelningens källa: {', '.join(shares)}."


_CLASSES_NOTE = ("Raderna är stockarnas längd i dm och kolumnerna deras diameter i cm, båda med klassens nedre gräns.")
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
    """The appendix as text: one matrix for all assortments together, and the changes to earlier months."""
    shares = layout.style == "andel"
    shown_as = (
        "Cellerna är procent av diameterklassens levererade volym, så att varje kolumn summerar till 100. Raden och "
        "kolumnen Summa är m3fub under bark, liksom ändringar av tidigare månader."
        if shares
        else "Volymerna är m3fub under bark."
    )
    intro = (f"Levererad volym, alla handelssortiment tillsammans. {_CLASSES_NOTE} Volymen är inmätningens; fördelningen på klasser "
             f"är skattad ur skördarens produktionsrapportering. {shown_as}" + (f" {_BANDS_NOTE}" if layout.banded else ""))
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
        lines += ["### Ändringar av tidigare månaders leveranser", "",
                  f"Krediterade lass och rättade fördelningar, netto {_litres(earlier).sum() / 1000:.3f} m3fub.", "",
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


def _font(columns: int) -> str:
    # Wide matrices get smaller type so that they fit across an A4 landscape page.
    return "9pt" if columns <= 16 else "8pt" if columns <= 24 else "7pt" if columns <= 32 else "6pt" if columns <= 42 else "5pt"


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
    head = "".join(f"<th>{escape(str(c))}</th>" for c in litres.columns)
    rows = []
    for length in litres.index:
        cells = []
        for dia in litres.columns:
            litre, share = litres.at[length, dia], percent.at[length, dia]
            if not litre:
                cells.append('<td class="none">–</td>')
            elif shares:
                # A light shade by share, so that the shape of each column shows at a glance.
                alpha = 0.06 + 0.5 * share / top if top > 0 and share > 0 else 0
                # Volume too small to show as a whole percent is still volume, not zero.
                shown = _sv(share, 0) if share >= 0.5 or share < 0 else "&lt;1"
                cells.append(f'<td style="background:rgba(37,99,235,{alpha:.2f})">{shown}</td>')
            else:
                cells.append(f"<td>{_volume(litre / 1000, 3)}</td>")
        rows.append(f"<tr><th>{escape(str(length))}</th>{''.join(cells)}"
                    f"<td class=\"sum\">{_volume(litres.loc[length].sum() / 1000, decimals)}</td></tr>")
    foot = "".join(f"<td>{_volume(v / (1_000_000 if thousands else 1000), decimals)}</td>" for v in columns)
    return (
        # Two header rows name the axes, instead of a corner cell that reads as a riddle.
        f'<table style="font-size:{_font(len(litres.columns))}"><thead>'
        f'<tr><th class="corner" rowspan="2">Längd, dm</th><th class="axis" colspan="{len(litres.columns)}">Diameter, cm</th>'
        f'<th class="sum" rowspan="2">Summa, m3fub</th></tr><tr>{head}</tr></thead><tbody>{"".join(rows)}'
        # The sum row belongs to the body: a footer would be repeated on every page the table spans.
        f'<tr class="total"><th>Summa, {"tusen " if thousands else ""}m3fub</th>{foot}'
        f'<td class="sum">{_volume(columns.sum() / 1000, decimals)}</td></tr></tbody></table>'
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
    """The changes to earlier months' deliveries, all assortments together, in m3fub, as the appendix shows them."""
    _, _, earlier = _together(output, destination)
    if not len(earlier):
        return ""
    return ('<div class="changes"><h3>Ändringar av tidigare månaders leveranser, m3fub</h3>'
            f"{_matrix_html(grid(earlier, layout), shares=False)}</div>")


def appendix_lead(output: MonthOutput, destination: str) -> str:
    """The delivered volume, and per assortment when there are several, as the appendix opens with it."""
    _, delivered, _ = _together(output, destination)
    per_sortiment = _per_sortiment(output, destination)
    held = (f" i {len(per_sortiment)} handelssortiment: "
            + ", ".join(f"{sortiment} {_sv(volume, 3)}" for sortiment, volume in per_sortiment)
            + " m3fub" if len(per_sortiment) > 1 else "")
    return f"Levererad volym {_sv(_litres(delivered).sum() / 1000, 3)} m3fub under bark{held}."


MATRIX_NOTE = ("Cellerna är procent av diameterklassens levererade volym, så att varje kolumn summerar till 100; – är "
               f"ingen volym och <1 under en halv procent. {_CLASSES_NOTE}")


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
        ("Alla handelssortiment, när det finns flera, och sedan ett handelssortiment per flik: matrisen i m3fub med längden i dm som rader och diametern i cm som kolumner, räknad med SUMIFS ur fliken Bilagans rader, och under den samma matris som procent av kolumnen.", None),
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
                                                    "Inmätning", "Avstämning", "Skördardata", ALL):
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

    # The matrix, as formulas over the appendix rows: all assortments together, as on the page.
    name, delivered, _ = _together(output, destination)
    sortiment = None if name == ALL else name
    for delivered in ([delivered] if len(delivered) else []):
        sheet = book.create_sheet(ALL if sortiment is None else sheets[sortiment])
        litres = grid(delivered, layout)
        n_rows, n_cols = len(litres.index), len(litres.columns)
        sheet["A1"], sheet["A1"].font = f"{_title(name)}, levererat {step.period}, m3fub", Font(bold=True, size=12)
        sheet["A2"] = ("Räknat med SUMIFS ur fliken Bilagans rader, där längden står i cm. Rubrikerna visar längden i dm "
                       "och diametern i cm, med klassens nedre gräns.")
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
