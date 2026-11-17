"""The appendix as a printable page: the Builder that draws a mill's appendix (bilaga.py) as HTML.

    <out>/bilagor/<mill>.html   first the matrix of all volume delivered to the mill in the month; then a Sankey
                                diagram from its assortments to where the distribution comes from, with the table
                                of sources; then the worked example of volume beyond the stock (exempel.py), the work
                                orders behind the matrix, and every part in words

The page is plain HTML and SVG with no script or web font, so it opens and prints on a machine without internet.
"""

from __future__ import annotations

from html import escape

import pandas as pd

from . import __version__
from .appendix import AppendixLayout, changes_matrix_html, first_matrix_html, matrix_note
from .bilaga import (
    BASIS,
    NAMES,
    PAGE_GUIDE,
    STATE,
    Bilaga,
    beyond_plan,
    build,
    certainty_lead,
    differing_stems,
    drifted,
    guide,
    APART,
    coverage,
    intro,
    origin_lead,
    origin_table,
    source_name,
    measures_lead,
    orders_lead,
    overshipped,
    percent,
    share,
    sv,
    volume_text,
)
from .contract import MEASURE, STEM
from .core.allocate import CERTAINTY_TIERS
from .core.pipeline import MonthOutput
from .exempel import LEAD, LEGEND, NOTE, RULE, TITLE, steps, this_month
from .sankey import COLOURS, flow_svg, sankey_svg
from .schema import AO, SORT, VOL
from .workorders import DIFFERS, DRIFT, MEAN, PROGRESS, SO_FAR, Facts


def _table(volumes: pd.DataFrame) -> str:
    total = float(volumes.to_numpy().sum())
    mills = [m for m in volumes.index if volumes.loc[m].sum() > 0]
    head = "".join(f"<th>{escape(str(m))}</th>" for m in mills)
    rows = []
    for tier in CERTAINTY_TIERS:
        volume = float(volumes[tier].sum())
        colour = COLOURS[tier]
        cells = "".join(f"<td>{volume_text(float(volumes.at[m, tier]))}</td>" for m in mills)
        rows.append(f'<tr><th><span class="key" style="background:{colour}"></span>{NAMES[tier]}</th>'
                    f'<td class="text">{STATE[tier]}</td><td class="text">{escape(BASIS[tier])}</td>'
                    f"{cells}<td>{volume_text(volume)}</td><td>{percent(volume, total) if volume > 0 else '–'}</td></tr>")
    sums = "".join(f"<td>{sv(float(volumes.loc[m].sum()))}</td>" for m in mills)
    return (f'<table><thead><tr><th>Fördelningens källa</th><th class="text">Mätt eller uppskattad</th>'
            f'<th class="text">Bygger på</th>{head}<th>Summa, m3fub</th><th>Andel</th></tr></thead>'
            f'<tbody>{"".join(rows)}<tr class="sum"><th>Summa</th><td></td><td></td>{sums}<td>{sv(total)}</td>'
            "<td>100 %</td></tr></tbody></table>")


