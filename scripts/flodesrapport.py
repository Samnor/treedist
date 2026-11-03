"""Write an HTML report of the monthly flow, one step at a time, for inspection.

Runs the months in order from an empty ledger and draws the flow as a graph:
the inputs, the ledger, the draw, the certainty classes and the outputs, each
with the month's numbers. Click a step to see its breakdown. If the data
directory has facit files, as the demo and `treedist simulate` do, the
matrices are scored against them.

    uv run python scripts/flodesrapport.py
    uv run python scripts/flodesrapport.py --data examples/egen --out out/flode.html
    uv run python scripts/flodesrapport.py --kalla kallor/system/kalla.toml --perioder 2026-01 2026-02

The default writes docs/flodesrapport.html from the demo, so the report in the
repository follows the method; rerun it after a change to the method.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from treedist import adapters
from treedist.config import Config, load_config
from treedist.core.allocate import CERTAINTY_TIERS, TIER_NAMES
from treedist.core.invoice import invoice_total_kr
from treedist.core.ledger import Ledger
from treedist.core.pipeline import MonthOutput, run_month
from treedist.dev.backtest import _score
from treedist.report import value_interval
from treedist.schema import AO, BRUTTO, DEST, DIA, LEN, PRODUCED, SORT, TIER, VINTAGE, VOL

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "climb" / "logg.jsonl"
DETAIL_ROWS = 40

EXPLAINED = {
    "skord": "Skördarens produktionsrapport: volym per arbetsorder, sortiment, diameter- och längdklass. Den vet "
    "fördelningen men mäter vid avverkning, inte vid leverans.",
    "lev": "Inmätningen vid industri avgör hur mycket som levererades, brutto och netto. Den säger inget om "
    "dimensioner. En negativ rad vänder ett lass.",
    "ao": "Planerad destination och grupp per arbetsorder. Används för att välja givare när skördardata saknas (S3).",
    "pris": "Pris per sortiment och klass, eventuellt per destination. Används för matrisernas värde och fakturan.",
    "avsl": "Arbetsordrar som avslutats denna månad. Deras kvarvarande lager skrivs av och underskott blir slutgiltiga.",
    "kal": "Skördad volym multipliceras med (1 − harvester_bias)(1 − handling_loss) innan den läggs i lagret.",
    "vand": "Ett lass som vänds i samma månad nettas mot sitt lass. Ett som fakturerats en tidigare månad krediteras "
    "med den fördelning som fakturerades.",
    "ligg": "Liggaren bär oleverat virke och preliminärt fakturerat underskott från förra månaden.",
    "korr": "Har skördardata kommit in för virke som fakturerats preliminärt tas den volymen ur lagret, och "
    "skillnaden mot den preliminära fördelningen bokas som korrigering.",
    "drag": "Bruttovolymen tas ur lagret. Började leveranserna innan det sista i lagret var avverkat går det äldsta "
    "först, annars ger varje klass samma andel. Läget är rekonstruerat ur datumen för rapporten.",
    "brist": "Det som levererats utöver lagret. Fördelningen lånas: AO:ns historik (S2), andra arbetsordrar (S3) "
    "eller inget alls (S4). Volymen blir underskott i liggaren tills skördardata kommer.",
    "S1": "Fördelning från AO:ns eget skördarlager. Slutlig.",
    "S2": "Fördelning från AO:ns hela skördehistorik, när mer levererats än lagret räcker till. Preliminär.",
    "S3": "Viktat medelvärde av andra arbetsordrar i samma sortiment: ×16 samma destination, ×4 samma grupp, "
    "närhet i syskonsortimentets grovlek. Preliminär.",
    "S4": "Ingen fördelning alls, bokas på klassen OKÄND. Debiteras bara med uttrycklig prisregel.",
    "matr": "Matriser per destination och sortiment, diameter × längd. Summerar till nettovolymen hos destinationen.",
    "mc": "Monte Carlo slumpar om fördelningen (Dirichlet, bredd från design_effect) och volymens mätfel, och ger "
    "intervall per cell och för värdet.",
    "fakt": "Fakturans volym är alltid inmätningens; körningen stoppar annars. Leverans, kreditering och korrigering "
    "per destination.",
    "ligg_ut": "Det som går vidare till nästa månad: oleverat lager, preliminärt underskott och vad som skrivits av.",
    "facit": "Jämförelse med simulatorns facit: prisfel är skattat minus sant medelpris, viktat med volym. Naivt är "
    "att bara använda månadens skörd.",
}


def _git() -> str:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        dirty = subprocess.run(["git", "status", "--porcelain", "src"], cwd=ROOT, capture_output=True, text=True)
        return rev.stdout.strip() + ("+ändrad" if dirty.stdout.strip() else "")
    except OSError:
        return "okänd"


def _clean(value):
    """JSON-safe: numpy to Python, NaN to null, floats rounded."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        value = float(value)
        return None if math.isnan(value) or math.isinf(value) else round(value, 4)
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m-%d")
    return value


def _swedish(text: str) -> str:
    """Python's 1,234.5 and 12.5% as 1 234,5 and 12,5 %."""
    text = re.sub(r"(?<=\d),(?=\d{3})", " ", text)
    text = re.sub(r"(?<=\d)\.(?=\d)", ",", text)
    return re.sub(r"(?<=\d)%", " %", text)


def _table(frame: pd.DataFrame, limit: int = DETAIL_ROWS) -> dict:
    shown = frame.head(limit)
    return {
        "kolumner": [str(c) for c in shown.columns],
        "rader": [list(row) for row in shown.itertuples(index=False)],
        "utelamnade": max(len(frame) - limit, 0),
    }


