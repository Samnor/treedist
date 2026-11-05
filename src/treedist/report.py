"""Writing the month's results to disk."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from .appendix import AppendixLayout, appendix_html, appendix_markdown, appendix_rows, appendix_workbook
from .appendix import markdown_table as _markdown_table
from .core.allocate import CERTAINTY_TIERS, TIER_NAMES
from .config import Config
from .core.invoice import invoice_total_kr
from .core.pipeline import MonthOutput
from .schema import DEST, DIA, LEN, SORT, VOL, sorted_groups

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
            "std_m3fub": m.std,
            "std_fordelning_m3fub": m.std_distribution,
            "p05_m3fub": m.p05,
            "p95_m3fub": m.p95,
            "skordat_ra_m3fub": m.harvested,
            "lager_utgaende_m3fub": m.closing_stock,
            "korrigering_m3fub": m.corrections,
            "pris_kr_m3fub": m.price_kr if output.priced else None,
            "varde_kr": m.value_kr if output.priced else None,
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
            "std": m.std,
            "std_fordelning": m.std_distribution,
            "p05": m.p05,
            "p95": m.p95,
            "skordat_ra": m.harvested,
            "lager_utgaende": m.closing_stock,
            "korrigering": m.corrections,
            "pris": m.price_kr if output.priced else None,
            "varde": m.value_kr if output.priced else None,
            **{f"levererat_{t}": m.by_tier[t] for t in CERTAINTY_TIERS},
        }
        for name, values in tables.items():
            if values is None:
                continue
            m.frame(values).round(4 if name == "andel" else _ROUNDING).to_csv(folder / f"{name}.csv")


def value_interval(output: MonthOutput, destination: str) -> tuple[float, float] | None:
    """90 % interval of a destination's delivered value with volumes as measured."""
    draws = [m.value_draws_fixed for m in output.matrices.values() if m.destination == destination]
    if not draws or any(d is None for d in draws):
        return None
    low, high = np.quantile(np.sum(draws, axis=0), [0.05, 0.95])
    return float(low), float(high)


def warnings_for(output: MonthOutput, destination: str | None = None) -> list[str]:
    notes = []
    invoice = output.invoice
    allocation = output.step.allocation
    if destination is not None:
        invoice = invoice[invoice[DEST] == destination]
        allocation = allocation[allocation[DEST] == destination]
    unpriced = invoice[~invoice["prissatt"].astype(bool)] if len(invoice) and output.priced else invoice.iloc[0:0]
    if len(unpriced):
        volume = unpriced["volym_m3fub"].sum()
        notes.append(f"{volume:.3f} m3fub saknar pris och är inte debiterat; komplettera prislistan eller invänta skördardata.")
    tiers = allocation.groupby("sakerhetsklass")[VOL].sum()
    for tier in ("S3", "S4"):
        if tiers.get(tier, 0) > 0:
            notes.append(f"{tiers[tier]:.3f} m3fub är {tier} ({TIER_NAMES[tier]}); fördelningen är preliminär.")
    return notes


def _invoice_markdown(output: MonthOutput, destination: str) -> str:
    invoice = output.invoice[output.invoice[DEST] == destination]
    lines = [f"# Fakturaunderlag {output.step.period}, {destination}", ""]

    shown = invoice.assign(
        volym_m3fub=invoice["volym_m3fub"].map(lambda v: f"{v:.3f}"),
        pris_kr=invoice["pris_kr"].map(lambda v: "saknas" if pd.isna(v) else f"{v:.2f}"),
        belopp_kr=invoice["belopp_kr"].map(lambda v: f"{v:.2f}"),
        andel_S1=invoice["andel_S1"].map(lambda v: "" if pd.isna(v) else f"{v:.0%}"),
    )[["radtyp", SORT, DIA, LEN, "volym_m3fub", "pris_kr", "belopp_kr", "andel_S1"]]
    lines += [_markdown_table(shown), ""]

    delivered = invoice[invoice["radtyp"] == "LEVERANS"]
    corrected = invoice[invoice["radtyp"] == "KORRIGERING"]
    credited = invoice[invoice["radtyp"] == "KREDITERING"]
    lines.append(f"- Levererad volym: {delivered['volym_m3fub'].sum():.3f} m3fub")
    lines.append(f"- Leveransbelopp: {delivered['belopp_kr'].sum():.2f} kr")
    if len(credited):
        lines.append(
            f"- Kreditering av lass från tidigare månader: {credited['volym_m3fub'].sum():.3f} m3fub, "
            f"{credited['belopp_kr'].sum():.2f} kr"
        )
    if len(corrected):
        lines.append(f"- Korrigering av tidigare månader: {corrected['belopp_kr'].sum():.2f} kr")
    lines.append(f"- **Att fakturera, exkl. moms: {invoice_total_kr(invoice):.2f} kr**")
    interval = value_interval(output, destination)
    if interval:
        lines.append(f"- 90 % intervall för leveransens värde vid mätt volym: {interval[0]:.0f}–{interval[1]:.0f} kr")
    lines += ["", *[f"- OBS: {note}" for note in warnings_for(output, destination)], ""]
    return "\n".join(lines)


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
    lines += ["", f"Avskrivet lager på avslutade arbetsordrar: {written_off:.1f} m3fub.", ""]
    if not output.priced:
        lines += ["Ingen prislista: matriser och bilagor per mottagare, inget fakturaunderlag.", ""]
    lines += [f"- OBS: {note}" for note in warnings_for(output)]
    return "\n".join([*lines, ""])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_month(output: MonthOutput, out_dir: Path, cfg: Config, inputs: dict[str, Path],
                layout: AppendixLayout = AppendixLayout(), harvest: pd.DataFrame | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_matrices(output, out_dir / "matriser")
    _long_matrices(output).round(4).to_csv(out_dir / "matriser_lang.csv", index=False)
    output.step.allocation.round(6).to_csv(out_dir / "leverans_ao_lang.csv", index=False)
    output.step.corrections.round(6).to_csv(out_dir / "korrigeringar_ao_lang.csv", index=False)
    output.step.credits.round(6).to_csv(out_dir / "krediteringar_ao_lang.csv", index=False)
    output.step.reconciliation.round(4).to_csv(out_dir / "avstamning_ao.csv", index=False)
    output.invoice.round(4).to_csv(out_dir / "faktura_rader.csv", index=False)
    appendices = out_dir / "bilagor"
    appendices.mkdir(exist_ok=True)
    for destination in sorted(set(output.invoice[DEST])):
        name = slug(destination)
        (appendices / f"{name}.md").write_text(appendix_markdown(output, destination, layout), encoding="utf-8")
        (appendices / f"{name}.html").write_text(appendix_html(output, destination, layout), encoding="utf-8")
        appendix_rows(output, destination).round(4).to_csv(appendices / f"{name}.csv", index=False)
        appendix_workbook(appendices / f"{name}.xlsx", output, destination, layout, harvest)
    if output.priced:
        invoices = out_dir / "fakturor"
        invoices.mkdir(exist_ok=True)
        for destination in sorted(set(output.invoice[DEST])):
            (invoices / f"{slug(destination)}.md").write_text(_invoice_markdown(output, destination), encoding="utf-8")
    (out_dir / "sammanfattning.md").write_text(_summary_markdown(output), encoding="utf-8")

    manifest = {
        "period": output.step.period,
        "config": asdict(cfg),
        "bilaga": asdict(layout),
        "indata": {name: {"fil": str(path), "sha256": _sha256(path)} for name, path in inputs.items()},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