_CSS = """
@page { size: A4 landscape; margin: 13mm 12mm 12mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0 auto; max-width: 273mm; font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: #1c2430;
       background: #fff; font-size: 9pt; }
.eyebrow { font-size: 8.5pt; letter-spacing: .04em; text-transform: uppercase; color: #5b6573; }
h1 { font-size: 18pt; margin: 2pt 0 4pt; font-weight: 650; }
.lead { margin: 0 0 8pt; color: #3a4452; line-height: 1.4; max-width: 210mm; }
svg { width: 100%; height: auto; display: block; margin: 6pt 0 10pt; }
svg text { font-size: 12px; fill: #1c2430; paint-order: stroke; stroke: #fff; stroke-width: 3px; stroke-linejoin: round; }
svg .name { font-weight: 600; }
svg .detail { font-weight: 400; fill: #52514e; }
svg path:hover { fill-opacity: .55; }
table { border-collapse: collapse; font-variant-numeric: tabular-nums; width: 100%; break-inside: avoid; font-size: 8pt; }
th, td { padding: 2pt 5pt; text-align: right; border: 0.4pt solid #d5dae1; vertical-align: top; white-space: nowrap; }
thead th { background: #eef1f5; font-weight: 600; border-bottom: 0.8pt solid #8c96a3; }
tbody th { text-align: left; white-space: nowrap; }
.text, th:first-child { text-align: left; }
td.text { white-space: normal; }
td.text { color: #3a4452; }
tr.sum th, tr.sum td { background: #eef1f5; font-weight: 600; border-top: 0.8pt solid #8c96a3; }
.key { display: inline-block; width: 8pt; height: 8pt; border-radius: 2pt; margin-right: 4pt; vertical-align: -1pt; }
.note { margin-top: 8pt; font-size: 7.5pt; color: #5b6573; line-height: 1.4; max-width: 230mm; }
.guide { break-before: page; max-width: 210mm; }
.guide dl { margin: 0; line-height: 1.4; }
.guide dl > div { display: grid; grid-template-columns: 52mm 1fr; column-gap: 8pt; margin-bottom: 5pt; break-inside: avoid; }
.guide dt { font-weight: 600; }
.guide dd { margin: 0; color: #3a4452; }
header { margin-bottom: 8pt; }
.orders + .mill, .certainty { break-before: page; }
.orders { margin-top: 8pt; }
.mill .note { margin-top: 4pt; }
.orders h2, .certainty h2, .example h2, .guide h2 { font-size: 13pt; margin: 0 0 4pt; font-weight: 650; }
.orders h2 span { font-weight: 400; color: #52514e; font-size: 10pt; }
.orders .lead { margin-bottom: 6pt; }
.orders table { break-inside: auto; font-size: 7.5pt; }
.orders th, .orders td { padding: 2pt 4pt; }
.orders thead th.group { text-align: center; border-bottom: 0.4pt solid #d5dae1; }
.orders thead tr:last-child th { white-space: normal; }
.measures { margin-top: 6pt; }
.measures h3, .measures .lead { break-after: avoid; }
.measures tr { break-inside: avoid; }
.measures h3, .example h3 { font-size: 9.5pt; margin: 0 0 3pt; font-weight: 650; }
.measures table { width: auto; }
.measures .lead { margin-bottom: 4pt; }
.example { break-before: page; }
.example .lead { max-width: none; margin-bottom: 6pt; }
.example .rule { margin: 0 0 8pt; padding: 5pt 8pt; border-left: 3pt solid #eb6834; background: #fdf1ea; line-height: 1.4; }
.example .rule strong { font-weight: 650; }
.example .legend { margin: 0 0 6pt; color: #3a4452; }
.example .legend span.item { margin-right: 14pt; white-space: nowrap; }
.example .steps { display: grid; grid-template-columns: repeat(3, 1fr); column-gap: 14pt; row-gap: 10pt; margin-bottom: 10pt; }
.example .step { break-inside: avoid; }
.example .step svg { margin: 0 0 4pt; max-width: 62mm; }
.example .step p { margin: 0; color: #3a4452; line-height: 1.4; }
.example .month { break-inside: avoid; border-top: 0.4pt solid #d5dae1; padding-top: 8pt; }
.example .month table { width: auto; margin-top: 4pt; }
td.nowrap { white-space: nowrap; }
td.flag { font-weight: 650; background: #fdf0e1; }
td.bar { background: linear-gradient(to right, rgba(42, 120, 214, .22) var(--w), transparent var(--w)); }
h2.millname { font-size: 15pt; margin: 4pt 0 2pt; font-weight: 650; border-bottom: 1.2pt solid #1c2430; padding-bottom: 2pt; }
h2.millname span { font-size: 10pt; font-weight: 400; color: #52514e; }
.matrix h2 { font-size: 12pt; margin: 2pt 0 5pt; font-weight: 650; }
.matrix h2 .total { font-size: 10pt; font-weight: 400; color: #5b6573; margin-left: 10pt; font-variant-numeric: tabular-nums; }
.matrix th, .matrix td { padding: 2pt 4pt; vertical-align: middle; }
.matrix thead th { vertical-align: bottom; }
.matrix thead tr + tr th { text-align: right; }
.matrix table.dense th, .matrix table.dense td { padding: 2pt 1.5pt; }
.matrix table.dense th.sum, .matrix table.dense th.corner, .matrix table.dense tr.total th { white-space: normal; }
.matrix th.corner { text-align: left; }
.matrix th.axis { text-align: center; color: #3a4452; border-bottom: 0.4pt solid #d5dae1; }
.matrix tbody th { font-weight: 600; background: #f6f8fa; }
.matrix td.sum, .matrix th.sum { background: #eef1f5; font-weight: 600; border-left: 0.8pt solid #8c96a3; }
.matrix tr.total th, .matrix tr.total td { background: #eef1f5; font-weight: 600; border-top: 0.8pt solid #8c96a3; }
.matrix tr { break-inside: avoid; }
.matrix h3 { font-size: 10pt; margin: 12pt 0 4pt; font-weight: 600; color: #3a4452; }
.changes { break-inside: avoid; }
.example + .orders { break-before: page; }
@media screen { .orders + .mill, .certainty, .example, .example + .orders, .guide { margin-top: 28pt; border-top: 1pt solid #d5dae1; padding-top: 14pt; } }
@media screen and (max-width: 720px) { .example .steps { grid-template-columns: repeat(2, 1fr); } }
"""


