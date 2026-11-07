"""The appendix to each mill's invoice: its matrix, then how the matrix was found.

    <out>/bilagor/<mill>.html   first the matrix of all volume delivered to the mill in the month; then a Sankey
                                diagram from its assortments to how the distribution was found: from the work order's
                                own harvester stock (S1), approximated (S2, S3) or not at all (S4); then the work orders
                                behind the matrix, and every part in words

The diagram is plain SVG with no script or web font, so it opens and prints on a machine without internet.
"""

from __future__ import annotations

from html import escape

import pandas as pd

from . import __version__
from .appendix import MATRIX_NOTE, AppendixLayout, appendix_lead, changes_matrix_html, first_matrix_html
from .core.allocate import CERTAINTY_TIERS
from .core.pipeline import MonthOutput
from .quality import Quality
from .schema import AO, DEST, SORT, VOL
from .contract import EAST, MEASURE, NORTH, STEM
from .workorders import DRIFT, MEAN, PROGRESS, Facts, donors, mean_diameter, work_orders

# What each class means for the reader, and whether it is settled.
GROUPS = {
    "S1": ("Bestämd", "Ur arbetsorderns egen skörd"),
    "S2": ("Approximerad", "Arbetsorderns skörd hittills"),
    "S3": ("Approximerad", "Lånad från liknande arbetsordrar"),
    "S4": ("Ingen fördelning", "Okänd, bokad som OKÄND"),
}
BASIS = {
    "S1": "Arbetsorderns olevererade skördarlager. Volymen ryms i lagret, så fördelningen är arbetsorderns egen.",
    "S2": "Arbetsorderns hela skördehistorik, för volym som levererats utöver lagret. Preliminär: rättas när "
          "skördardata kommer.",
    "S3": "Andra arbetsordrar i samma sortiment, viktade efter likhet, när arbetsordern saknar skördardata. "
          "Preliminär: rättas när skördardata kommer.",
    "S4": "Inget: skördardata saknas för hela sortimentet. Volymen bokas på klassen OKÄND och rättas när "
          "skördardata kommer.",
}
# Categorical colours by identity, checked for colour blindness; text never wears them.
COLOURS = {"Bestämd": "#2a78d6", "Approximerad": "#eb6834", "S2": "#1baf7a", "S3": "#eda100",
           "Ingen fördelning": "#8c8b85", "mill": "#52514e"}

WIDTH, HEIGHT, NODE, GAP = 1000, 300, 12, 14
X = {0: 190, 1: 520, 2: 760}


def tier_volumes(output: MonthOutput, mill: str | None = None) -> pd.DataFrame:
    """Delivered m3fub per certainty class for the month, from the allocation the invoice is built on: per mill, or for
    one mill per assortment."""
    allocation = output.step.allocation
    if mill is not None:
        allocation = allocation[allocation[DEST] == mill]
    if not len(allocation):
        return pd.DataFrame(columns=CERTAINTY_TIERS, dtype=float)
    by = DEST if mill is None else SORT
    volumes = allocation.pivot_table(index=by, columns="sakerhetsklass", values=VOL, aggfunc="sum", fill_value=0.0)
    return volumes.reindex(columns=CERTAINTY_TIERS, fill_value=0.0).clip(lower=0.0)