def _files(data: Path | None, period: str) -> dict[str, Path | None] | None:
    if data is None:
        return None

    def optional(name: str) -> Path | None:
        path = data / name
        return path if path.exists() else None

    return {
        "skordning": data / f"skordning_{period}.csv",
        "leverans": data / f"leverans_{period}.csv",
        "prislista": data / "prislista.csv",
        "arbetsordrar": optional("arbetsordrar.csv"),
        "avslutade_ao": optional(f"avslutade_ao_{period}.csv"),
    }


def _truth(data: Path | None, period: str) -> pd.DataFrame | None:
    path = data / f"facit_{period}.csv" if data else None
    if path is None or not path.exists():
        return None
    return pd.read_csv(path, dtype={DIA: str, LEN: str, AO: str})


def _draw_modes(previous: Ledger, harvest: pd.DataFrame, deliveries: pd.DataFrame, rec: pd.DataFrame) -> pd.DataFrame:
    """Oldest first or pro rata per work order and assortment, as the draw decides it.

    The core does not report the mode, so it is rebuilt from the same dates: the
    first delivery against the last harvest date in the stock before the draw.
    """
    stock = pd.concat([previous.stock[[AO, SORT, VINTAGE]], harvest[[AO, SORT, VINTAGE]]])
    last_harvest = pd.to_datetime(stock.groupby([AO, SORT])[VINTAGE].max())
    produced = PRODUCED if PRODUCED in deliveries.columns else SORT
    positive = deliveries[deliveries[VOL] > 0]
    first_delivery = positive.groupby([AO, produced])["leveransdatum"].min().rename_axis([AO, SORT])

    drawn = rec[rec["tackning_s1"] > 0].assign(dragit=lambda r: r["tackning_s1"] * r["levererat_brutto"])
    drawn = drawn.set_index([AO, SORT])
    drawn["forsta_leverans"] = first_delivery.reindex(drawn.index)
    drawn["sista_avverkning"] = last_harvest.reindex(drawn.index)
    oldest = drawn["forsta_leverans"].dt.normalize() <= drawn["sista_avverkning"]
    drawn["lage"] = np.where(oldest, "äldst först", "pro rata")
    return drawn.reset_index()[[AO, SORT, "lage", "forsta_leverans", "sista_avverkning", "dragit"]]


def _by_dest_sort(frame: pd.DataFrame, value: str = VOL) -> pd.DataFrame:
    return frame.groupby([DEST, SORT], as_index=False)[value].sum().round(3)