def _tiers(row: pd.Series) -> str:
    """The classes a contract object's volume was classed by, largest first, as shares of it."""
    shares = [(t, float(row[t]) / float(row[VOL])) for t in CERTAINTY_TIERS if row[t] > 0.0005]
    if len(shares) == 1:
        return NAMES[shares[0][0]]
    return "<br>".join(f"{NAMES[t]} {'>99 %' if share > 0.995 else percent(share, 1)}"
                       for t, share in sorted(shares, key=lambda s: -s[1]))


_MONTHS = ("jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec")


def _day(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{int(day)} {_MONTHS[int(month) - 1]}"


def _felled(row: pd.Series) -> str:
    first, last = row[DRIFT[0]], row[DRIFT[1]]
    if not isinstance(first, str):
        return "–"
    if first == last:
        return _day(first)
    if first[:7] == last[:7]:
        return f"{int(first[8:])}–{_day(last)}"
    return f"{_day(first)}–{_day(last)}"


def _diameters(row: pd.Series) -> str:
    """The mean diameter and length of the first and the second half of the harvest, one line each."""
    lines = []
    early, late = row[DRIFT[2]], row[DRIFT[3]]
    if not (pd.isna(early) or pd.isna(late)):
        lines.append(f"{sv(early)} → {sv(late)} cm")
    early, late = row[DRIFT[4]], row[DRIFT[5]]
    if not (pd.isna(early) or pd.isna(late)):
        lines.append(f"{sv(early / 10)} → {sv(late / 10)} dm")
    return "<br>".join(lines) or "–"


def _so_far(row: pd.Series, planned: pd.Series) -> str:
    whole = float(planned.get(row[AO], float("nan")))
    if pd.isna(whole) or whole <= 0 or pd.isna(row[SO_FAR]):
        return "–"
    return f"{percent(float(row[SO_FAR]), whole)} av {sv(whole, 0)}"


def _flagged(text: str, flag: bool) -> str:
    return f'<td class="flag">{text}</td>' if flag else f"<td>{text}</td>"


def _cm(value: float) -> str:
    return "–" if pd.isna(value) else sv(value)


def _orders(b: Bilaga) -> str:
    """The contract objects behind one mill's matrix: who they are, how much each brought and how far along each one is."""
    rows, planned = b.rows, b.planned
    total = float(rows[VOL].sum())
    with_plan = bool(len(planned)) and bool(rows[AO].isin(set(planned.index)).any())
    body = "".join(
        f"<tr><th>{escape(str(r[AO]))}</th><td class=\"text\">{escape(str(r[SORT]))}</td><td>{sv(r[VOL])}</td>"
        f"<td class=\"bar\" style=\"--w:{100 * r['andel_av_sagverket']:.1f}%\">{percent(r['andel_av_sagverket'], 1)}</td>"
        f"<td>{_cm(r[MEAN])}</td><td>{'–' if pd.isna(r[DIFFERS]) else percent(r[DIFFERS], 1)}</td>"
        f"<td class=\"text nowrap\">{_tiers(r)}</td>"
        f"<td>{volume_text(r[PROGRESS[0]])}</td>{_flagged(share(r[PROGRESS[1]], r[PROGRESS[0]]), overshipped(r))}"
        f"<td>{volume_text(r[PROGRESS[2]])}</td>" + (_flagged(_so_far(r, planned), beyond_plan(r, planned)).replace("<td", "<td style=\"white-space:nowrap\"", 1) if with_plan else "")
        + f"<td>{_felled(r)}</td>{_flagged(_diameters(r), drifted(r))}</tr>"
        for _, r in rows.iterrows())
    lead = orders_lead(rows, b.mean, planned)
    return (f'<section class="orders"><h2>Avtalsobjekten bakom matrisen <span>· {escape(str(b.mill))} · '
            f'{sv(total)} m3fub</span></h2><p class="lead">{escape(lead)}</p><table><thead>'
            f"<tr><th rowspan=\"2\">Avtalsobjekt</th><th class=\"text\" rowspan=\"2\">Sortiment</th>"
            f"<th colspan=\"5\" class=\"group\">Till sågverket i månaden</th>"
            f"<th colspan=\"{6 if with_plan else 5}\" class=\"group\">Hela avtalsobjektet</th></tr>"
            f"<tr><th>m3fub</th><th>Andel av matrisen</th><th>Medeldiameter, cm</th><th>Annan klass än hela skörden</th>"
            f"<th class=\"text\">Fördelningens källa</th><th>Skördat hittills, m3fub</th>"
            f"<th>Levererat i månaden, andel av skördat</th><th>Kvar i lager, m3fub</th>"
            + ("<th>Levererat hittills, andel av planerad volym i m3fub</th>" if with_plan else "")
            + "<th>Avverkad</th><th>Medeldiameter och medellängd, första → andra halvan av skörden</th></tr></thead>"
            f"<tbody>{body}</tbody></table>"
            f"{_measures(rows, b.measures)}</section>")


def _source_colour(tier: str) -> str:
    return COLOURS["outside"] if tier == APART else COLOURS[tier]


def _origin_section(b: Bilaga) -> str:
    """Where the mill's measured wood comes from, per anskaffningsform, and what became of it: the diagram, and its
    numbers as a table."""
    table = origin_table(b.origins)
    total = float(table.to_numpy().sum())
    left = [(o, str(o), COLOURS["mill"]) for o in table.index]
    right = [(t, source_name(t), _source_colour(t)) for t in table.columns]
    links = {(o, t): (float(table.at[o, t]), _source_colour(t)) for o in table.index for t in table.columns}
    head = "".join(f'<th><span class="key" style="background:{colour}"></span>{escape(name)}</th>'
                   for _, name, colour in right)
    body = "".join(
        f"<tr><th>{escape(str(o))}</th>" + "".join(f"<td>{volume_text(float(v))}</td>" for v in table.loc[o])
        + f"<td>{sv(float(table.loc[o].sum()))}</td><td>{percent(float(table.loc[o].sum()), total)}</td></tr>"
        for o in table.index)
    sums = "".join(f"<td>{sv(float(table[t].sum()))}</td>" for t in table.columns)
    return (f'<section class="certainty origin"><h2>Varifrån virket kommer</h2>'
            f'<p class="lead">{escape(origin_lead(b.origins))}</p>\n'
            f'{flow_svg([left, right], [links], "Varifrån virket kommer och vad matrisen gäller")}\n'
            f"<table><thead><tr><th>Anskaffningsform</th>{head}<th>Summa, m3fub</th><th>Andel</th></tr></thead>"
            f'<tbody>{body}<tr class="sum"><th>Summa</th>{sums}<td>{sv(total)}</td><td>100 %</td></tr></tbody></table>'
            '<p class="note">Volymen är den inmätta, i m3fub. Anskaffningsformen är avtalsobjektets, enligt underlaget.'
            "</p></section>")


def _guide(per_day: bool = False, coverage: str = "", origins: bool = False) -> str:
    items = "".join(f"<div><dt>{escape(term)}</dt><dd>{escape(text)}</dd></div>"
                    for term, text in guide(PAGE_GUIDE, per_day, coverage, origins))
    return f'<section class="guide"><h2>Så läser du bilagan</h2><dl>{items}</dl></section>'


def _example(b: Bilaga) -> str:
    """The page on volume beyond the stock: the worked example in three steps, then the mill's own month."""
    legend = "".join(f'<span class="item"><span class="key" style="background:{colour}"></span>{escape(name)}</span>'
                     for colour, name in LEGEND)
    drawn = "".join(f'<div class="step"><h3>{escape(s.title)}</h3>{s.figure}<p>{escape(s.text)}</p></div>'
                    for s in steps())
    lead, rows = this_month(b)
    table = ""
    if rows:
        # The second column is the assortment, text; the rest are numbers.
        head = "".join(f'<th class="text">{escape(name)}</th>' if i == 1 else f"<th>{escape(name)}</th>"
                       for i, name in enumerate(rows[0]))
        body = "".join("<tr>" + "".join(
            f"<th>{escape(v)}</th>" if i == 0 else f'<td class="text">{escape(v)}</td>' if i == 1
            else f"<td>{escape(v)}</td>" for i, v in enumerate(row.values())) + "</tr>" for row in rows)
        table = f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    return (f'<section class="example"><h2>{escape(TITLE)}</h2><p class="lead">{escape(LEAD)}</p>'
            f'<p class="rule"><strong>{escape(RULE)}</strong> {escape(NOTE)}</p>'
            f'<p class="legend">{legend}</p><div class="steps">{drawn}</div>'
            f'<div class="month"><h3>Månadens volym utöver lagret</h3><p class="lead">{escape(lead)}</p>{table}</div></section>')


def _measures(rows: pd.DataFrame, held: pd.DataFrame) -> str:
    """The measures of the contract objects behind the matrix, with mean stem volume, where the source has them."""
    if not len(held):
        return ""
    body = []
    order = list(rows.groupby(AO)[VOL].sum().sort_values(ascending=False).index)
    differing = differing_stems(held)
    for ao in [a for a in order if a in set(held[AO])]:
        block = held[held[AO] == ao]
        differs = str(ao) in differing
        for i, (_, m) in enumerate(block.iterrows()):
            head = f'<th rowspan="{len(block)}">{escape(str(ao))}</th>' if i == 0 else ""
            stem = "–" if pd.isna(m[STEM]) else sv(float(m[STEM]), 2)
            body.append(f'<tr>{head}<td class="text">{escape(str(m[MEASURE]))}</td>{_flagged(stem, differs)}'
                        f'<td>{volume_text(float(m[VOL])) if not pd.isna(m[VOL]) else "–"}</td></tr>')
    lead = measures_lead(held, order)
    return (f'<div class="measures"><h3>Avverkningsformer och medelstam</h3><p class="lead">{escape(lead)}</p><table><thead>'
            '<tr><th>Avtalsobjekt</th><th class="text">Avverkningsform</th><th>Medelstam, m3fub</th><th>Planerad volym, m3fub</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def render(b: Bilaga) -> str:
    """The appendix to one mill's invoice for the month: first the matrix of all volume delivered there, then how its
    distribution on classes was found, an example of volume beyond the stock, the contract objects behind it, and every
    part in words."""
    note = "Volymen är den inmätta, i m3fub. Lass från tidigare månader som krediterats denna månad ingår inte."
    matrix = first_matrix_html(b.output, b.mill, b.layout)
    certainty = (f'<section class="certainty"><h2>Hur matrisen togs fram</h2>'
                 f'<p class="lead">{escape(certainty_lead(b.volumes, b.mill))}</p>\n'
                 f"{sankey_svg(b.volumes)}\n{_table(b.volumes)}"
                 f'<p class="note">{escape(note)}</p></section>')
    if len(b.origins):
        certainty = _origin_section(b) + "\n" + certainty
    orders = _orders(b) if len(b.rows) else ""
    example = _example(b) if b.total > 0.0005 else ""
    title = f"Bilaga till faktura {b.period}, {b.mill}"
    return (
        f'<!doctype html>\n<html lang="sv"><head><meta charset="utf-8"><title>{escape(title)}</title>'
        f"<style>{_CSS}{_running_mill(b.mill, b.period)}</style></head><body>\n<header><div class=\"eyebrow\">Bilaga till "
        f'faktura · {b.period}</div><h1>{escape(str(b.mill))}</h1><p class="lead">{escape(intro(b))}</p></header>\n'
        f'<section class="mill"><div class="matrix">{matrix}{changes_matrix_html(b.output, b.mill, b.layout)}</div>'
        f'<p class="note">{escape(matrix_note(b.output, b.mill, b.layout))}</p></section>\n'
        f"{certainty}\n{example}\n{orders}\n{_guide(b.output.step.draw_per_day, coverage(b), bool(len(b.origins)))}\n"
        f"<!-- treedist {__version__} -->\n</body></html>\n"
    )


def mill_appendix_html(output: MonthOutput, mill: str, layout: AppendixLayout = AppendixLayout(),
                       facts: Facts | None = None) -> str:
    """The appendix as a page, built from the month's output."""
    return render(build(output, mill, layout, facts))


def _running_mill(mill: str, period: str) -> str:
    """Mill, period and page number in the margins, so that a loose page still says what it belongs to."""
    words = f"{mill} · Bilaga till faktura {period}".replace("\\", "\\\\").replace('"', '\\"')
    box = "font-family: \"Segoe UI\", \"Helvetica Neue\", Arial, sans-serif; font-size: 7.5pt; color: #5b6573;"
    return (f'@page {{ @top-left {{ content: "{words}"; {box} }} '
            f'@bottom-right {{ content: "Sida " counter(page) " av " counter(pages); {box} }} }}'
            "@page :first { @top-left { content: none; } }")
