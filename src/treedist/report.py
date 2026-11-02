"""Writing the month's results to disk."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from .allocate import CERTAINTY_TIERS, TIER_NAMES
from .config import Config
from .invoice import invoice_total_kr
from .pipeline import MonthOutput
from .schema import DIA, LEN, SORT, VOL

_ROUNDING = 3


def _slug(sortiment: str) -> str:
    return re.sub(r"[^\w.-]+", "_", sortiment)


def _long_matrices(output: MonthOutput) -> pd.DataFrame:
    frames = []
    for sortiment, m in output.matrices.items():
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
            "pris_kr_m3fub": m.price_kr,
            "varde_kr": m.value_kr,
        }
        combined = pd.DataFrame(
            {name: m.frame(values).stack(future_stack=True) for name, values in tables.items()}
        ).reset_index()
        combined.insert(0, SORT, sortiment)
        frames.append(combined)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _write_matrices(output: MonthOutput, target: Path) -> None:
    for sortiment, m in output.matrices.items():
        folder = target / _slug(sortiment)
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
            "pris": m.price_kr,
            "varde": m.value_kr,
            **{f"levererat_{t}": m.by_tier[t] for t in CERTAINTY_TIERS},
        }
        for name, values in tables.items():
            m.frame(values).round(4 if name == "andel" else _ROUNDING).to_csv(folder / f"{name}.csv")


def value_interval(output: MonthOutput) -> tuple[float, float] | None:
    """90 % interval of the month's delivered value with volumes as measured."""
    draws = [m.value_draws_fixed for m in output.matrices.values()]
    if not draws:
        return None
    low, high = np.quantile(np.sum(draws, axis=0), [0.05, 0.95])
    return float(low), float(high)


def warnings_for(output: MonthOutput) -> list[str]:
    notes = []
    invoice = output.invoice
    unpriced = invoice[~invoice["prissatt"].astype(bool)] if len(invoice) else invoice
    if len(unpriced):
        volume = unpriced["volym_m3fub"].sum()
        notes.append(f"{volume:.3f} m3fub saknar pris och är inte debiterat; komplettera prislistan eller invänta skördardata.")
    tiers = output.step.allocation.groupby("sakerhetsklass")[VOL].sum()
    for tier in ("S3", "S4"):
        if tiers.get(tier, 0) > 0:
            notes.append(f"{tiers[tier]:.3f} m3fub är {tier} ({TIER_NAMES[tier]}); fördelningen är preliminär.")
    return notes


def _markdown_table(df: pd.DataFrame) -> str:
    header = "| " + " | ".join(df.columns) + " |"
    rule = "|" + "---|" * len(df.columns)
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, rule, *rows])


def _invoice_markdown(output: MonthOutput) -> str:
    invoice = output.invoice
    lines = [f"# Fakturaunderlag {output.step.period}", ""]
    if invoice.empty:
        return "\n".join([*lines, "Inga leveranser under perioden.", ""])

    shown = invoice.assign(
        volym_m3fub=invoice["volym_m3fub"].map(lambda v: f"{v:.3f}"),
        pris_kr=invoice["pris_kr"].map(lambda v: "saknas" if pd.isna(v) else f"{v:.2f}"),
        belopp_kr=invoice["belopp_kr"].map(lambda v: f"{v:.2f}"),
        andel_S1=invoice["andel_S1"].map(lambda v: "" if pd.isna(v) else f"{v:.0%}"),
    )[["radtyp", SORT, DIA, LEN, "volym_m3fub", "pris_kr", "belopp_kr", "andel_S1"]]
    lines += [_markdown_table(shown), ""]

    delivered = invoice[invoice["radtyp"] == "LEVERANS"]
    corrected = invoice[invoice["radtyp"] == "KORRIGERING"]
    lines.append(f"- Levererad volym: {delivered['volym_m3fub'].sum():.3f} m3fub")
    lines.append(f"- Leveransbelopp: {delivered['belopp_kr'].sum():.2f} kr")
    if len(corrected):
        lines.append(f"- Korrigering av tidigare månader: {corrected['belopp_kr'].sum():.2f} kr")
    lines.append(f"- **Att fakturera, exkl. moms: {invoice_total_kr(invoice):.2f} kr**")
    interval = value_interval(output)
    if interval:
        lines.append(f"- 90 % intervall för leveransens värde vid mätt volym: {interval[0]:.0f}–{interval[1]:.0f} kr")
    lines += ["", *[f"- OBS: {note}" for note in warnings_for(output)], ""]
    return "\n".join(lines)


def _summary_markdown(output: MonthOutput) -> str:
    step = output.step
    rows = []
    for sortiment, m in output.matrices.items():
        delivered = m.delivered.sum()
        tier_share = {t: m.by_tier[t].sum() / delivered if delivered > 0 else 0.0 for t in CERTAINTY_TIERS}
        rows.append(
            {
                SORT: sortiment,
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
    lines += [f"- OBS: {note}" for note in warnings_for(output)]
    return "\n".join([*lines, ""])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_month(output: MonthOutput, out_dir: Path, cfg: Config, inputs: dict[str, Path]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_matrices(output, out_dir / "matriser")
    _long_matrices(output).round(4).to_csv(out_dir / "matriser_lang.csv", index=False)
    output.step.allocation.round(6).to_csv(out_dir / "leverans_ao_lang.csv", index=False)
    output.step.corrections.round(6).to_csv(out_dir / "korrigeringar_ao_lang.csv", index=False)
    output.step.reconciliation.round(4).to_csv(out_dir / "avstamning_ao.csv", index=False)
    output.invoice.round(4).to_csv(out_dir / "faktura_rader.csv", index=False)
    (out_dir / "faktura.md").write_text(_invoice_markdown(output), encoding="utf-8")
    (out_dir / "sammanfattning.md").write_text(_summary_markdown(output), encoding="utf-8")

    manifest = {
        "period": output.step.period,
        "config": asdict(cfg),
        "indata": {name: {"fil": str(path), "sha256": _sha256(path)} for name, path in inputs.items()},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