def month_report(
    period: str, inputs: adapters.Inputs, output: MonthOutput, previous: Ledger, cfg: Config, truth: pd.DataFrame | None
) -> dict:
    step = output.step
    harvest, deliveries, invoice = inputs.harvest, inputs.deliveries, output.invoice
    rec, alloc = step.reconciliation, step.allocation
    nodes: dict[str, dict] = {}

    def node(key: str, lines: list[str], detail: pd.DataFrame | None = None, **numbers) -> None:
        nodes[key] = {"rader": [_swedish(line) for line in lines], "text": EXPLAINED[key],
                      "tabell": _table(detail) if detail is not None else None, "tal": numbers}

    raw = float(harvest[VOL].sum())
    node(
        "skord",
        [f"{len(harvest):,} rader · {harvest[AO].nunique()} AO", f"{raw:,.1f} m3fub"],
        harvest.groupby(SORT).agg(arbetsordrar=(AO, "nunique"), rader=(VOL, "size"), m3fub=(VOL, "sum")).round(1).reset_index(),
        volym=raw,
    )

    net, gross = float(deliveries[VOL].sum()), float(deliveries[BRUTTO].sum())
    negative = deliveries[deliveries[VOL] < 0]
    loads = deliveries["leverans_id"].nunique() if "leverans_id" in deliveries else len(deliveries)
    per_dest = deliveries.assign(negativa=deliveries[VOL] < 0).groupby([DEST, SORT]).agg(
        rader=(VOL, "size"), negativa=("negativa", "sum"), netto=(VOL, "sum"), brutto=(BRUTTO, "sum")
    ).round(3).reset_index()
    node("lev", [f"{loads} lass · {len(negative)} negativa", f"netto {net:,.0f} · brutto {gross:,.0f}"],
         per_dest, volym=net, brutto=gross)

    destinations = pd.Series(inputs.work_orders.destinations, name=DEST)
    groups = pd.Series(inputs.work_orders.groups, name="grupp")
    known = pd.concat([destinations, groups], axis=1)
    detail = known.groupby(DEST).agg(arbetsordrar=(DEST, "size"), grupper=("grupp", "nunique")).reset_index() if len(known) else None
    node("ao", [f"{len(destinations)} AO · {groups.nunique()} grupper", f"{destinations.nunique()} destinationer"], detail)

    rules = {s: len(r) for s, r in inputs.prices.rules.items()}
    node("pris", [f"{sum(rules.values())} regler", f"{len(rules)} sortiment"],
         pd.DataFrame({SORT: list(rules), "regler": list(rules.values())}))

    node("avsl", [f"{len(inputs.closed_aos)} arbetsordrar", "lager skrivs av"],
         pd.DataFrame({AO: sorted(inputs.closed_aos)}))

    calibrated = raw * cfg.calibration
    node("kal", [f"× {cfg.calibration:.4f}", f"{calibrated:,.1f} m3fub till lagret"],
         harvest.groupby(SORT)[VOL].sum().to_frame("skordat").assign(kalibrerat=lambda f: f["skordat"] * cfg.calibration)
         .round(2).reset_index(), volym=calibrated)

    reversed_net = -float(negative[VOL].sum())
    credited = -float(step.credits[VOL].sum()) if len(step.credits) else 0.0
    netted = abs(max(reversed_net - credited, 0.0))
    node("vand", [f"{netted:.1f} nettat i månaden", f"{credited:.1f} krediterat"],
         negative[[AO, SORT, DEST, "leveransdatum", VOL]].assign(leveransdatum=lambda f: f["leveransdatum"].dt.strftime("%Y-%m-%d")),
         nettat=netted, krediterat=credited)

    opening_stock, opening_deficit = float(previous.stock[VOL].sum()), float(previous.deficit[VOL].sum())
    stock_in = previous.stock.groupby(SORT)[VOL].sum().rename("lager")
    deficit_in = previous.deficit.groupby(SORT)[VOL].sum().rename("underskott")
    node("ligg", [f"lager {opening_stock:,.1f}", f"underskott {opening_deficit:,.1f}"],
         pd.concat([stock_in, deficit_in], axis=1).fillna(0.0).round(2).rename_axis(SORT).reset_index(),
         lager=opening_stock, underskott=opening_deficit)

    corrected = float(rec["korrigerat"].sum()) if len(rec) else 0.0
    correction_lines = invoice[invoice["radtyp"] == "KORRIGERING"]
    correction_kr = float(correction_lines["belopp_kr"].sum())
    node("korr", [f"{corrected:,.1f} m3fub avräknat", f"{correction_kr:+,.0f} kr"],
         correction_lines.groupby([DEST, SORT], as_index=False).agg(rader=("belopp_kr", "size"), belopp_kr=("belopp_kr", "sum")).round(2),
         volym=corrected, kr=correction_kr)

    modes = _draw_modes(previous, harvest, deliveries, rec) if len(rec) else pd.DataFrame(columns=["lage", "dragit"])
    by_mode = modes.groupby("lage")["dragit"].agg(["size", "sum"])
    oldest, pro_rata = (by_mode.loc[m] if m in by_mode.index else pd.Series({"size": 0, "sum": 0.0})
                        for m in ("äldst först", "pro rata"))
    node("drag", [f"äldst först {int(oldest['size'])} · {oldest['sum']:,.0f}",
                  f"pro rata {int(pro_rata['size'])} · {pro_rata['sum']:,.0f}"],
         modes.sort_values("dragit", ascending=False).assign(
             forsta_leverans=lambda f: f["forsta_leverans"].dt.strftime("%Y-%m-%d"),
             sista_avverkning=lambda f: f["sista_avverkning"].dt.strftime("%Y-%m-%d"),
             dragit=lambda f: f["dragit"].round(2)) if len(modes) else None,
         volym=float(modes["dragit"].sum()) if len(modes) else 0.0)

    tiers = {t: float(alloc.loc[alloc[TIER] == t, VOL].sum()) for t in CERTAINTY_TIERS}
    billed_net = sum(tiers.values())
    shortfall = alloc[alloc[TIER] != "S1"]
    node("brist", [f"{billed_net - tiers['S1']:,.1f} m3fub utöver lagret",
                   f"{shortfall[[AO, SORT]].drop_duplicates().shape[0]} AO × sortiment"],
         shortfall.groupby([AO, SORT, TIER], as_index=False)[VOL].sum().round(3).sort_values(VOL, ascending=False),
         volym=billed_net - tiers["S1"])
    for tier in CERTAINTY_TIERS:
        block = alloc[alloc[TIER] == tier]
        share = tiers[tier] / billed_net if billed_net > 0 else 0.0
        node(tier, [f"{tiers[tier]:,.1f} m3fub · {share:.1%}", f"{block[AO].nunique()} AO"],
             _by_dest_sort(block) if len(block) else None, volym=tiers[tier], andel=share)

    cells = sum(int((m.delivered > 0.0005).sum()) for m in output.matrices.values())
    matrix_rows = []
    for m in output.matrices.values():
        delivered = float(m.delivered.sum())
        matrix_rows.append({DEST: m.destination, SORT: m.sortiment, "levererat": round(delivered, 2),
                            "celler": int((m.delivered > 0.0005).sum()),
                            "andel_S1": round(float(m.by_tier["S1"].sum()) / delivered, 3) if delivered > 0 else None})
    node("matr", [f"{len(output.matrices)} destination × sortiment", f"{cells} celler med volym"],
         pd.DataFrame(matrix_rows))

    delivered_lines = invoice[invoice["radtyp"] == "LEVERANS"]
    value_rows = []
    for destination, lines in delivered_lines.groupby(DEST):
        interval = value_interval(output, destination)
        value = float(lines["belopp_kr"].sum())
        row = {DEST: destination, "varde_kr": round(value, 0)}
        if interval:
            row |= {"p05_kr": round(interval[0], 0), "p95_kr": round(interval[1], 0),
                    "halv_bredd": _swedish(f"±{(interval[1] - interval[0]) / 2 / value:.1%}") if value else ""}
        value_rows.append(row)
    widths = [(r["p95_kr"] - r["p05_kr"]) / 2 / r["varde_kr"] for r in value_rows if "p05_kr" in r and r["varde_kr"]]
    node("mc", [f"{cfg.mc_draws} dragningar" if cfg.intervals else "avstängt (profil enkel)",
                f"värde ±{np.mean(widths):.1%} (90 %)" if widths else "inga intervall"],
         pd.DataFrame(value_rows))

    invoice_rows = []
    for destination, lines in invoice.groupby(DEST):
        amounts = lines.groupby("radtyp")["belopp_kr"].sum()
        invoice_rows.append({DEST: destination, "leverans_kr": amounts.get("LEVERANS", 0.0),
                             "kreditering_kr": amounts.get("KREDITERING", 0.0),
                             "korrigering_kr": amounts.get("KORRIGERING", 0.0), "att_fakturera_kr": invoice_total_kr(lines)})
    unpriced = float(invoice.loc[~invoice["prissatt"].astype(bool), "volym_m3fub"].sum()) if len(invoice) else 0.0
    total_kr = invoice_total_kr(invoice) if len(invoice) else 0.0
    node("fakt", [f"{total_kr:,.0f} kr",
                  "volym = inmätning ✓" + (f" · {unpriced:.1f} utan pris" if unpriced > 0.0005 else "")],
         pd.DataFrame(invoice_rows).round(2), kr=total_kr, utan_pris=unpriced)

    closing = step.ledger
    stock_out = closing.stock.groupby(SORT)[VOL].sum().rename("lager")
    deficit_out = closing.deficit.groupby(SORT)[VOL].sum().rename("underskott")
    written = rec.groupby(SORT)["avskrivet"].sum() if len(rec) else pd.Series(dtype=float)
    node("ligg_ut", [f"lager {closing.stock[VOL].sum():,.1f} m3fub",
                     f"underskott {closing.deficit[VOL].sum():,.0f} · avskrivet {written.sum():,.0f}"],
         pd.concat([stock_out, deficit_out, written.rename("avskrivet")], axis=1).fillna(0.0).round(2).rename_axis(SORT).reset_index(),
         lager=float(closing.stock[VOL].sum()), underskott=float(closing.deficit[VOL].sum()), avskrivet=float(written.sum()))

    scores = pd.DataFrame()
    if truth is not None:
        month = SimpleNamespace(period=period, truth=truth)
        scores = pd.DataFrame([
            _score(month, m, inputs.prices, m.harvested if m.harvested.sum() > 0 else None)
            for m in output.matrices.values() if m.delivered.sum() > 0
        ])
    facit = {}
    if len(scores):
        weights = scores["levererat_facit"]

        def weighted(column: str) -> float | None:
            usable = scores[column].notna() if column in scores else None
            if usable is None or not usable.any():
                return None
            return float(np.average(scores.loc[usable, column].abs(), weights=weights[usable]))

        inside = scores["varde_inom_90"].dropna()
        facit = {"prisfel": weighted("prisfel_kr_m3"), "prisfel_naiv": weighted("prisfel_kr_m3_naiv"),
                 "felplacerad": weighted("fel_placerad_andel"), "felplacerad_naiv": weighted("fel_placerad_andel_naiv"),
                 "inom": int(inside.sum()), "av": int(len(inside))}
        shown = scores[[DEST, SORT, "levererat_facit", "prisfel_kr_m3", "prisfel_kr_m3_naiv", "fel_placerad_andel",
                        "varde_inom_90"]].rename(columns={"levererat_facit": "facit_m3fub", "prisfel_kr_m3": "prisfel",
                                                          "prisfel_kr_m3_naiv": "prisfel_naivt", "fel_placerad_andel": "felplacerad",
                                                          "varde_inom_90": "värde_inom_90"})
        node("facit", [f"prisfel {facit['prisfel']:.1f} kr/m3fub",
                       f"naivt {facit['prisfel_naiv']:.1f} · inom 90 %: {facit['inom']}/{facit['av']}"
                       if facit["prisfel_naiv"] is not None else f"inom 90 %: {facit['inom']}/{facit['av']}"],
             shown.round(3), **facit)
    else:
        node("facit", ["inget facit", "verklig data saknar facit"])

    pairs = []
    for m in output.matrices.values():
        delivered = float(m.delivered.sum())
        if delivered <= 0:
            continue
        row = {"destination": m.destination, "sortiment": m.sortiment, "levererat": delivered,
               **{t: float(m.by_tier[t].sum()) / delivered for t in CERTAINTY_TIERS},
               "lager_ut": float(m.closing_stock.sum()), "varde_kr": float(m.value_kr.sum())}
        if len(scores):
            match = scores[(scores[DEST] == m.destination) & (scores[SORT] == m.sortiment)]
            if len(match):
                row |= {"prisfel": float(match["prisfel_kr_m3"].iloc[0]),
                        "felplacerad": float(match["fel_placerad_andel"].iloc[0]),
                        "inom_90": match["varde_inom_90"].iloc[0]}
        pairs.append(row)

    return {
        "period": period,
        "noder": nodes,
        "kpi": {"netto": net, "kr": total_kr, "S1": tiers["S1"] / billed_net if billed_net else None,
                "provisoriskt": 1 - tiers["S1"] / billed_net if billed_net else None, "lager_ut": float(closing.stock[VOL].sum()),
                "underskott_ut": float(closing.deficit[VOL].sum()), **{f"facit_{k}": v for k, v in facit.items()}},
        "par": sorted(pairs, key=lambda r: (r["destination"], r["sortiment"])),
    }