def _sv(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


def _volume(value: float) -> str:
    # Volume too small to show at one decimal is still volume, not zero.
    return "–" if value <= 0 else "<0,1" if value < 0.05 else _sv(value)


def _percent(part: float, whole: float) -> str:
    share = 100 * part / whole if whole > 0 else 0.0
    if 0 < share < 0.5:
        return "<1 %"
    # Not all of it is not all of it, even when it rounds to 100.
    return ">99 %" if 99.5 <= share < 100 - 1e-9 and part < whole else f"{share:.0f} %"


def _stack(sizes: dict[str, float], scale: float, top: float = 20) -> dict[str, list[float]]:
    """Nodes in one column, top to bottom: [y, height]."""
    placed, y = {}, top
    for name, size in sizes.items():
        placed[name] = [y, size * scale]
        y += size * scale + GAP
    return placed


def _spread(centres: list[float], gap: float = 34, bottom: float = float("inf")) -> list[float]:
    """Label centres at least `gap` apart, pushed down from the top and then, if they run past `bottom`, up."""
    placed: list[float] = []
    for centre in centres:
        placed.append(max(centre, placed[-1] + gap) if placed else centre)
    for i in reversed(range(len(placed))):
        placed[i] = min(placed[i], bottom if i == len(placed) - 1 else placed[i + 1] - gap)
    return placed


def _band(x0: float, y0: float, x1: float, y1: float, thickness: float) -> str:
    middle = (x0 + x1) / 2
    return (f"M{x0:.1f},{y0:.1f} C{middle:.1f},{y0:.1f} {middle:.1f},{y1:.1f} {x1:.1f},{y1:.1f} "
            f"L{x1:.1f},{y1 + thickness:.1f} C{middle:.1f},{y1 + thickness:.1f} {middle:.1f},{y0 + thickness:.1f} "
            f"{x0:.1f},{y0 + thickness:.1f} Z")


def sankey_svg(volumes: pd.DataFrame, quality: Quality | None = None) -> str:
    """The diagram: mill → how the distribution was found → which approximation, with how much of the approximated
    volume changed class when it was corrected, where any has been."""
    total = float(volumes.to_numpy().sum())
    if total <= 0:
        return "<p>Ingen levererad volym denna månad.</p>"
    mills = volumes.sum(axis=1).sort_values(ascending=False)
    mills = mills[mills > 0]
    groups: dict[str, float] = {}
    for tier in CERTAINTY_TIERS:
        group = GROUPS[tier][0]
        groups[group] = groups.get(group, 0.0) + float(volumes[tier].sum())
    groups = {g: v for g, v in groups.items() if v > 0}
    approximated = {t: float(volumes[t].sum()) for t in ("S2", "S3") if volumes[t].sum() > 0}

    gaps = GAP * max(len(mills), len(groups), len(approximated)) - GAP
    scale = (HEIGHT - 40 - gaps) / total
    left, middle = _stack(dict(mills), scale), _stack(groups, scale)
    # The approximated kinds sit a little above their group, so that their bands rise away from its label, which
    # stands level with the node and below its top.
    right = (_stack(approximated, scale, top=max(middle["Approximerad"][0] - 40, 20)) if "Approximerad" in middle
             else {})

    parts = []
    out_y = {name: y for name, (y, _) in left.items()}
    in_y = {name: y for name, (y, _) in middle.items()}
    for mill in mills.index:
        for tier in CERTAINTY_TIERS:
            volume = float(volumes.at[mill, tier])
            if volume <= 0:
                continue
            group = GROUPS[tier][0]
            thickness = volume * scale
            parts.append(f'<path d="{_band(X[0] + NODE, out_y[mill], X[1], in_y[group], thickness)}" '
                         f'fill="{COLOURS[group]}" fill-opacity="0.3"><title>{escape(str(mill))} → {tier} '
                         f'{escape(GROUPS[tier][1])}: {_sv(volume)} m3fub</title></path>')
            out_y[mill] += thickness
            in_y[group] += thickness
    if right:
        y = middle["Approximerad"][0]
        for tier, volume in approximated.items():
            thickness = volume * scale
            parts.append(f'<path d="{_band(X[1] + NODE, y, X[2], right[tier][0], thickness)}" fill="{COLOURS[tier]}" '
                         f'fill-opacity="0.3"><title>{tier} {escape(GROUPS[tier][1])}: {_sv(volume)} m3fub</title></path>')
            y += thickness

    def node(x: float, y: float, height: float, colour: str, title: str) -> str:
        return (f'<rect x="{x}" y="{y:.1f}" width="{NODE}" height="{max(height, 1.5):.1f}" rx="2" fill="{colour}">'
                f"<title>{escape(title)}</title></rect>")

    def label(x: float, y: float, anchor: str, name: str, detail: str, measured: str | None) -> str:
        extra = f'<tspan x="{x}" dy="1.25em" class="measured">{escape(measured)}</tspan>' if measured else ""
        return (f'<text x="{x}" y="{y:.1f}" text-anchor="{anchor}" class="name">{escape(name)}'
                f'<tspan x="{x}" dy="1.25em" class="detail">{escape(detail)}</tspan>{extra}</text>')

    tiers_of = {"Bestämd": "S1", "Approximerad": "S2, S3", "Ingen fördelning": "S4"}
    columns = [
        (X[0], "end", COLOURS["mill"], left, {m: (str(m), float(mills[m]), False) for m in left}),
        (X[1], "start", None, middle, {g: (f"{g} ({tiers_of[g]})", groups[g], True) for g in middle}),
        (X[2], "start", None, right, {t: (f"{t} {GROUPS[t][1]}", approximated[t], True) for t in right}),
    ]
    for x, anchor, colour, placed, texts in columns:
        # Labels sit level with their node, but never on top of the label above.
        gap = 48 if quality is not None else 34
        # A node whose bands leave to the right has its label below it, where the rising bands cannot cross it.
        wanted = [y + height + gap / 2 if placed is middle and name == "Approximerad" and right else y + height / 2
                  for name, (y, height) in placed.items()]
        centres = _spread(wanted, gap, HEIGHT + 30 - gap / 2)
        for (name, (y, height)), centre in zip(placed.items(), centres):
            text, volume, share = texts[name]
            parts.append(node(x, y, height, colour or COLOURS[name], f"{text}: {_sv(volume)} m3fub"))
            detail = f"{_sv(volume)} m3fub" + (f" · {_percent(volume, total)}" if share else "")
            measured = _measured(quality, MEMBERS.get(name, ()))
            parts.append(label(x - 8 if anchor == "end" else x + NODE + 8, centre - (10 if measured else 4), anchor,
                               text, detail, measured))
    return (f'<svg viewBox="0 0 {WIDTH} {HEIGHT + 30}" role="img" aria-label="Volymens fördelning på säkerhetsklasser">'
            + "".join(parts) + "</svg>")


# The provisional classes behind each node that can have been corrected.
MEMBERS = {"Approximerad": ("S2", "S3"), "Ingen fördelning": ("S4",), "S2": ("S2",), "S3": ("S3",)}


def _measured(quality: Quality | None, tiers: tuple[str, ...]) -> str | None:
    """How much of the corrected volume of these classes changed class, if any of it has been corrected."""
    if quality is None or not tiers:
        return None
    measured = quality.by_tier().loc[list(tiers)]
    settled, moved = float(measured["avraknat_m3fub"].sum()), float(measured["flyttat_m3fub"].sum())
    if settled <= 0.0005:
        return "Inget rättat än"
    return f"{_percent(moved, settled)} bytte klass vid rättelse"


def _table(volumes: pd.DataFrame, quality: Quality | None = None, scope: str = "") -> str:
    total = float(volumes.to_numpy().sum())
    mills = [m for m in volumes.index if volumes.loc[m].sum() > 0]
    head = "".join(f"<th>{escape(str(m))}</th>" for m in mills)
    rows = []
    for tier in CERTAINTY_TIERS:
        volume = float(volumes[tier].sum())
        colour = COLOURS.get(tier, COLOURS[GROUPS[tier][0]])
        cells = "".join(f"<td>{_volume(float(volumes.at[m, tier]))}</td>" for m in mills)
        if quality is None:
            corrected = ""
        elif tier == "S1":
            corrected = "<td class=\"text\">Rättas inte</td>"
        else:
            row = quality.by_tier().loc[tier]
            corrected = (f"<td class=\"text\">{_percent(row['flyttat_m3fub'], row['avraknat_m3fub'])} av "
                         f"{_sv(row['avraknat_m3fub'])} m3fub</td>" if row["avraknat_m3fub"] > 0.0005
                         else "<td class=\"text\">Inget rättat än</td>")
        rows.append(f'<tr><th><span class="key" style="background:{colour}"></span>{tier}</th>'
                    f"<td class=\"text\">{escape(GROUPS[tier][0])}</td><td class=\"text\">{escape(BASIS[tier])}</td>"
                    f"{cells}<td>{_volume(volume)}</td><td>{_percent(volume, total) if volume > 0 else '–'}</td>{corrected}</tr>")
    sums = "".join(f"<td>{_sv(float(volumes.loc[m].sum()))}</td>" for m in mills)
    measured_head = (f'<th class="text">Bytte klass vid rättelse, {scope}sedan {escape(quality.since)}</th>'
                     if quality is not None else "")
    return (f'<table><thead><tr><th>Säkerhetsklass</th><th class="text">Fördelningen är</th><th class="text">Bygger på</th>{head}'
            f'<th>Summa, m3fub</th><th>Andel</th>{measured_head}</tr></thead><tbody>{"".join(rows)}'
            f'<tr class="sum"><th>Summa</th><td></td><td></td>{sums}<td>{_sv(total)}</td><td>100 %</td>'
            f'{"<td></td>" if quality is not None else ""}</tr></tbody></table>')


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
svg .measured { font-weight: 400; font-style: italic; fill: #52514e; }
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
.orders h2, .certainty h2, .guide h2 { font-size: 13pt; margin: 0 0 4pt; font-weight: 650; }
.orders h2 span { font-weight: 400; color: #52514e; font-size: 10pt; }
.orders .lead { margin-bottom: 6pt; }
.orders table { break-inside: auto; }
.orders thead th.group { text-align: center; border-bottom: 0.4pt solid #d5dae1; }
.orders thead tr:last-child th { white-space: normal; }
.lent, .measures, .where { break-inside: avoid; margin-top: 6pt; }
.where { margin-bottom: 8pt; }
.where svg { margin: 2pt 0 2pt; }
.where .note { margin-top: 2pt; }
.measures h3, .where h3 { font-size: 9.5pt; margin: 0 0 3pt; font-weight: 650; }
.measures table { width: auto; }
.measures .lead { margin-bottom: 4pt; }
.lent h3 { font-size: 9.5pt; margin: 0 0 3pt; font-weight: 650; }
td.nowrap { white-space: nowrap; }
td.flag { font-weight: 650; background: #fdf0e1; }
td.bar { background: linear-gradient(to right, rgba(42, 120, 214, .22) var(--w), transparent var(--w)); }
h2.millname { font-size: 15pt; margin: 4pt 0 2pt; font-weight: 650; border-bottom: 1.2pt solid #1c2430; padding-bottom: 2pt; }
h2.millname span { font-size: 10pt; font-weight: 400; color: #52514e; }
.matrix h2 { font-size: 12pt; margin: 2pt 0 5pt; font-weight: 650; }
.matrix h2 .total { font-size: 10pt; font-weight: 400; color: #5b6573; margin-left: 10pt; font-variant-numeric: tabular-nums; }
.matrix th, .matrix td { padding: 2pt 4pt; vertical-align: middle; }
.matrix thead th { vertical-align: bottom; }
.matrix th.corner { text-align: left; }
.matrix th.axis { text-align: center; color: #3a4452; border-bottom: 0.4pt solid #d5dae1; }
.matrix tbody th { font-weight: 600; background: #f6f8fa; }
.matrix td.sum, .matrix th.sum { background: #eef1f5; font-weight: 600; border-left: 0.8pt solid #8c96a3; }
.matrix tr.total th, .matrix tr.total td { background: #eef1f5; font-weight: 600; border-top: 0.8pt solid #8c96a3; }
.matrix tr { break-inside: avoid; }
.matrix h3 { font-size: 10pt; margin: 12pt 0 4pt; font-weight: 600; color: #3a4452; }
.changes { break-inside: avoid; }
.certainty + .orders { break-before: page; }
@media screen { .orders + .mill, .certainty, .guide { margin-top: 28pt; border-top: 1pt solid #d5dae1; padding-top: 14pt; } }
"""


def _tiers(row: pd.Series) -> str:
    """The classes a work order's volume was classed by, largest first, as shares of it."""
    shares = [(t, float(row[t]) / float(row[VOL])) for t in CERTAINTY_TIERS if row[t] > 0.0005]
    if len(shares) == 1:
        return shares[0][0]
    return ", ".join(f"{t} {'>99 %' if share > 0.995 else _percent(share, 1)}"
                     for t, share in sorted(shares, key=lambda s: -s[1]))


def _plural(count: int) -> str:
    return f"{count} arbetsorder" if count == 1 else f"{count} arbetsordrar"


def _share(part: float, whole: float) -> str:
    return _percent(part, whole) if whole > 0.0005 and part > 0.0005 else "–"


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
    early, late = row[DRIFT[2]], row[DRIFT[3]]
    if pd.isna(early) or pd.isna(late):
        return "–"
    return f"{_sv(early)} → {_sv(late)}"


# A harvest whose mean diameter moved this much between its halves is marked: a month's delivery may differ from it.
DRIFT_CM = 2.0


def _overshipped(row: pd.Series) -> bool:
    return row[PROGRESS[0]] > 0.0005 and row[PROGRESS[1]] > row[PROGRESS[0]] * 1.005


def _drifted(row: pd.Series) -> bool:
    early, late = row[DRIFT[2]], row[DRIFT[3]]
    return not (pd.isna(early) or pd.isna(late)) and abs(late - early) >= DRIFT_CM


def _flagged(text: str, flag: bool) -> str:
    return f'<td class="flag">{text}</td>' if flag else f"<td>{text}</td>"


def _cm(value: float) -> str:
    return "–" if pd.isna(value) else _sv(value)


def _orders(mill: str, rows: pd.DataFrame, lent: pd.DataFrame, matrix_mean: float, facts: Facts = Facts()) -> str:
    """The work orders behind one mill's matrix: who they are, how much each brought and how far along each one is."""
    total = float(rows[VOL].sum())
    body = "".join(
        f"<tr><th>{escape(str(r[AO]))}</th><td class=\"text\">{escape(str(r[SORT]))}</td><td>{_sv(r[VOL])}</td>"
        f"<td class=\"bar\" style=\"--w:{100 * r['andel_av_sagverket']:.1f}%\">{_percent(r['andel_av_sagverket'], 1)}</td><td>{_cm(r[MEAN])}</td><td class=\"text nowrap\">{_tiers(r)}</td>"
        f"<td>{_volume(r[PROGRESS[0]])}</td>{_flagged(_share(r[PROGRESS[1]], r[PROGRESS[0]]), _overshipped(r))}"
        f"<td>{_volume(r[PROGRESS[2]])}</td><td>{_felled(r)}</td>{_flagged(_diameters(r), _drifted(r))}</tr>"
        for _, r in rows.iterrows())
    per_order = rows.groupby(AO)[VOL].sum().sort_values(ascending=False)
    count = len(per_order)
    lead = f"Matrisen bygger på virke från {_plural(count)}."
    if count > 1:
        half = int((per_order.cumsum() < total / 2).sum()) + 1
        lead += (f" Den största, {per_order.index[0]}, står för {_percent(float(per_order.iloc[0]), total)} av volymen"
                 + (f", och {half} av dem för hälften." if half > 1 else "."))
    if not pd.isna(matrix_mean):
        lead += (f" Matrisens medeldiameter är {_sv(matrix_mean)} cm; kolumnen Medeldiameter visar vilka arbetsordrar "
                 "som drar den uppåt och vilka nedåt.")
    extra = sorted(set(lent["givare"]) - set(rows[AO]))
    if extra:
        lead += (f" Den lånade fördelningen (S3) bygger dessutom på skördardata från {_plural(len(extra))} som inte "
                 "levererade hit denna månad.")
    return (f'<section class="orders"><h2>Arbetsordrarna bakom matrisen <span>· {escape(str(mill))} · '
            f'{_sv(total)} m3fub</span></h2><p class="lead">{escape(lead)}</p>{_where(rows, facts.sites)}<table><thead>'
            f"<tr><th rowspan=\"2\">Arbetsorder</th><th class=\"text\" rowspan=\"2\">Sortiment</th>"
            f"<th colspan=\"4\" class=\"group\">Till sågverket i månaden</th>"
            f"<th colspan=\"5\" class=\"group\">Arbetsorderns skörd</th></tr>"
            f"<tr><th>m3fub</th><th>Andel av sågverket</th><th>Medeldiameter, cm</th><th class=\"text\">Säkerhetsklass</th><th>Skördat hittills, m3fub</th>"
            f"<th>Inkört i månaden</th><th>Kvar i lager, m3fub</th><th>Fälld</th>"
            f"<th>Medeldiameter, cm, första → andra halvan</th></tr></thead><tbody>{body}</tbody></table>"
            f"{_lent(lent)}{_measures(rows, facts.measures)}</section>")


def _lent(lent: pd.DataFrame, shown: int = 5) -> str:
    """Where each borrowed distribution came from: how many work orders, and those that weigh the most."""
    if not len(lent):
        return ""
    rows = []
    for (ao, sortiment), block in lent.groupby([AO, SORT], sort=False):
        weights = block["vikt"] / block["vikt"].sum()
        half = int((weights.cumsum() < 0.5).sum()) + 1
        top = ", ".join(f"{escape(str(g))} {_percent(w, 1)}" for g, w in zip(block["givare"][:shown], weights[:shown]))
        rows.append(f"<tr><th>{escape(str(ao))}</th><td class=\"text\">{escape(str(sortiment))}</td>"
                    f"<td>{_sv(float(block[VOL].iloc[0]))}</td><td>{len(block)}</td><td>{half}</td>"
                    f"<td class=\"text\">{top}</td></tr>")
    return ('<div class="lent"><h3>Lånad fördelning (S3): varifrån den kom</h3><table><thead><tr><th>Arbetsorder</th>'
            '<th class="text">Sortiment</th><th>m3fub</th><th>Givare</th><th>Givare för halva vikten</th>'
            f'<th class="text">Störst vikt</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def _guide(quality: Quality | None) -> str:
    """Every part of the appendix in words, on a page of its own, for the reader who wants to know what they see. The
    left of the diagram is the mill's assortments, and the measure of corrections covers every mill."""
    since = quality.since if quality is not None else ""
    parts = [
        ("Ordningen", "Först matrisen, sedan diagrammet och tabellen över hur dess fördelning på klasser togs fram, "
         "sedan arbetsordrarna bakom den, och sist den här förklaringen."),
        ("Matrisen", "All volym som levererats till sågverket under månaden: stockarnas längd i dm som rader och diameter i cm "
         "som kolumner, båda med klassens nedre gräns, för alla handelssortiment tillsammans. Varje cell är procent av "
         "diameterklassens levererade volym, så att varje kolumn summerar till 100; – är ingen volym och <1 under en halv "
         "procent. Summan är m3fub under bark. Krediterade lass och rättade fördelningar från tidigare månader står i en "
         "egen matris i m3fub."),
        ("Diagrammet", "Volymen flödar från vänster till höger. Ett bands bredd är den volym det bär, så banden in i en "
         "nod är tillsammans lika breda som noden. Noderna till vänster är tillsammans matrisens hela volym, liksom noderna "
         "i mitten; noderna till höger delar upp den approximerade volymen. Vid varje nod står dess volym i m3fub och "
         "andel av matrisen. Färgerna är grupperna: blått bestämd, orange approximerad, "
         "grönt S2, gult S3 och grått ingen fördelning, med sortimenten i mörkgrått; tabellen under har samma färger. På skärmen visar markören över ett "
         "band eller en nod dess volym."),
        ("Handelssortimenten, till vänster", "Den volym av varje inmätt handelssortiment som levererats till "
         "sågverket under månaden, enligt inmätningen, i m3fub under bark; tillsammans matrisens summa. Lass från "
         "tidigare månader som vänts denna månad ingår inte."),
        ("Bestämd (S1), i mitten", "Volym som ryms i arbetsorderns eget olevererade skördarlager. Fördelningen på "
         "diameter och längd är arbetsorderns egen skörd, så som skördaren mätte stockarna. Den är slutlig och rättas inte."),
        ("Approximerad (S2, S3), i mitten", "Volym där arbetsorderns eget lager inte räckte eller saknades. Fördelningen "
         "är en skattning: preliminär, och den rättas i en senare månad när skördardata för arbetsordern kommer. Till "
         "höger delas den i sina två slag."),
        ("S2 Arbetsorderns skörd hittills, till höger", "Arbetsordern har levererat mer än det som fanns kvar i lagret. "
         "Det som går utöver lagret fördelas som allt skördaren har rapporterat för arbetsordern hittills, även det som redan "
         "levererats."),
        ("S3 Lånad från liknande arbetsordrar, till höger", "Arbetsordern saknar skördardata. Fördelningen lånas från "
         "andra arbetsordrar i samma handelssortiment, med störst vikt för de som liknar den mest."),
        ("Ingen fördelning (S4), i mitten", "Skördardata saknas för hela handelssortimentet, så det finns inget att låna "
         "från. Volymen bokas på klassen OKÄND och får bara ett pris om prislistan har en regel för det. Den rättas när "
         "skördardata kommer."),
    ]
    if quality is not None:
        parts.append(("Bytte klass vid rättelse", "När skördardata kommer ersätts de preliminära klasserna med de skördade. "
                      "Andelen är den del av den rättade volymen som hamnade i en annan diameter- eller längdklass än den "
                      "preliminära fördelningen sa: 0 % betyder att fördelningen var rätt, 100 % att ingen volym låg i "
                      f"rätt klass. Den räknas på allt som rättats sedan {since}, i leveransens fina klasser, så finare "
                      "klasser ger en högre andel. Inget rättat än betyder att ingen volym i klassen har rättats ännu. "
                      "S1 rättas aldrig, så dess fel syns inte här."
                      + " Måttet gäller alla sågverk tillsammans, eftersom det behöver mycket rättad volym för att "
                      "säga något, och står därför bara i tabellen."))
    parts += [
        ("Arbetsordrarna bakom matrisen", "Varje arbetsorder som levererat till sågverket under månaden, en rad per "
         "arbetsorder och sortiment. Summan av m3fub är matrisens summa. Andel av sågverket, och meningen över tabellen "
         "om den största och hur många som står för hälften, visar om några få arbetsordrar dominerar matrisen. Säkerhetsklass är "
         "säkerhetsklassen för just den arbetsorderns volym."),
        ("Arbetsorderns skörd", "Skördat hittills är allt skördaren rapporterat för arbetsordern och sortimentet, "
         "omräknat som fördelningen räknar. Inkört i månaden är arbetsorderns hela leverans i månaden, till alla "
         "sågverk, som andel av det skördade; över 100 % betyder att mer kördes in än skördardatan visar, och det som "
         "går utöver får S2. Kvar i lager är det skördade som ännu inte levererats. Ett sådant värde är fetstilt "
         "och tonat."),
        ("Fälld och medeldiameter", "Första och sista avverkningsdag i skördardatan. Medeldiametern är den "
         "volymvägda diameterklassen, i cm, för första och andra halvan av skörden i den ordning den fälldes. En stor "
         "skillnad betyder att stockarna ändrades medan arbetsordern skördades, så att en månads leverans kan skilja "
         "sig från arbetsorderns hela skörd. En skillnad på minst 2 cm är fetstilt och tonad. Ett streck betyder att "
         "avverkningsdag eller diameter saknas."),
        ("Kartan", "Var arbetsordrarna bakom matrisen ligger, i SWEREF 99 TM, när källan har deras läge. Punktens "
         "yta är arbetsorderns volym till sågverket under månaden och färgen den säkerhetsklass som större delen av "
         "volymen fick. Kartan saknar bakgrund, så att bilagan går att öppna utan internet; skalstocken och pilen mot "
         "norr ger avstånd och riktning."),
        ("Åtgärder och medelstam", "Åtgärderna i varje arbetsorder enligt källan, med medelstam i m3fub under bark "
         "och planerad volym. En arbetsorder med flera åtgärder där den största medelstammen är minst dubbelt så stor "
         "som den minsta är fetstil och tonad: dess delar kan ge olika stockar, så att en månads leverans kan skilja "
         "sig från arbetsorderns hela skörd."),
        ("Lånad fördelning (S3)", "För en arbetsorder utan skördardata lånas fördelningen från alla arbetsordrar med "
         "skördardata i samma sortiment, även sådana som inte levererade denna månad. Givare är hur många de är, Givare "
         "för halva vikten hur få som står för hälften, och Störst vikt de som väger mest, med sin andel av vikten."),
        ("Tabellen under diagrammet", "En rad per säkerhetsklass. Fördelningen är och Bygger på säger vad klassen betyder; därefter "
         "volymen per handelssortiment, summan och andelen av matrisen" + (", och sist hur stor del av den rättade volymen som "
         "bytte klass, av hur mycket som rättats" if quality is not None else "") + ". Ett streck betyder ingen volym."),
        ("Vad sidan inte säger", "Säkerhetsklassen säger vad fördelningen bygger på, inte hur stort felet är i en "
         "enskild bilaga. Även S1 bygger på skördarens mätning av stockarna, och på antagandet om vilka stockar som "
         "lämnade lagret. Kartan och åtgärderna visas bara när källan har arbetsordrarnas läge och åtgärder."),
    ]
    items = "".join(f"<div><dt>{escape(term)}</dt><dd>{escape(text)}</dd></div>" for term, text in parts)
    return f'<section class="guide"><h2>Så läser du sidan</h2><dl>{items}</dl></section>'


MAP_WIDTH, MAP_HEIGHT, MAP_PAD = 1000, 360, 46
# A lone work order, or a few close together, still get a map a few kilometres wide.
MAP_MIN_SPAN = 6000.0


def _map(rows: pd.DataFrame, places: pd.DataFrame) -> str:
    """Where the work orders behind the matrix are, relative to each other, as plain SVG with no background map."""
    if not len(places):
        return ""
    per = rows.groupby(AO)[[VOL, *CERTAINTY_TIERS]].sum()
    located = per.join(places.set_index(AO)[[NORTH, EAST]], how="inner")
    if not len(located):
        return ""
    east, north = located[EAST].astype(float), located[NORTH].astype(float)
    span_x = max(east.max() - east.min(), MAP_MIN_SPAN)
    span_y = max(north.max() - north.min(), MAP_MIN_SPAN * (MAP_HEIGHT - 2 * MAP_PAD) / (MAP_WIDTH - 2 * MAP_PAD))
    scale = min((MAP_WIDTH - 2 * MAP_PAD - 120) / span_x, (MAP_HEIGHT - 2 * MAP_PAD) / span_y)
    middle_x, middle_y = (east.max() + east.min()) / 2, (north.max() + north.min()) / 2

    def x(value: float) -> float:
        return (MAP_WIDTH - 120) / 2 + (value - middle_x) * scale

    def y(value: float) -> float:
        return MAP_HEIGHT / 2 - (value - middle_y) * scale

    largest = float(located[VOL].max())
    parts: list[str] = []
    taken: list[tuple[float, float, float, float]] = []
    points: list[tuple[str, float, float, float]] = []
    # Largest first, so that a small work order is never hidden under a large one.
    for ao, row in located.sort_values(VOL, ascending=False).iterrows():
        groups: dict[str, float] = {}
        for tier in CERTAINTY_TIERS:
            groups[GROUPS[tier][0]] = groups.get(GROUPS[tier][0], 0.0) + float(row[tier])
        colour = COLOURS[max(groups, key=groups.get)]
        radius = 4 + 14 * (float(row[VOL]) / largest) ** 0.5 if largest > 0 else 4
        cx, cy = x(float(row[EAST])), y(float(row[NORTH]))
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" fill="{colour}" fill-opacity="0.55" '
                     f'stroke="{colour}" stroke-width="1.2"><title>{escape(str(ao))}: {_sv(float(row[VOL]))} m3fub'
                     f"</title></circle>")
        points.append((str(ao), cx, cy, radius))
    # Names go where they cover neither another name nor a point.
    taken += [(cx - r, cy - r, 2 * r, 2 * r) for _, cx, cy, r in points]
    for ao, cx, cy, radius in points:
        parts.append(_map_label(ao, cx, cy, radius, taken))
    # A scale bar about a quarter of the width, at a round number of kilometres.
    target = (MAP_WIDTH - 2 * MAP_PAD) / 4 / scale / 1000
    km = next((k for k in (100, 50, 20, 10, 5, 2, 1, 0.5) if k <= target), 0.5)
    bar = km * 1000 * scale
    bottom = MAP_HEIGHT - 14
    parts.append(f'<path d="M{MAP_PAD},{bottom - 6} V{bottom} H{MAP_PAD + bar:.1f} V{bottom - 6}" fill="none" '
                 f'stroke="#52514e" stroke-width="1.5"/><text x="{MAP_PAD + bar + 6:.1f}" y="{bottom}" class="detail">'
                 f'{_sv(km, 0 if km >= 1 else 1)} km</text>')
    parts.append(f'<path d="M{MAP_WIDTH - 30},{MAP_PAD + 22} V{MAP_PAD - 2} M{MAP_WIDTH - 36},{MAP_PAD + 6} '
                 f'L{MAP_WIDTH - 30},{MAP_PAD - 4} L{MAP_WIDTH - 24},{MAP_PAD + 6}" fill="none" stroke="#52514e" '
                 f'stroke-width="1.5"/><text x="{MAP_WIDTH - 30}" y="{MAP_PAD + 38}" text-anchor="middle" '
                 'class="name">N</text>')
    legend = "".join(
        f'<circle cx="{MAP_WIDTH - 110}" cy="{MAP_HEIGHT - 70 + 18 * i}" r="5" fill="{COLOURS[g]}" fill-opacity="0.55" '
        f'stroke="{COLOURS[g]}"/><text x="{MAP_WIDTH - 100}" y="{MAP_HEIGHT - 66 + 18 * i}" class="detail">{g}</text>'
        for i, g in enumerate(("Bestämd", "Approximerad", "Ingen fördelning")))
    return (f'<svg class="map" viewBox="0 0 {MAP_WIDTH} {MAP_HEIGHT}" role="img" aria-label="Arbetsordrarnas läge">'
            f'<rect x="0.5" y="0.5" width="{MAP_WIDTH - 1}" height="{MAP_HEIGHT - 1}" fill="#f6f8fa" stroke="#d5dae1"/>'
            + "".join(parts) + legend + "</svg>")


def _map_label(text: str, cx: float, cy: float, radius: float, taken: list[tuple[float, float, float, float]]) -> str:
    """A work order's name beside its point, moved up or down until it does not cover a name already placed."""
    width, height = 7.2 * len(text), 14.0
    for side in (1, -1):
        left = cx + radius + 4 if side == 1 else cx - radius - 4 - width
        for shift in (0, 14, -14, 28, -28, 42, -42):
            box = (left, cy - 10 + shift, width, height)
            if all(box[0] + box[2] <= o[0] or o[0] + o[2] <= box[0] or box[1] + box[3] <= o[1] or o[1] + o[3] <= box[1]
                   for o in taken):
                taken.append(box)
                return f'<text x="{left:.1f}" y="{cy + 4 + shift:.1f}" class="detail">{escape(text)}</text>'
    taken.append((cx + radius + 4, cy - 10, width, height))
    return f'<text x="{cx + radius + 4:.1f}" y="{cy + 4:.1f}" class="detail">{escape(text)}</text>'


def _where(rows: pd.DataFrame, places: pd.DataFrame) -> str:
    """The map with a line on what it shows, or nothing when the source has no positions."""
    drawn = _map(rows, places)
    if not drawn:
        return ""
    count = rows[AO].nunique()
    located = int(rows[AO].drop_duplicates().isin(set(places[AO])).sum())
    missing = count - located
    text = (f"Var de {_plural(located)} ligger i förhållande till varandra, i SWEREF 99 TM. Punktens yta är volymen "
            "till sågverket och färgen fördelningens säkerhet. Kartan har ingen bakgrund, så att bilagan går att öppna "
            "utan internet.")
    if missing:
        text += f" {_plural(missing).capitalize()} saknar läge i källan och syns inte."
    return f'<div class="where"><h3>Var arbetsordrarna ligger</h3>{drawn}<p class="note">{escape(text)}</p></div>'


# A work order whose measures differ this much in mean stem volume is marked: its parts may give different logs.
STEM_RATIO = 2.0


def _measures(rows: pd.DataFrame, held: pd.DataFrame) -> str:
    """The measures of the work orders behind the matrix, with mean stem volume, where the source has them."""
    held = held[held[AO].isin(set(rows[AO]))]
    if not len(held):
        return ""
    body, multi, apart = [], 0, 0
    order = rows.groupby(AO)[VOL].sum().sort_values(ascending=False).index
    for ao in [a for a in order if a in set(held[AO])]:
        block = held[held[AO] == ao]
        stems = block[STEM].dropna()
        differs = len(block) > 1 and len(stems) > 1 and stems.min() > 0 and stems.max() / stems.min() >= STEM_RATIO
        multi += len(block) > 1
        apart += differs
        for i, (_, m) in enumerate(block.iterrows()):
            head = f'<th rowspan="{len(block)}">{escape(str(ao))}</th>' if i == 0 else ""
            stem = "–" if pd.isna(m[STEM]) else _sv(float(m[STEM]), 2)
            body.append(f'<tr>{head}<td class="text">{escape(str(m[MEASURE]))}</td>{_flagged(stem, differs)}'
                        f'<td>{_volume(float(m[VOL])) if not pd.isna(m[VOL]) else "–"}</td></tr>')
    shown = held[AO].nunique()
    lead = f"{_plural(shown).capitalize()} har åtgärder i källan."
    if multi:
        lead += (f" {multi} av dem har flera åtgärder, och i {apart} av dessa är den största medelstammen minst "
                 "dubbelt så stor som den minsta.")
    return (f'<div class="measures"><h3>Åtgärder och medelstam</h3><p class="lead">{escape(lead)}</p><table><thead>'
            '<tr><th>Arbetsorder</th><th class="text">Åtgärd</th><th>Medelstam, m3fub</th><th>Planerad volym, m3fub</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def mill_appendix_html(output: MonthOutput, mill: str, quality: Quality | None = None,
                       layout: AppendixLayout = AppendixLayout(), facts: Facts | None = None) -> str:
    """The appendix to one mill's invoice for the month: first the matrix of all volume delivered there, then how its
    distribution on classes was found, the work orders behind it, and every part in words."""
    period = output.step.period
    volumes = tier_volumes(output, mill)
    total = float(volumes.to_numpy().sum())
    settled = float(volumes["S1"].sum()) if len(volumes) else 0.0
    rows = work_orders(output)
    rows = rows[rows[DEST] == mill]
    lent = donors(output)
    lent = lent[lent[DEST] == mill]
    mean = float(mean_diameter(output.step.allocation, [DEST]).get(mill, float("nan")))
    intro = (appendix_lead(output, mill) + " Först står matrisen, sedan hur dess fördelning på klasser togs fram och "
             "vilka arbetsordrar den bygger på, och sist en förklaring av varje del.")
    lead = (f"Av matrisens {_sv(total)} m3fub har {_percent(settled, total)} en fördelning på klasser som bestäms av "
            "arbetsorderns egen skörd." if total > 0.0005 else
            "Inget levererades till sågverket denna månad; bilagan visar bara ändringar av tidigare månader.")
    if total - settled > 0.0005:
        lead += (" Resten är approximerat ur arbetsorderns skörd hittills, lånat från liknande arbetsordrar eller utan "
                 "fördelning, och rättas i en senare månad när skördardata kommer.")
    if quality is not None:
        measured = quality.by_tier()
        corrected, moved = float(measured["avraknat_m3fub"].sum()), float(measured["flyttat_m3fub"].sum())
        if corrected > 0.0005:
            lead += (f" För alla sågverk tillsammans hamnade {_percent(moved, corrected)} av de {_sv(corrected)} m3fub "
                     f"preliminär volym som rättats sedan {quality.since} i en annan klass än den preliminära "
                     "fördelningen sa.")
    note = "Volymen är inmätningens, i m3fub under bark; reverserade lass från tidigare månader ingår inte."
    matrix = first_matrix_html(output, mill, layout)
    certainty = (f'<section class="certainty"><h2>Hur matrisen togs fram</h2><p class="lead">{escape(lead)}</p>\n'
                 f"{sankey_svg(volumes)}\n{_table(volumes, quality, 'alla sågverk ')}"
                 f'<p class="note">{escape(note)}</p></section>')
    facts = facts or Facts()
    orders = _orders(mill, rows, lent, mean, facts) if len(rows) else ""
    title = f"Bilaga till faktura {period}, {mill}"
    return (
        f'<!doctype html>\n<html lang="sv"><head><meta charset="utf-8"><title>{escape(title)}</title>'
        f"<style>{_CSS}{_running_mill(mill, period)}</style></head><body>\n<header><div class=\"eyebrow\">Bilaga till "
        f'faktura · {period}</div><h1>{escape(str(mill))}</h1><p class="lead">{escape(intro)}</p></header>\n'
        f'<section class="mill"><div class="matrix">{matrix}{changes_matrix_html(output, mill, layout)}</div>'
        f'<p class="note">{escape(MATRIX_NOTE)} Summa är m3fub under bark.</p></section>\n'
        f"{certainty}\n{orders}\n{_guide(quality)}\n"
        f"<!-- treedist {__version__} -->\n</body></html>\n"
    )


def _running_mill(mill: str, period: str) -> str:
    """Mill, period and page number in the margins, so that a loose page still says what it belongs to."""
    words = f"{mill} · Bilaga till faktura {period}".replace("\\", "\\\\").replace('"', '\\"')
    box = "font-family: \"Segoe UI\", \"Helvetica Neue\", Arial, sans-serif; font-size: 7.5pt; color: #5b6573;"
    return (f'@page {{ @top-left {{ content: "{words}"; {box} }} '
            f'@bottom-right {{ content: "Sida " counter(page) " av " counter(pages); {box} }} }}'
            "@page :first { @top-left { content: none; } }")
