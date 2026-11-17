"""The worked example on the appendix: how volume delivered beyond a contract object's stock gets its classes (S2).

    steps()                the example in three steps, each with a title, a paragraph and a small figure
    example_rows()         the same steps as text, for the workbook, which has no figures
    this_month(b)          the mill's own volume beyond the stock in the month, with the contract objects that brought most

The numbers are round and made up, one contract object and one assortment with three diameter classes, and every later
number follows from the first three. The classes are named as the matrix names them, by diameter in cm and length in
dm, so that none can be taken for an assortment: the assortment is the one measured in, and is never estimated. The
last step shows the whole harvest so far and the volume beyond the stock split the same way, per diameter and length
class, a cell of the matrix. The figures are plain SVG with no script or web font, as the rest of the appendix.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from .bilaga import NAMES, Bilaga, percent, plural, sv, volume_text
from .sankey import COLOURS
from .schema import AO, SORT, VOL
from .workorders import PROGRESS

# The diameter classes of the example, named by their lower bound in cm as the columns of the matrix are.
DIAMETERS = (18, 24, 30)
CLASSES = tuple(f"{d} cm" for d in DIAMETERS)
# What the harvester has reported for the contract object so far, what of it is still in the stock, and what is measured in
# at the mill in the month, in m3fub.
HARVESTED = (30, 50, 20)
STOCK = (10, 20, 10)
LOAD = 50

BEYOND = LOAD - sum(STOCK)
ESTIMATE = tuple(BEYOND * h // sum(HARVESTED) for h in HARVESTED)
MONTH = tuple(s + e for s, e in zip(STOCK, ESTIMATE))

# The same harvest with its length classes, in dm: one row per length, one column per diameter class, in m3fub. The
# whole harvest is 100 m3fub, so each number is also the cell's share of it in percent.
LENGTHS = (43, 49)
HARVESTED_CELLS = ((20, 20, 5), (10, 30, 15))
ESTIMATE_CELLS = tuple(tuple(BEYOND * v / sum(HARVESTED) for v in row) for row in HARVESTED_CELLS)

# Wood delivered in earlier months: context, not a source, so it has no series colour.
DELIVERED = "#c9ced6"

TITLE = f"{NAMES['S2']}: så fördelas volym utöver lagret"
LEAD = ("Skördaren rapporterar varje stocks diameter och längd. Det som är rapporterat men ännu inte levererat är "
        "avtalsobjektets lager, och ett lass som mäts in får sina klasser ur lagret. Ibland mäts mer in än lagret räcker "
        "till, till exempel när sågverket mäter något mer än skördaren eller när en del av skörden rapporteras först "
        "efter att lasset körts.")
# The one thing the page has to say, and what kind of number it gives.
RULE = ("Volym utöver lagret fördelas på diameter- och längdklasser med samma andelar som avtalsobjektets hela skörd "
        "hittills, alltså allt skördaren har rapporterat för avtalsobjektet.")
NOTE = (f"Det kallas {NAMES['S2'].lower()} och är en uppskattning, inte en mätning. Handelssortimentet uppskattas "
        "aldrig: det är det som mäts in vid sågverket.")
LEGEND = ((COLOURS["S1"], "Eget lager"), (COLOURS["S2"], "Egen skörd i snitt, utöver lagret"),
          (DELIVERED, "Levererat tidigare månader"))


@dataclass(frozen=True)
class Step:
    title: str
    text: str
    figure: str


def _listed(values: tuple) -> str:
    said = [f"{value} i {name}" for value, name in zip(values, CLASSES)]
    return f"{', '.join(said[:-1])} och {said[-1]}"


def _three(values: tuple) -> str:
    return f"{values[0]}, {values[1]} och {values[2]}"


def _tenth(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _words(figures: bool = True) -> list[tuple[str, str]]:
    """The three steps as (title, text). Each title says what the step shows. The numbers of the last step are left
    to its figure where there are figures."""
    whole = sum(HARVESTED)
    first, got = HARVESTED_CELLS[0][0], ESTIMATE_CELLS[0][0]
    cells = ""
    if not figures:
        per_length = [(f"{_three(tuple(100 * v // whole for v in row))} % i {length} dm",
                       f"{_three(tuple(_tenth(v) for v in got_row))} i {length} dm")
                      for length, row, got_row in zip(LENGTHS, HARVESTED_CELLS, ESTIMATE_CELLS)]
        cells = (f" Av hela skörden hittills är {' och '.join(s for s, _ in per_length)}, i ordningen "
                 f"{_three(DIAMETERS)} cm. Av de {BEYOND} m3fub blir det {' och '.join(g for _, g in per_length)}.")
    return [
        (f"1 Skörden hittills: {whole} m3fub",
         f"Skördaren har hittills rapporterat {whole} m3fub av ett handelssortiment för avtalsobjektet, här i tre "
         f"diameterklasser: {_listed(HARVESTED)}. {whole - sum(STOCK)} har levererats tidigare månader. Kvar i lagret "
         f"finns {sum(STOCK)}: {_listed(STOCK)}."),
        (f"2 Lasset: {BEYOND} m3fub utöver lagret",
         f"Under månaden mäts {LOAD} m3fub av sortimentet in vid sågverket. Lagret räcker till {sum(STOCK)}, och de "
         f"har klasserna skördaren mätte. De sista {BEYOND} är volym utöver lagret: deras diameter och längd "
         "uppskattas i nästa steg."),
        (f"3 De {BEYOND} får skördens andelar per diameter och längd",
         f"De {BEYOND} fördelas med samma andelar som hela skörden hittills, per kombination av diameter- och "
         f"längdklass, en cell i matrisen. Här har skörden två längder. {100 * first // whole} % av hela skörden "
         f"hittills är {CLASSES[0]} i {LENGTHS[0]} dm, så den cellen får {100 * first // whole} % av de {BEYOND}: "
         f"{_tenth(got)} m3fub. Alla celler räknas så.{cells} Per diameterklass blir det {_three(ESTIMATE)}, och med "
         f"de {sum(STOCK)} ur lagret står {_three(MONTH)} i bilagan."),
    ]


def example_rows() -> list[tuple[str, str]]:
    """The example as (term, text), for a format without figures."""
    return [("Exempel: volym utöver lagret", f"{LEAD} {RULE} {NOTE}"), *_words(figures=False)]


WIDTH, HEIGHT, BASE = 240, 180, 160
CENTRES = (50, 120, 190)


def _svg(parts: list[str], label: str) -> str:
    return f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{escape(label)}">{"".join(parts)}</svg>'


def _column(x: float, y: float, width: float, height: float, colour: str, title: str, top: bool) -> str:
    """One segment of a column; the data end, the top of the uppermost segment, is rounded."""
    if not top:
        return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" fill="{colour}">'
                f"<title>{escape(title)}</title></rect>")
    r = min(4.0, height)
    return (f'<path d="M{x:.1f},{y + height:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} H{x + width - r:.1f} '
            f'Q{x + width:.1f},{y:.1f} {x + width:.1f},{y + r:.1f} V{y + height:.1f} Z" fill="{colour}">'
            f"<title>{escape(title)}</title></path>")


def _axis(names: bool = True) -> list[str]:
    parts = [f'<line x1="14" y1="{BASE + 0.5}" x2="{WIDTH - 14}" y2="{BASE + 0.5}" stroke="#8c96a3"/>']
    if names:
        parts += [f'<text x="{x}" y="{BASE + 16}" text-anchor="middle" class="detail">{name}</text>'
                  for x, name in zip(CENTRES, CLASSES)]
    return parts


def _stacked(lower: tuple[int, ...], upper: tuple[int, ...], colours: tuple[str, str], names: tuple[str, str],
             detail, label: str) -> str:
    """Three columns of two segments each."""
    scale, width = 2.4, 44
    parts = _axis()
    for x, cls, low, high in zip(CENTRES, CLASSES, lower, upper):
        left = x - width / 2
        low_h, high_h = low * scale, high * scale
        parts.append(_column(left, BASE - low_h, width, low_h, colours[0], f"{cls}: {low} m3fub {names[0]}", False))
        # A 2 px gap of the surface between the segments.
        parts.append(_column(left, BASE - low_h - high_h, width, high_h - 2, colours[1],
                             f"{cls}: {high} m3fub {names[1]}", True))
        top = BASE - low_h - high_h
        parts.append(f'<text x="{x}" y="{top - 19:.1f}" text-anchor="middle" class="name">{low + high}'
                     f'<tspan x="{x}" dy="1.15em" class="detail">{escape(detail(low, high))}</tspan></text>')
    return _svg(parts, label)


def _reported() -> str:
    earlier = tuple(h - s for h, s in zip(HARVESTED, STOCK))
    return _stacked(STOCK, earlier, (COLOURS["S1"], DELIVERED), ("kvar i lagret", "levererat tidigare"),
                    lambda low, _high: f"{low} kvar", "Skördat hittills per klass, och vad som är kvar i lagret")


def _measured() -> str:
    """The stock against what is measured in: the load is longer than the stock, and the rest is beyond it."""
    scale, left, height = 3.0, 62, 24
    stock, load = sum(STOCK) * scale, LOAD * scale
    end = left + stock
    rows = {"Lager": 58, "Inmätt": 108}
    parts = [f'<text x="{left - 8}" y="{y + 16}" text-anchor="end" class="detail">{name}</text>'
             for name, y in rows.items()]

    def bar(x: float, y: float, width: float, colour: str, title: str, end_: bool) -> str:
        if not end_:
            return (f'<rect x="{x:.1f}" y="{y}" width="{width:.1f}" height="{height}" fill="{colour}">'
                    f"<title>{escape(title)}</title></rect>")
        return (f'<path d="M{x:.1f},{y} H{x + width - 4:.1f} Q{x + width:.1f},{y} {x + width:.1f},{y + 4} '
                f'V{y + height - 4} Q{x + width:.1f},{y + height} {x + width - 4:.1f},{y + height} H{x:.1f} Z" '
                f'fill="{colour}"><title>{escape(title)}</title></path>')

    parts.append(bar(left, rows["Lager"], stock, COLOURS["S1"], f"Kvar i lagret: {sum(STOCK)} m3fub", True))
    parts.append(f'<text x="{end + 6:.1f}" y="{rows["Lager"] + 16}" class="name">{sum(STOCK)}</text>')
    parts.append(bar(left, rows["Inmätt"], stock - 1, COLOURS["S1"], f"Ryms i lagret: {sum(STOCK)} m3fub", False))
    parts.append(bar(end + 1, rows["Inmätt"], load - stock - 1, COLOURS["S2"], f"Utöver lagret: {BEYOND} m3fub", True))
    parts.append(f'<text x="{left + load + 6:.1f}" y="{rows["Inmätt"] + 16}" class="name">{LOAD}</text>')
    # Where the stock ends.
    parts.append(f'<line x1="{end:.1f}" y1="{rows["Lager"] - 8}" x2="{end:.1f}" y2="{rows["Inmätt"] + height + 8}" '
                 'stroke="#8c96a3" stroke-dasharray="3 3"/>')
    below = rows["Inmätt"] + height + 22
    parts.append(f'<text x="{left + stock / 2:.1f}" y="{below}" text-anchor="middle" class="detail">'
                 f"{sum(STOCK)} ur lagret</text>")
    parts.append(f'<text x="{end + (load - stock) / 2 + 12:.1f}" y="{below}" text-anchor="middle" class="detail">'
                 f"{BEYOND} utöver</text>")
    return _svg(parts, "Lagret mot det som mäts in under månaden")


# The whole harvest so far is context, neutral; what is estimated from it has the colour of its source.
SO_FAR = ("#8c96a3", "0.22")
ESTIMATED = (COLOURS["S2"], "0.28")
HARVEST_TITLE = "Hela skörden hittills, andel"
BEYOND_TITLE = f"De {BEYOND} utöver lagret, m3fub"


def _cell(x: float, y: float, width: float, height: float, tint: tuple[str, str], shown: str, title: str) -> str:
    """A tinted cell with its number; no halo on a tint."""
    return (f'<rect x="{x:.1f}" y="{y}" width="{width:.1f}" height="{height}" rx="2" fill="{tint[0]}" '
            f'fill-opacity="{tint[1]}"><title>{escape(title)}</title></rect>'
            f'<text x="{x + width / 2:.1f}" y="{y + height / 2 + 4:.0f}" text-anchor="middle" style="stroke:none">'
            f"{escape(shown)}</text>")


def _arrow(x: float, top: int, bottom: int) -> str:
    return (f'<path d="M{x:.1f},{top} V{bottom} M{x - 3:.1f},{bottom - 4} L{x:.1f},{bottom} L{x + 3:.1f},{bottom - 4}" '
            'fill="none" stroke="#8c96a3"/>')


def _cells() -> str:
    """The whole harvest so far and the volume beyond the stock, one row per length class and one column per diameter
    class: each cell's share of the whole harvest, and what the cell gets of the volume beyond the stock."""
    left, width, height = 52, 58, 20
    centres = [left + i * (width + 2) + width / 2 for i in range(len(CLASSES))]
    whole = sum(HARVESTED)
    parts = [f'<text x="14" y="12" class="name">{HARVEST_TITLE}</text>']
    parts += [f'<text x="{x:.0f}" y="28" text-anchor="middle" class="detail">{name}</text>'
              for x, name in zip(centres, CLASSES)]

    def grid(top: int, rows, tint: tuple[str, str], shown, told) -> None:
        for r, (length, row) in enumerate(zip(LENGTHS, rows)):
            y = top + r * (height + 2)
            parts.append(f'<text x="{left - 6}" y="{y + 14}" text-anchor="end" class="detail">{length} dm</text>')
            parts.extend(_cell(x - width / 2, y, width, height, tint, shown(value), f"{cls}, {length} dm: {told(value)}")
                         for x, cls, value in zip(centres, CLASSES, row))

    grid(34, HARVESTED_CELLS, SO_FAR, lambda v: f"{100 * v // whole} %",
         lambda v: f"{100 * v // whole} % av hela skörden hittills")
    parts += [_arrow(x, 80, 92) for x in centres]
    parts.append(f'<text x="14" y="108" class="name">{BEYOND_TITLE}</text>')
    grid(114, ESTIMATE_CELLS, ESTIMATED, _tenth, lambda v: f"{_tenth(v)} m3fub som egen skörd i snitt")
    parts.append(f'<text x="{left - 6}" y="174" text-anchor="end" class="detail">Summa</text>')
    parts += [f'<text x="{x:.0f}" y="174" text-anchor="middle" class="name">{value}</text>'
              for x, value in zip(centres, ESTIMATE)]
    return _svg(parts, "Skördens andel per diameter- och längdklass, och volymen utöver lagret fördelad på samma klasser")