def _climb_status() -> dict | None:
    if not LOG.exists():
        return None
    entries = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    baseline = next((e for e in reversed(entries) if e["typ"] == "jamforelse" and not e["andring"]), None)
    control = next((e for e in reversed(entries) if e["typ"] == "kontroll"), None)
    if baseline is None:
        return None
    status = {"tid": baseline["tid"], "kod": baseline["kod"], "poang": baseline["poang"], "prisfel": baseline["prisfel"],
              "varde_90": baseline["varde_90"], "steg": len(entries)}
    if control:
        status["kontroll"] = {"tid": control["tid"], "poang": control["poang"], "prisfel": control["prisfel"],
                              "varde_90": control["varde_90"], "diff": control["diff"], "se": control["se"]}
    return status


def _shown(path: Path | None) -> str:
    """A path inside the repository relative to it, so the report does not show the machine's folders."""
    if path is None:
        return ""
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name


def build(periods: list[str], cfg: Config, data: Path | None, source: Path | None) -> dict:
    ledger = Ledger.empty()
    months = []
    for period in periods:
        inputs = adapters.load(period, cfg, source, _files(data, period))
        output = run_month(ledger, inputs.harvest, inputs.deliveries, inputs.prices, period, inputs.closed_aos, cfg,
                           inputs.work_orders)
        months.append(month_report(period, inputs, output, ledger, cfg, _truth(data, period)))
        ledger = output.step.ledger
    return {
        "skapad": time.strftime("%Y-%m-%d %H:%M"),
        "kod": _git(),
        "data": _shown(source or data),
        "parametrar": {k: v for k, v in asdict(cfg).items() if k not in ("volume_methods",)},
        "klassnamn": TIER_NAMES,
        "klattring": _climb_status(),
        "manader": months,
    }


