"""Writing the month's results to disk."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .appendix import AppendixLayout, appendix_markdown, appendix_rows, appendix_workbook
from .appendix import markdown_table as _markdown_table
from .core.allocate import CERTAINTY_TIERS, TIER_NAMES
from .config import Config
from .core.pipeline import MonthOutput
from .bilaga import build
from .bilaga_html import render
from .bilaga_excel import add_sheets
from .workorders import Facts, work_orders
from .schema import DEST, PRODUCED, SORT

_ROUNDING = 3


def slug(sortiment: str) -> str:
    return re.sub(r"[^\w.-]+", "_", sortiment)


def _long_matrices(output: MonthOutput) -> pd.DataFrame:
    frames = []
    for m in output.matrices.values():
        tables = {
            "levererat_m3fub": m.delivered,
            **{f"levererat_{t}_m3fub": m.by_tier[t] for t in CERTAINTY_TIERS},
            "andel": m.share,
            "skordat_ra_m3fub": m.harvested,
            "lager_utgaende_m3fub": m.closing_stock,
            "kreditering_m3fub": m.credits,
        }
        combined = pd.DataFrame(
            {name: m.frame(values).stack(future_stack=True) for name, values in tables.items() if values is not None}
        ).reset_index()
        combined.insert(0, SORT, m.sortiment)
        combined.insert(0, DEST, m.destination)
        frames.append(combined)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _write_matrices(output: MonthOutput, target: Path) -> None:
    for m in output.matrices.values():
        folder = target / slug(m.destination) / slug(m.sortiment)
        folder.mkdir(parents=True, exist_ok=True)
        tables = {
            "levererat": m.delivered,
            "andel": m.share,
            "skordat_ra": m.harvested,
            "lager_utgaende": m.closing_stock,
            "kreditering": m.credits,
            **{f"levererat_{t}": m.by_tier[t] for t in CERTAINTY_TIERS},
        }
        for name, values in tables.items():
            if values is None:
                continue
            m.frame(values).round(4 if name == "andel" else _ROUNDING).to_csv(folder / f"{name}.csv")


def _summary_markdown(output: MonthOutput) -> str:
    step = output.step
    rows = []
    for m in output.matrices.values():
        delivered = m.delivered.sum()
        tier_share = {t: m.by_tier[t].sum() / delivered if delivered > 0 else 0.0 for t in CERTAINTY_TIERS}
        rows.append(
            {
                DEST: m.destination,
                SORT: m.sortiment,
                "levererat_m3fub": f"{delivered:.1f}",
                "skordat_ra_m3fub": f"{m.harvested.sum():.1f}",
                "utgaende_lager_m3fub": f"{m.closing_stock.sum():.1f}",
                **{t: f"{tier_share[t]:.1%}" for t in CERTAINTY_TIERS},
            }
        )
    lines = [f"# Sammanfattning {step.period}", ""]
    if rows:
        lines += [_markdown_table(pd.DataFrame(rows)), ""]
    lines += [f"- {t}: {name}" for t, name in TIER_NAMES.items()]
    written_off = step.reconciliation["avskrivet"].sum() if len(step.reconciliation) else 0.0
    lines += ["", f"Avskrivet lager på avslutade avtalsobjekt: {written_off:.1f} m3fub.", ""]
    return "\n".join([*lines, ""])


# Where --utvecklare puts what the appendices were built from, inside the month's output.
DEVELOPER_DIR = "utveckling"


def _write_developer(output: MonthOutput, target: Path, layout: AppendixLayout) -> None:
    """Every matrix, the distribution per contract object and the appendix as text: for following a number to its source."""
    target.mkdir(parents=True, exist_ok=True)
    _write_matrices(output, target / "matriser")
    _long_matrices(output).round(4).to_csv(target / "matriser_lang.csv", index=False)
    output.step.allocation.round(6).to_csv(target / "leverans_ao_lang.csv", index=False)
    output.step.credits.round(6).to_csv(target / "krediteringar_ao_lang.csv", index=False)
    # The stock is the produced assortment's; the file has always called it handelssortiment.
    output.step.reconciliation.rename(columns={PRODUCED: SORT}).round(4).to_csv(target / "avstamning_ao.csv", index=False)
    # How earlier months' estimates differed from the harvester data that arrived this month. Nothing is invoiced.
    output.step.corrections.round(6).to_csv(target / "uppskattning_mot_skordardata.csv", index=False)
    appendices = target / "bilagor"
    appendices.mkdir(exist_ok=True)
    for destination in sorted(set(output.invoice[DEST])):
        name = slug(destination)
        (appendices / f"{name}.md").write_text(appendix_markdown(output, destination, layout), encoding="utf-8")
        appendix_rows(output, destination).round(4).to_csv(appendices / f"{name}.csv", index=False)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_month(output: MonthOutput, out_dir: Path, cfg: Config, inputs: dict[str, Path],
                layout: AppendixLayout = AppendixLayout(), harvest: pd.DataFrame | None = None,
                facts: Facts | None = None, developer: bool = False) -> None:
    """The month's appendices and the files a person follows up with; with `developer`, also what they were built from."""
    out_dir.mkdir(parents=True, exist_ok=True)
    output.invoice.round(4).to_csv(out_dir / "faktura_rader.csv", index=False)
    appendices = out_dir / "bilagor"
    appendices.mkdir(exist_ok=True)
    for destination in sorted(set(output.invoice[DEST])):
        name = slug(destination)
        # What the appendix says is built once; the page and the workbook each draw it.
        content = build(output, destination, layout, facts)
        (appendices / f"{name}.html").write_text(render(content), encoding="utf-8")
        appendix_workbook(appendices / f"{name}.xlsx", output, destination, layout, harvest,
                          extra=lambda book, n, content=content: add_sheets(book, content, n))
    (out_dir / "sammanfattning.md").write_text(_summary_markdown(output), encoding="utf-8")
    work_orders(output).to_csv(out_dir / "avtalsobjekt.csv", index=False, float_format="%.3f")
    if developer:
        _write_developer(output, out_dir / DEVELOPER_DIR, layout)

    manifest = {
        "period": output.step.period,
        "config": asdict(cfg),
        "bilaga": asdict(layout),
        "indata": {name: {"fil": str(path), "sha256": _sha256(path)} for name, path in inputs.items()},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
