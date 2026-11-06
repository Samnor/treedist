"""How much of the month's volume has a distribution of its own, and how much is approximated, as a Sankey diagram.

    <out>/sakerhet.html   one page for the month: mills on the left, then how the distribution of their volume was
                          found: from the work order's own harvester stock (S1), approximated (S2, S3) or not at all
                          (S4); the approximated part is split into its two kinds on the right

The diagram is plain SVG with no script or web font, so it opens and prints on a machine without internet.
"""

from __future__ import annotations

from html import escape

import pandas as pd

from . import __version__
from .core.allocate import CERTAINTY_TIERS
from .core.pipeline import MonthOutput
from .quality import Quality
from .schema import DEST, VOL

# What each class means for the reader, and whether it is settled.
GROUPS = {
    "S1": ("Bestämd", "Ur arbetsorderns egen skörd"),
    "S2": ("Approximerad", "Arbetsorderns tidigare skörd"),
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


def tier_volumes(output: MonthOutput) -> pd.DataFrame:
    """Delivered m3fub per mill and certainty class for the month, from the allocation the invoice is built on."""
    allocation = output.step.allocation
    if not len(allocation):
        return pd.DataFrame(columns=CERTAINTY_TIERS, dtype=float)
    volumes = allocation.pivot_table(index=DEST, columns="sakerhetsklass", values=VOL, aggfunc="sum", fill_value=0.0)
    return volumes.reindex(columns=CERTAINTY_TIERS, fill_value=0.0).clip(lower=0.0)


def _sv(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


def _volume(value: float) -> str:
    return _sv(value) if value > 0 else "–"


def _percent(part: float, whole: float) -> str:
    share = 100 * part / whole if whole > 0 else 0.0
    return "<1 %" if 0 < share < 0.5 else f"{share:.0f} %"


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
    # The approximated kinds sit level with their group, so their bands run straight.
    right = _stack(approximated, scale, top=middle["Approximerad"][0]) if "Approximerad" in middle else {}

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
        centres = _spread([y + height / 2 for y, height in placed.values()], gap, HEIGHT + 30 - gap / 2)
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


def _table(volumes: pd.DataFrame, quality: Quality | None = None) -> str:
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
    measured_head = (f'<th class="text">Bytte klass vid rättelse, sedan {escape(quality.since)}</th>'
                     if quality is not None else "")
    return (f'<table><thead><tr><th>Klass</th><th class="text">Fördelningen är</th><th class="text">Bygger på</th>{head}'
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
.guide h2 { font-size: 13pt; margin: 0 0 6pt; font-weight: 650; }
.guide dl { margin: 0; display: grid; grid-template-columns: 52mm 1fr; column-gap: 8pt; row-gap: 5pt; line-height: 1.4; }
.guide dt { font-weight: 600; }
.guide dd { margin: 0; color: #3a4452; }
@media screen { .guide { margin-top: 28pt; border-top: 1pt solid #d5dae1; padding-top: 14pt; } }
"""


def _guide(quality: Quality | None) -> str:
    """Every part of the page in words, on a page of its own, for the reader who wants to know what they see."""
    since = quality.since if quality is not None else ""
    parts = [
        ("Diagrammet", "Volymen flödar från vänster till höger. Ett bands bredd är den volym det bär, så banden in i en "
         "nod är tillsammans lika breda som noden. Noderna till vänster är tillsammans månadens hela volym, liksom noderna "
         "i mitten; noderna till höger delar upp den approximerade volymen. På skärmen visar markören över ett band eller "
         "en nod dess volym."),
        ("Sågverken, till vänster", "Den volym som levererats till varje sågverk under månaden, enligt inmätningen vid "
         "sågverket, i m3fub under bark: samma volym som i fakturans bilaga. Lass från tidigare månader som vänts denna "
         "månad ingår inte."),
        ("Bestämd (S1), i mitten", "Volym som ryms i arbetsorderns eget olevererade skördarlager. Fördelningen på "
         "diameter och längd är arbetsorderns egen skörd, så som skördaren mätte stockarna. Den är slutlig och rättas inte."),
        ("Approximerad (S2, S3), i mitten", "Volym där arbetsorderns eget lager inte räckte eller saknades. Fördelningen "
         "är en skattning: preliminär, och den rättas i en senare månad när skördardata för arbetsordern kommer. Till "
         "höger delas den i sina två slag."),
        ("S2 Arbetsorderns tidigare skörd, till höger", "Arbetsordern har levererat mer än det som fanns kvar i lagret. "
         "Det som går utöver lagret fördelas som arbetsorderns hela skörd hittills."),
        ("S3 Lånad från liknande arbetsordrar, till höger", "Arbetsordern saknar skördardata. Fördelningen lånas från "
         "andra arbetsordrar i samma handelssortiment, med störst vikt för de som liknar den mest."),
        ("Ingen fördelning (S4), i mitten", "Skördardata saknas för hela handelssortimentet, så det finns inget att låna "
         "från. Volymen bokas på klassen OKÄND och får bara ett pris om prislistan har en regel för det. Den rättas när "
         "skördardata kommer."),
        ("Siffrorna vid en nod", "Nodens volym i m3fub och dess andel av månadens levererade volym."),
    ]
    if quality is not None:
        parts.append(("Bytte klass vid rättelse", "När skördardata kommer ersätts de preliminära klasserna med de skördade. "
                      "Andelen är den del av den rättade volymen som hamnade i en annan diameter- eller längdklass än den "
                      "preliminära fördelningen sa: 0 % betyder att fördelningen var rätt, 100 % att ingen volym låg i "
                      f"rätt klass. Den räknas på allt som rättats sedan {since}, i leveransens fina klasser, så finare "
                      "klasser ger en högre andel. Inget rättat än betyder att ingen volym i klassen har rättats ännu. "
                      "S1 rättas aldrig, så dess fel syns inte här."))
    parts += [
        ("Färgerna", "Varje färg är en grupp: blått bestämd, orange approximerad, grönt S2, gult S3 och grått ingen "
         "fördelning. Sågverken är mörkgrå. Tabellen använder samma färger."),
        ("Tabellen", "En rad per säkerhetsklass. Fördelningen är och Bygger på säger vad klassen betyder; därefter "
         "volymen per sågverk, summan och andelen av månaden" + (", och sist hur stor del av den rättade volymen som "
         "bytte klass, av hur mycket som rättats" if quality is not None else "") + ". Ett streck betyder ingen volym."),
        ("Vad sidan inte säger", "Säkerhetsklassen säger vad fördelningen bygger på, inte hur stort felet är i en "
         "enskild bilaga. Även S1 bygger på skördarens mätning av stockarna, och på antagandet om vilka stockar som "
         "lämnade lagret."),
    ]
    items = "".join(f"<dt>{escape(term)}</dt><dd>{escape(text)}</dd>" for term, text in parts)
    return f'<section class="guide"><h2>Så läser du sidan</h2><dl>{items}</dl></section>'


def sankey_html(output: MonthOutput, quality: Quality | None = None) -> str:
    volumes = tier_volumes(output)
    total = float(volumes.to_numpy().sum())
    settled = float(volumes["S1"].sum()) if len(volumes) else 0.0
    period = output.step.period
    lead = (f"Av {_sv(total)} m3fub levererat under {period} har {_percent(settled, total)} en fördelning på klasser "
            "som bestäms av arbetsorderns egen skörd.")
    if total - settled > 0.0005:
        lead += (" Resten är approximerat ur arbetsorderns tidigare skörd, lånat från liknande arbetsordrar eller utan "
                 "fördelning, och rättas i en senare månad när skördardata kommer.")
    if quality is not None:
        measured = quality.by_tier()
        corrected, moved = float(measured["avraknat_m3fub"].sum()), float(measured["flyttat_m3fub"].sum())
        if corrected > 0.0005:
            lead += (f" Av de {_sv(corrected)} m3fub preliminär volym (S2–S4) som rättats sedan {quality.since} hamnade "
                     f"{_percent(moved, corrected)} i en annan klass än den preliminära fördelningen sa.")
    note = ("Volymen är inmätningens, i m3fub under bark; reverserade lass från tidigare månader ingår inte. "
            "Säkerhetsklassen säger vad fördelningen bygger på. Hur bra en approximation var syns först när skördardata "
            "kommer: rättelsen ersätter de preliminära klasserna med de skördade, och andelen av den rättade volymen som "
            "bytte klass är approximationens fel, mätt i leveransens fina klasser. S1 rättas aldrig, så dess fel syns "
            "inte här; även S1 bygger på skördarens mätning av stockarna.")
    return (
        f'<!doctype html>\n<html lang="sv"><head><meta charset="utf-8"><title>Säkerhet i fördelningen {period}</title>'
        f'<style>{_CSS}</style></head><body>\n<div class="eyebrow">Säkerhet i fördelningen · {period}</div>'
        f'<h1>Hur volymen fördelades på klasser</h1><p class="lead">{escape(lead)}</p>\n'
        f"{sankey_svg(volumes, quality)}\n{_table(volumes, quality)}<p class=\"note\">{escape(note)}</p>\n"
        f"{_guide(quality)}\n"
        f"<!-- treedist {__version__} -->\n</body></html>\n"
    )