def render(report: dict) -> str:
    payload = json.dumps(_clean(report), ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("/*DATA*/null", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=ROOT / "examples" / "demo",
                        help="Katalog med kanoniska filer per månad, och facit om det finns")
    parser.add_argument("--kalla", type=Path, help="Källbeskrivning i stället för --data; kräver --perioder")
    parser.add_argument("--perioder", nargs="+", help="Månader i ordning; annars alla med leveransfil i --data")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "flodesrapport.html")
    args = parser.parse_args(argv)

    if args.kalla and not args.perioder:
        parser.error("--kalla kräver --perioder")
    periods = args.perioder or sorted(p.stem.removeprefix("leverans_") for p in args.data.glob("leverans_*.csv"))
    if not periods:
        parser.error(f"Inga leveransfiler i {args.data}")
    report = build(periods, load_config(args.config), None if args.kalla else args.data.resolve(),
                   args.kalla.resolve() if args.kalla else None)
    report["modell"] = args.config.stem if args.config else "standard"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(report), encoding="utf-8")
    print(f"{len(periods)} månader, rapport i {args.out}")
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>treedist flöde</title>
<style>
:root {
  --bg: #f7f6f2; --panel: #ffffff; --ink: #1d1f22; --muted: #62666d; --line: #d9d7d0; --edge: #b4b1a8;
  --accent: #2f5d8a; --accent-soft: #e3ecf5; --input: #f0eee8; --output: #e8f1ea; --output-ink: #2d6a3e;
  --s1: #2d7a46; --s2: #b7862a; --s3: #c0602a; --s4: #b03a3a; --warn: #a33b2b;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #15171a; --panel: #1e2125; --ink: #e8e6e1; --muted: #9a9ea5; --line: #33373d; --edge: #555a61;
    --accent: #7fb0e0; --accent-soft: #1f3040; --input: #24272b; --output: #1d2e22; --output-ink: #8fd0a2;
    --s1: #5cbf7c; --s2: #dcb052; --s3: #e58a55; --s4: #e06a6a; --warn: #e07a6a;
  }
}
:root[data-theme="dark"] {
  --bg: #15171a; --panel: #1e2125; --ink: #e8e6e1; --muted: #9a9ea5; --line: #33373d; --edge: #555a61;
  --accent: #7fb0e0; --accent-soft: #1f3040; --input: #24272b; --output: #1d2e22; --output-ink: #8fd0a2;
  --s1: #5cbf7c; --s2: #dcb052; --s3: #e58a55; --s4: #e06a6a; --warn: #e07a6a;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1240px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 32px 0 10px; }
.meta { color: var(--muted); font-size: 13px; }
.tabs { display: flex; gap: 6px; flex-wrap: wrap; margin: 18px 0 14px; }
.tabs button { border: 1px solid var(--line); background: var(--panel); color: var(--ink); padding: 6px 12px;
  border-radius: 6px; cursor: pointer; font: inherit; }
.tabs button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: var(--bg); }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.kpi { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
.kpi .label { color: var(--muted); font-size: 12px; }
.kpi .value { font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; }
.kpi .sub { color: var(--muted); font-size: 12px; }
.graph { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow-x: auto; }
.graph svg { display: block; min-width: 980px; width: 100%; height: auto; }
.node { cursor: pointer; }
.node rect.box { stroke: var(--line); stroke-width: 1; }
.node:hover rect.box, .node.selected rect.box { stroke: var(--accent); stroke-width: 2; }
.node text { fill: var(--ink); font-size: 11.5px; }
.node text.title { font-weight: 600; font-size: 12.5px; }
.node text.line { fill: var(--muted); font-variant-numeric: tabular-nums; }
.edge { fill: none; stroke: var(--edge); stroke-width: 1.4; opacity: .7; }
.edge.on { stroke: var(--accent); opacity: 1; stroke-width: 2; }
.col-label { fill: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }
.detail { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; margin-top: 12px; }
.detail h3 { margin: 0 0 4px; font-size: 15px; }
.detail p { margin: 0 0 10px; color: var(--muted); max-width: 820px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; font-variant-numeric: tabular-nums; font-size: 13px; }
th, td { padding: 4px 10px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
th { color: var(--muted); font-weight: 500; }
th:first-child, td:first-child, th.text, td.text { text-align: left; }
.note { color: var(--muted); font-size: 12px; margin-top: 6px; }
.bar { display: inline-flex; width: 120px; height: 10px; border-radius: 2px; overflow: hidden; vertical-align: middle; background: var(--line); }
.bar span { display: block; height: 100%; }
.legend { display: flex; gap: 14px; flex-wrap: wrap; color: var(--muted); font-size: 12px; margin-top: 8px; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
.bad { color: var(--warn); }
.params { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 2px 18px; font-size: 13px; }
.params div { display: flex; justify-content: space-between; border-bottom: 1px dotted var(--line); padding: 2px 0; }
.params span:last-child { font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
<main>
  <h1>treedist, månadens flöde</h1>
  <div class="meta" id="meta"></div>
  <div class="tabs" id="tabs" role="group" aria-label="Månad"></div>
  <div class="kpis" id="kpis"></div>
  <h2>Flödet steg för steg</h2>
  <div class="graph"><svg id="dag" viewBox="0 0 1200 560" role="img" aria-label="Flödesgraf"></svg></div>
  <div class="legend">
    <span><i style="background:var(--input)"></i>indata</span>
    <span><i style="background:var(--accent-soft)"></i>steg</span>
    <span><i style="background:var(--s1)"></i>S1 slutlig</span>
    <span><i style="background:var(--s2)"></i>S2</span>
    <span><i style="background:var(--s3)"></i>S3</span>
    <span><i style="background:var(--s4)"></i>S4 preliminära</span>
    <span><i style="background:var(--output)"></i>utdata</span>
  </div>
  <div class="detail" id="detail"></div>
  <h2>Destination och sortiment</h2>
  <div class="scroll"><table id="pairs"></table></div>
  <h2>Månad för månad</h2>
  <div class="scroll"><table id="trend"></table></div>
  <div class="note">Ingående liggare är tom första månaden, så virke skördat tidigare saknar skördardata där (kallstart).</div>
  <h2>Metodens prövning</h2>
  <div id="climb"></div>
  <h2>Parametrar</h2>
  <div class="params" id="params"></div>
</main>
<script>
const R = /*DATA*/null;
const fmt = (v, d = 1) => v == null ? "–" : v.toLocaleString("sv-SE", {minimumFractionDigits: d, maximumFractionDigits: d});
const pct = (v, d = 1) => v == null ? "–" : (100 * v).toLocaleString("sv-SE", {minimumFractionDigits: d, maximumFractionDigits: d}) + " %";
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const TIER = {S1: "var(--s1)", S2: "var(--s2)", S3: "var(--s3)", S4: "var(--s4)"};

const W = 178, H = 64;
const COLS = [{x: 12, label: "Indata"}, {x: 208, label: "Förbehandling"}, {x: 404, label: "Liggare"},
  {x: 600, label: "Dragning"}, {x: 796, label: "Säkerhetsklass"}, {x: 1008, label: "Utdata"}];
const NODES = [
  {id: "skord", t: "Skördardata", c: 0, y: 34, kind: "input"},
  {id: "lev", t: "Inmätning", c: 0, y: 134, kind: "input"},
  {id: "ao", t: "Arbetsordrar", c: 0, y: 234, kind: "input"},
  {id: "avsl", t: "Avslutade AO", c: 0, y: 334, kind: "input"},
  {id: "pris", t: "Prislista", c: 0, y: 470, kind: "input"},
  {id: "kal", t: "Kalibrering", c: 1, y: 34, kind: "step"},
  {id: "vand", t: "Vända lass", c: 1, y: 184, kind: "step"},
  {id: "ligg", t: "Liggare in", c: 2, y: 34, kind: "step"},
  {id: "korr", t: "Korrigering", c: 2, y: 184, kind: "step"},
  {id: "drag", t: "Dragning ur lagret", c: 3, y: 110, kind: "step"},
  {id: "brist", t: "Utöver lagret", c: 3, y: 254, kind: "step"},
  {id: "S1", t: "S1 eget lager", c: 4, y: 34, kind: "S1"},
  {id: "S2", t: "S2 AO-historik", c: 4, y: 164, kind: "S2"},
  {id: "S3", t: "S3 lånad", c: 4, y: 254, kind: "S3"},
  {id: "S4", t: "S4 okänd", c: 4, y: 344, kind: "S4"},
  {id: "matr", t: "Matriser", c: 5, y: 34, kind: "output"},
  {id: "mc", t: "Monte Carlo", c: 5, y: 124, kind: "output"},
  {id: "fakt", t: "Faktura", c: 5, y: 234, kind: "output"},
  {id: "ligg_ut", t: "Liggare ut", c: 5, y: 344, kind: "output"},
  {id: "facit", t: "Facit", c: 5, y: 470, kind: "output"},
];
const EDGES = [["skord", "kal"], ["kal", "ligg"], ["ligg", "korr"], ["ligg", "drag"], ["lev", "drag"], ["lev", "vand"],
  ["drag", "S1"], ["drag", "brist"], ["ao", "brist"], ["brist", "S2"], ["brist", "S3"], ["brist", "S4"],
  ["S1", "matr"], ["S2", "matr"], ["S3", "matr"], ["S4", "matr"], ["matr", "mc"], ["matr", "fakt"],
  ["korr", "fakt"], ["vand", "fakt"], ["pris", "fakt"], ["drag", "ligg_ut"], ["brist", "ligg_ut"], ["avsl", "ligg_ut"],
  ["matr", "facit"], ["mc", "facit"]];
const pos = Object.fromEntries(NODES.map(n => [n.id, {x: COLS[n.c].x, y: n.y}]));
const fill = k => ({input: "var(--input)", step: "var(--accent-soft)", output: "var(--output)"}[k] || "var(--panel)");

let month = R.manader.length - 1, selected = "drag";

function svgEl(tag, attrs, parent) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (parent) parent.appendChild(el);
  return el;
}

function drawGraph() {
  const svg = document.getElementById("dag");
  svg.innerHTML = "";
  const m = R.manader[month];
  COLS.forEach(c => svgEl("text", {x: c.x, y: 18, class: "col-label"}, svg).textContent = c.label);
  const edges = svgEl("g", {}, svg);
  for (const [a, b] of EDGES) {
    const p = pos[a], q = pos[b];
    const x1 = p.x + W, y1 = p.y + H / 2, x2 = q.x, y2 = q.y + H / 2, mid = (x1 + x2) / 2;
    const on = a === selected || b === selected;
    svgEl("path", {d: `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2 - 2},${y2}`, class: "edge" + (on ? " on" : "")}, edges);
  }
  for (const n of NODES) {
    const p = pos[n.id], info = m.noder[n.id];
    const g = svgEl("g", {class: "node" + (n.id === selected ? " selected" : ""), tabindex: 0, role: "button",
      "aria-label": n.t}, svg);
    svgEl("rect", {x: p.x, y: p.y, width: W, height: H, rx: 7, class: "box", fill: fill(n.kind)}, g);
    if (TIER[n.kind]) {
      svgEl("rect", {x: p.x, y: p.y, width: 5, height: H, rx: 2, fill: TIER[n.kind]}, g);
      const share = info.tal.andel || 0;
      svgEl("rect", {x: p.x + 12, y: p.y + H - 9, width: W - 24, height: 4, rx: 2, fill: "var(--line)"}, g);
      svgEl("rect", {x: p.x + 12, y: p.y + H - 9, width: Math.max((W - 24) * share, share > 0 ? 2 : 0), height: 4, rx: 2,
        fill: TIER[n.kind]}, g);
    }
    svgEl("text", {x: p.x + 12, y: p.y + 18, class: "title"}, g).textContent = n.t;
    info.rader.forEach((line, i) => svgEl("text", {x: p.x + 12, y: p.y + 35 + i * 15, class: "line"}, g).textContent = line);
    const pick = () => { selected = n.id; drawGraph(); drawDetail(); };
    g.addEventListener("click", pick);
    g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
  }
}

function tableHtml(t) {
  if (!t || !t.rader.length) return '<div class="note">Inget att visa denna månad.</div>';
  const numeric = t.kolumner.map((_, i) => t.rader.every(r => r[i] == null || typeof r[i] === "number"));
  const cell = (v, i) => v == null ? "–" : numeric[i] ? fmt(v, Math.abs(v) < 10 && !Number.isInteger(v) ? 3 : Number.isInteger(v) ? 0 : 2) : esc(v);
  let html = '<div class="scroll"><table><tr>' + t.kolumner.map((c, i) => `<th class="${numeric[i] ? "" : "text"}">${esc(c)}</th>`).join("") + "</tr>";
  for (const r of t.rader) html += "<tr>" + r.map((v, i) => `<td class="${numeric[i] ? "" : "text"}">${cell(v, i)}</td>`).join("") + "</tr>";
  html += "</table></div>";
  if (t.utelamnade) html += `<div class="note">${t.utelamnade} rader till visas inte.</div>`;
  return html;
}

function drawDetail() {
  const n = NODES.find(x => x.id === selected), info = R.manader[month].noder[selected];
  document.getElementById("detail").innerHTML =
    `<h3>${esc(n.t)} · ${esc(R.manader[month].period)}</h3><p>${esc(info.text)}</p>` + tableHtml(info.tabell);
}

function drawKpis() {
  const k = R.manader[month].kpi;
  const tiles = [
    ["Inmätt netto", fmt(k.netto, 0) + " m3fub", ""],
    ["Att fakturera", fmt(k.kr, 0) + " kr", "exkl. moms"],
    ["Från eget lager (S1)", pct(k.S1), "preliminärt " + pct(k.provisoriskt)],
    ["Liggare ut", fmt(k.lager_ut, 0) + " m3fub", "underskott " + fmt(k.underskott_ut, 1)],
  ];
  if (k.facit_prisfel != null) {
    tiles.push(["Prisfel mot facit", fmt(k.facit_prisfel, 1) + " kr/m3fub", "naivt " + fmt(k.facit_prisfel_naiv, 1)]);
    tiles.push(["Fel placerad volym", pct(k.facit_felplacerad), "naivt " + pct(k.facit_felplacerad_naiv)]);
    tiles.push(["Värde inom 90 %", `${k.facit_inom} av ${k.facit_av}`, "destination × sortiment"]);
  }
  document.getElementById("kpis").innerHTML = tiles.map(([l, v, s]) =>
    `<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div><div class="sub">${s}</div></div>`).join("");
}

function tierBar(row) {
  return '<span class="bar">' + ["S1", "S2", "S3", "S4"].map(t =>
    `<span style="width:${100 * (row[t] || 0)}%;background:${TIER[t]}" title="${t} ${pct(row[t])}"></span>`).join("") + "</span>";
}

function drawPairs() {
  const rows = R.manader[month].par, facit = rows.some(r => r.prisfel != null);
  let html = '<tr><th class="text">Destination</th><th class="text">Sortiment</th><th>Levererat m3fub</th><th class="text">S1–S4</th>' +
    "<th>S1</th><th>Värde kr</th><th>Lager ut m3fub</th>" + (facit ? "<th>Prisfel kr/m3fub</th><th>Fel placerat</th><th>Värde inom 90 %</th>" : "") + "</tr>";
  for (const r of rows) {
    html += `<tr><td class="text">${esc(r.destination)}</td><td class="text">${esc(r.sortiment)}</td><td>${fmt(r.levererat)}</td>` +
      `<td class="text">${tierBar(r)}</td><td>${pct(r.S1, 0)}</td><td>${fmt(r.varde_kr, 0)}</td><td>${fmt(r.lager_ut)}</td>`;
    if (facit) html += `<td>${fmt(r.prisfel, 1)}</td><td>${pct(r.felplacerad)}</td>` +
      `<td class="${r.inom_90 === 0 ? "bad" : ""}">${r.inom_90 == null ? "–" : r.inom_90 ? "ja" : "nej"}</td>`;
    html += "</tr>";
  }
  document.getElementById("pairs").innerHTML = html;
}

function drawTrend() {
  const facit = R.manader.some(m => m.kpi.facit_prisfel != null);
  let html = '<tr><th class="text">Månad</th><th>Netto m3fub</th><th>Fakturerat kr</th><th>S1</th><th>Korrigering kr</th>' +
    "<th>Lager ut m3fub</th><th>Underskott m3fub</th>" + (facit ? "<th>Prisfel</th><th>Naivt</th><th>Inom 90 %</th>" : "") + "</tr>";
  R.manader.forEach((m, i) => {
    const k = m.kpi;
    html += `<tr${i === month ? ' style="font-weight:600"' : ""}><td class="text">${esc(m.period)}</td><td>${fmt(k.netto, 0)}</td>` +
      `<td>${fmt(k.kr, 0)}</td><td>${pct(k.S1)}</td><td>${fmt(m.noder.korr.tal.kr, 0)}</td><td>${fmt(k.lager_ut, 0)}</td><td>${fmt(k.underskott_ut, 1)}</td>`;
    if (facit) html += `<td>${fmt(k.facit_prisfel, 1)}</td><td>${fmt(k.facit_prisfel_naiv, 1)}</td><td>${k.facit_av ? k.facit_inom + "/" + k.facit_av : "–"}</td>`;
    html += "</tr>";
  });
  document.getElementById("trend").innerHTML = html;
}

function drawStatic() {
  document.getElementById("meta").textContent =
    `Modell ${R.modell} · data ${R.data} · kod ${R.kod} · skapad ${R.skapad} · ${R.manader.length} månader körda i följd från tom liggare`;
  const c = R.klattring, el = document.getElementById("climb");
  if (c) {
    let html = `<p class="note" style="font-size:13px">Simulerade flöden, 4 scenarier × 6 utvecklingsfrön × 12 månader. ` +
      `Poäng = prisfel + 0,3 × |täckning − 90 %| i procentenheter. Lägre är bättre.</p><div class="kpis">` +
      `<div class="kpi"><div class="label">Poäng, utveckling</div><div class="value">${fmt(c.poang, 2)}</div><div class="sub">${esc(c.tid)} · ${esc(c.kod)}</div></div>` +
      `<div class="kpi"><div class="label">Prisfel, utveckling</div><div class="value">${fmt(c.prisfel, 2)} kr/m3fub</div><div class="sub">medel över scenarier</div></div>` +
      `<div class="kpi"><div class="label">Värde inom 90 %</div><div class="value">${pct(c.varde_90)}</div><div class="sub">mål 90 %</div></div>`;
    if (c.kontroll) html += `<div class="kpi"><div class="label">Kontrollfrön</div><div class="value">${fmt(c.kontroll.poang, 2)}</div>` +
      `<div class="sub">prisfel ${fmt(c.kontroll.prisfel, 2)} · inom 90 % ${pct(c.kontroll.varde_90)}</div></div>`;
    el.innerHTML = html + `</div><div class="note">Senaste baslinje i climb/logg.jsonl, ${c.steg} prövningar totalt. ` +
      "Allt är prövat mot simulatorn, inte mot verklig data.</div>";
  } else el.innerHTML = '<div class="note">Ingen klättringslogg hittades.</div>';
  document.getElementById("params").innerHTML = Object.entries(R.parametrar).map(([k, v]) =>
    `<div><span>${esc(k)}</span><span>${esc(v == null ? "–" : v)}</span></div>`).join("");
  document.getElementById("tabs").innerHTML = R.manader.map((m, i) =>
    `<button type="button" data-i="${i}" aria-pressed="${i === month}">${esc(m.period)}</button>`).join("");
  document.querySelectorAll("#tabs button").forEach(b => b.addEventListener("click", () => {
    month = +b.dataset.i;
    document.querySelectorAll("#tabs button").forEach(x => x.setAttribute("aria-pressed", x === b));
    drawMonth();
  }));
}

function drawMonth() { drawKpis(); drawGraph(); drawDetail(); drawPairs(); drawTrend(); }
drawStatic();
drawMonth();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