def steps() -> list[Step]:
    figures = (_reported(), _measured(), _cells())
    return [Step(title, text, figure) for (title, text), figure in zip(_words(), figures)]


# How many contract objects the month's table shows, largest volume beyond the stock first.
SHOWN = 5


def this_month(b: Bilaga) -> tuple[str, list[dict[str, str]]]:
    """What the mill's own month holds beyond the stock, in a sentence, and the contract objects that brought most of it."""
    beyond = float(b.volumes["S2"].sum()) if len(b.volumes) else 0.0
    if beyond <= 0.0005:
        return (f"Den här månaden ryms all volym till {b.mill} i avtalsobjektens eget lager, så inget är fördelat som "
                "egen skörd i snitt."), []
    rows = b.rows[b.rows["S2"] > 0.0005].sort_values("S2", ascending=False)
    count = rows[AO].nunique()
    lead = (f"Den här månaden levererades {sv(beyond)} m3fub utöver lagret till {b.mill}, {percent(beyond, b.total)} av "
            f"matrisen, från {plural(count)}. Den är fördelad som varje avtalsobjekts hela skörd hittills.")
    if len(rows) > SHOWN:
        lead += f" Tabellen visar de {SHOWN} rader som har mest volym utöver lagret."
    table = [{"Avtalsobjekt": str(r[AO]), "Sortiment": str(r[SORT]),
              "Skördat hittills, m3fub": volume_text(float(r[PROGRESS[0]])),
              "Till sågverket i månaden, m3fub": sv(float(r[VOL])),
              f"varav {NAMES['S1'].lower()}": volume_text(float(r["S1"])),
              f"varav {NAMES['S2'].lower()}": volume_text(float(r["S2"]))}
             for _, r in rows.head(SHOWN).iterrows()]
    return lead, table
