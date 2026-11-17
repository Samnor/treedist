"""The Sankey diagram on the appendix's page: from the mill's assortments to where the distribution came from.

It is plain SVG with no script or web font, so it opens and prints on a machine without internet.
"""

from __future__ import annotations

from html import escape

import pandas as pd

from .bilaga import NAMES, percent, sv
from .core.allocate import CERTAINTY_TIERS


# Categorical colours by identity, checked for colour blindness; text never wears them.
COLOURS = {"S1": "#2a78d6", "S2": "#eb6834", "mill": "#52514e", "outside": "#a3a19a"}


WIDTH, HEIGHT, NODE, GAP = 1000, 300, 12, 14


X = {0: 190, 1: 720}

# The height a node's two lines of label take.
LABEL = 34


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


def sankey_svg(volumes: pd.DataFrame) -> str:
    """The diagram: the mill's assortments → where their distribution on classes comes from."""
    total = float(volumes.to_numpy().sum())
    if total <= 0:
        return "<p>Ingen levererad volym denna månad.</p>"
    mills = volumes.sum(axis=1).sort_values(ascending=False)
    mills = mills[mills > 0]
    sources = {t: float(volumes[t].sum()) for t in CERTAINTY_TIERS if volumes[t].sum() > 0}

    gaps = GAP * max(len(mills), len(sources)) - GAP
    scale = (HEIGHT - 40 - gaps) / total
    left, right = _stack(dict(mills), scale), _stack(sources, scale)

    parts = []
    out_y = {name: y for name, (y, _) in left.items()}
    in_y = {name: y for name, (y, _) in right.items()}
    for mill in mills.index:
        for tier in sources:
            volume = float(volumes.at[mill, tier])
            if volume <= 0:
                continue
            thickness = volume * scale
            parts.append(f'<path d="{_band(X[0] + NODE, out_y[mill], X[1], in_y[tier], thickness)}" '
                         f'fill="{COLOURS[tier]}" fill-opacity="0.3"><title>{escape(str(mill))} → '
                         f'{escape(NAMES[tier])}: {sv(volume)} m3fub</title></path>')
            out_y[mill] += thickness
            in_y[tier] += thickness

    def node(x: float, y: float, height: float, colour: str, title: str) -> str:
        return (f'<rect x="{x}" y="{y:.1f}" width="{NODE}" height="{max(height, 1.5):.1f}" rx="2" fill="{colour}">'
                f"<title>{escape(title)}</title></rect>")

    def label(x: float, y: float, anchor: str, name: str, detail: str) -> str:
        return (f'<text x="{x}" y="{y:.1f}" text-anchor="{anchor}" class="name">{escape(name)}'
                f'<tspan x="{x}" dy="1.25em" class="detail">{escape(detail)}</tspan></text>')

    columns = [
        (X[0], "end", left, {m: (str(m), float(mills[m]), COLOURS["mill"]) for m in left}),
        (X[1], "start", right, {t: (NAMES[t], sources[t], COLOURS[t]) for t in right}),
    ]
    for x, anchor, placed, texts in columns:
        # Labels sit level with their node, but never on top of the label above.
        gap = 34
        centres = _spread([y + height / 2 for y, height in placed.values()], gap, HEIGHT + 30 - gap / 2)
        for (name, (y, height)), centre in zip(placed.items(), centres):
            text, volume, colour = texts[name]
            parts.append(node(x, y, height, colour, f"{text}: {sv(volume)} m3fub"))
            detail = f"{sv(volume)} m3fub" + (f" · {percent(volume, total)}" if anchor == "start" else "")
            parts.append(label(x - 8 if anchor == "end" else x + NODE + 8, centre - 4, anchor, text, detail))
    return (f'<svg viewBox="0 0 {WIDTH} {HEIGHT + 30}" role="img" aria-label="Var volymens fördelning kommer ifrån">'
            + "".join(parts) + "</svg>")


def flow_svg(stages: list[list[tuple[str, str, str]]], links: list[dict[tuple[str, str], tuple[float, str]]],
             aria: str) -> str:
    """A diagram of two or more columns. `stages` holds each column's nodes from the top as (key, text, colour), and
    `links` for each gap {(from, to): (m3fub, band colour)}. The last column also shows each node's share."""
    def size(stage: int, key: str) -> float:
        gap, end = (links[0], 0) if stage == 0 else (links[stage - 1], 1)
        return sum(volume for pair, (volume, _) in gap.items() if pair[end] == key)

    sizes = [{key: size(i, key) for key, _, _ in nodes} for i, nodes in enumerate(stages)]
    total = sum(sizes[0].values())
    if total <= 0:
        return "<p>Ingen inmätt volym denna månad.</p>"
    most = max(len(nodes) for nodes in stages)
    scale = (HEIGHT - 40 - GAP * (most - 1)) / total
    xs = [190 + i * (720 - 190) / (len(stages) - 1) for i in range(len(stages))]
    # A thin node still takes a label's height, so that every label sits level with its own node.
    placed, height = [], HEIGHT
    for column in sizes:
        nodes, y = {}, 20.0
        for key, volume in column.items():
            nodes[key] = [y, volume * scale]
            y += max(volume * scale + GAP, LABEL)
        placed.append(nodes)
        height = max(height, y - GAP + 20)

    parts = []
    for i, gap in enumerate(links):
        out_y = {key: y for key, (y, _) in placed[i].items()}
        in_y = {key: y for key, (y, _) in placed[i + 1].items()}
        names = [{key: text for key, text, _ in nodes} for nodes in stages[i:i + 2]]
        for start in placed[i]:
            for end in placed[i + 1]:
                volume, colour = gap.get((start, end), (0.0, ""))
                if volume <= 0:
                    continue
                thickness = volume * scale
                parts.append(f'<path d="{_band(xs[i] + NODE, out_y[start], xs[i + 1], in_y[end], thickness)}" '
                             f'fill="{colour}" fill-opacity="0.3"><title>{escape(names[0][start])} → '
                             f'{escape(names[1][end])}: {sv(volume)} m3fub</title></path>')
                out_y[start] += thickness
                in_y[end] += thickness

    for i, nodes in enumerate(stages):
        first, last = i == 0, i == len(stages) - 1
        centres = _spread([y + h / 2 for y, h in placed[i].values()], LABEL, height + 30 - LABEL / 2)
        for (key, text, colour), centre in zip(nodes, centres):
            y, h = placed[i][key]
            volume = sizes[i][key]
            parts.append(f'<rect x="{xs[i]:.0f}" y="{y:.1f}" width="{NODE}" height="{max(h, 1.5):.1f}" rx="2" '
                         f'fill="{colour}"><title>{escape(text)}: {sv(volume)} m3fub</title></rect>')
            x, anchor = (xs[i] - 8, "end") if first else (xs[i] + NODE + 8, "start")
            detail = f"{sv(volume)} m3fub" + (f" · {percent(volume, total)}" if last else "")
            parts.append(f'<text x="{x:.0f}" y="{centre - 4:.1f}" text-anchor="{anchor}" class="name">{escape(text)}'
                         f'<tspan x="{x:.0f}" dy="1.25em" class="detail">{escape(detail)}</tspan></text>')
    return f'<svg viewBox="0 0 {WIDTH} {height + 30}" role="img" aria-label="{escape(aria)}">' + "".join(parts) + "</svg>"
