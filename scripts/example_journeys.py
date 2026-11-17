"""Follow example work orders from felling to delivery, and summarise the simulated flow.

Picks one work order of each kind (an ordinary one, one that crosses a month end,
one with a late report and one redirected), and shows what happened to its logs
next to what `treedist` made of it month by month. Then measures the flow as a whole, for comparison with
published statistics in docs/antaganden.md.

Run from the repository root:

    uv run python scripts/example_journeys.py --out docs/exempelresor.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from treedist.dev.model import Model, evaluate_month
from treedist.core.ledger import Ledger
from treedist.schema import AO, BRUTTO, DEST, DIA, SORT, TIER, VOL, validate_deliveries, validate_harvest
from treedist.dev.simulate import Flow, SimParams, monthly, simulate_flow

BURN_IN = 2


def _mean_diameter(frame: pd.DataFrame) -> float:
    diameters = pd.to_numeric(frame[DIA], errors="coerce")
    known = diameters.notna() & (frame[VOL] > 0)
    return float(np.average(diameters[known], weights=frame.loc[known, VOL])) if known.any() else float("nan")


def _diameter_index(estimate: pd.DataFrame, truth: pd.DataFrame) -> float:
    e = estimate.groupby(DIA)[VOL].sum()
    t = truth.groupby(DIA)[VOL].sum()
    joined = pd.concat([e / e.sum(), t / t.sum()], axis=1).fillna(0.0)
    return 0.5 * float((joined.iloc[:, 0] - joined.iloc[:, 1]).abs().sum())


def _run(flow: Flow, cfg: Model) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Allocation, how earlier estimates differed from harvester data that arrived later, and facit, for every month."""
    ledger = Ledger.empty()
    allocations, differences, truths = [], [], []
    for month in monthly(flow):
        harvest = validate_harvest(month.harvest, month.period)
        deliveries = validate_deliveries(month.deliveries, month.period)
        output = evaluate_month(ledger, harvest, deliveries, month.period, month.transport_done, cfg)
        ledger = output.step.ledger
        allocations.append(output.step.allocation.assign(period=month.period))
        differences.append(output.step.corrections.assign(period=month.period))
        truths.append(month.truth.assign(period=month.period))
    return pd.concat(allocations), pd.concat(differences), pd.concat(truths)


def _work_orders(flow: Flow) -> pd.DataFrame:
    """One row per work order and assortment with what characterises its journey."""
    logs = flow.logs
    delivered = logs[~logs["lost"]]
    rows = []
    for (ao, sortiment), block in logs.groupby([AO, SORT], sort=False):
        sent = delivered[(delivered[AO] == ao) & (delivered[SORT] == sortiment)]
        rows.append(
            {
                AO: ao,
                SORT: sortiment,
                "planerad": flow.destinations[ao],
                "faktisk": block[DEST].iloc[0],
                "avlagg": block["landing"].nunique(),
                "volym": float(block["v"].sum()),
                "skord_fran": block["harvested"].min(),
                "skord_till": block["harvested"].max(),
                "lev_fran": sent["delivered"].min(),
                "lev_till": sent["delivered"].max(),
                "lass": sent["load"].nunique(),
                "sen_rapport": bool((block["reported"] > block["harvested"].dt.strftime("%Y-%m")).any()),
                "lev_manader": sent["delivered"].dt.strftime("%Y-%m").nunique(),
            }
        )
    return pd.DataFrame(rows)


def _pick(work_orders: pd.DataFrame, flow: Flow) -> list[tuple[str, pd.Series]]:
    usable = work_orders[
        (work_orders["skord_fran"] >= pd.Timestamp(flow.periods[BURN_IN]))
        & (work_orders["lev_till"] <= pd.Period(flow.periods[-1], freq="M").end_time)
    ]
    ordinary = ~usable["sen_rapport"] & (usable["planerad"] == usable["faktisk"])
    choices = [
        ("En leveransmånad", ordinary & (usable["lev_manader"] == 1) & (usable["avlagg"] >= 2)),
        ("Över ett månadsskifte", ordinary & (usable["lev_manader"] == 2)),
        ("Sen skördarrapport", usable["sen_rapport"]),
        ("Omdirigerad till annat sågverk", usable["planerad"] != usable["faktisk"]),
    ]
    picked = []
    for title, mask in choices:
        candidates = usable[mask]
        if len(candidates):
            # The candidate closest to the median volume is the most typical one.
            typical = (candidates["volym"] - candidates["volym"].median()).abs().idxmin()
            picked.append((title, candidates.loc[typical]))
    return picked


def _journey(title: str, row: pd.Series, flow: Flow, allocation, differences, truth) -> list[str]:
    ao, sortiment = row[AO], row[SORT]
    logs = flow.logs[(flow.logs[AO] == ao) & (flow.logs[SORT] == sortiment)]
    sent = logs[~logs["lost"]]
    loads = flow.deliveries[(flow.deliveries[AO] == ao) & (flow.deliveries[SORT] == sortiment)]
    reported = sorted(set(logs["reported"]))

    lines = [
        f"## {title}: {ao}, {sortiment}",
        "",
        f"- **Skörd:** {len(logs):,} stockar, {row['volym']:.0f} m3fub på {row['avlagg']} avlägg.",
        f"- **Planerad destination:** {row['planerad']}. **Faktisk:** {row['faktisk']}.",
        f"- **Skördarrapport:** {', '.join(reported)}.",
        f"- **Svinn:** {int(logs['lost'].sum())} stockar kom aldrig fram.",
        "",
        "| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for landing, block in logs.groupby("landing"):
        delivered = block[~block["lost"]]
        storage = (delivered["delivered"] - delivered["harvested"]).dt.days
        lines.append(
            f"| {landing + 1} | {block['harvested'].min():%d/%m}–{block['harvested'].max():%d/%m} | {len(block)} "
            f"| {block['v'].sum():.0f} | {np.average(block['d'], weights=block['v']):.1f} "
            f"| {delivered['delivered'].min():%d/%m}–{delivered['delivered'].max():%d/%m} "
            f"| {delivered['load'].nunique()} | {storage.median():.0f} |"
        )

    gross, net = loads[BRUTTO].sum(), loads[VOL].sum()
    lines += [
        "",
        f"Inmätt: {len(loads)} leveranser, {gross:.1f} m3fub brutto och {net:.1f} netto, "
        f"mot {sent['v'].sum():.1f} som faktiskt kom fram och {logs['measured_v'].sum():.1f} enligt skördaren.",
        "",
        "| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Skattad medeldiameter | "
        "Verklig | Felindex diameter |",
        "|---|---|---|---|---|---|---|",
    ]
    mine = allocation[(allocation[AO] == ao) & (allocation[SORT] == sortiment)]
    facit = truth[(truth[AO] == ao) & (truth[SORT] == sortiment)]
    for period, block in mine.groupby("period"):
        tiers = block.groupby(TIER)[VOL].sum()
        total = tiers.sum()
        actual = facit[facit["period"] == period]
        share = {t: f"{tiers.get(t, 0.0) / total:.0%}" for t in ("S1", "S2")}
        lines.append(
            f"| {period} | {total:.1f} | {share['S1']} | {share['S2']} "
            f"| {_mean_diameter(block):.1f} | {_mean_diameter(actual):.1f} | {_diameter_index(block, actual):.2f} |"
        )
    differed = differences[(differences[AO] == ao) & (differences[SORT] == sortiment)]
    if len(differed):
        moved = differed.groupby("period")[VOL].apply(lambda v: v.abs().sum() / 2)
        lines += ["", "Uppskattningen (S2) mot skördardata som kom senare: "
                  + ", ".join(f"{p}: {v:.1f} m3fub i en annan klass" for p, v in moved.items())
                  + ". Uppskattningen står kvar på bilagan."]
    whole = _diameter_index(mine, facit)
    lines += ["", f"Över hela avtalsobjektet: felindex {whole:.2f} för diameterfördelningen.", ""]
    return lines


def _flow_statistics(flow: Flow, work_orders: pd.DataFrame) -> list[str]:
    logs = flow.logs[~flow.logs["lost"]]
    days = (logs["delivered"] - logs["harvested"]).dt.days
    weights = logs["v"]
    quantiles = np.quantile(np.repeat(days.to_numpy(), np.maximum((weights * 20).round().astype(int), 1)), [0.1, 0.5, 0.9])

    # Little's law: mean stock between felling and delivery divided by the flow.
    span = pd.date_range(flow.periods[BURN_IN], pd.Period(flow.periods[-1], freq="M").end_time, freq="D")
    felled = logs.groupby(logs["harvested"].dt.floor("D"))["v"].sum().reindex(span, fill_value=0.0).cumsum()
    left = logs.groupby(logs["delivered"].dt.floor("D"))["v"].sum().reindex(span, fill_value=0.0).cumsum()
    before = logs[logs["harvested"] < span[0]]
    opening = float(before["v"].sum() - before[before["delivered"] < span[0]]["v"].sum())
    stock = opening + felled - left
    daily = float(logs[(logs["delivered"] >= span[0]) & (logs["delivered"] <= span[-1])]["v"].sum()) / len(span)

    durations = (work_orders["skord_till"] - work_orders["skord_fran"]).dt.days + 1
    campaigns = (work_orders["lev_till"] - work_orders["lev_fran"]).dt.days + 1
    gaps = (work_orders["lev_fran"] - work_orders["skord_till"]).dt.days
    loads = flow.deliveries[BRUTTO]
    return [
        "## Flödet som helhet",
        "",
        f"Simulering med frö {flow.logs.attrs.get('seed', '')}, {len(flow.periods)} månader, efter {BURN_IN} månaders "
        "inkörning.",
        "",
        "| Storhet | Simulatorn |",
        "|---|---|",
        f"| Tid från fällning till leverans per m3fub, 10/50/90 % | {quantiles[0]:.0f} / {quantiles[1]:.0f} / {quantiles[2]:.0f} dagar |",
        f"| Medeltid enligt Littles lag, lager delat med flöde | {stock.mean() / daily:.0f} dagar |",
        f"| Skördetid per avtalsobjekt, median | {durations.median():.0f} dagar |",
        f"| Från sista fällning till första lass, median | {gaps.median():.0f} dagar |",
        f"| Leveranskampanj, median | {campaigns.median():.0f} dagar |",
        f"| Volym per avtalsobjekt och sortiment, median | {work_orders['volym'].median():.0f} m3fub |",
        f"| Lass per avtalsobjekt och sortiment, median | {work_orders['lass'].median():.0f} |",
        f"| Bruttovolym per leverans, median | {loads.median():.1f} m3fub |",
        f"| Andel avtalsobjekt som levererar i två månader eller fler | {(work_orders['lev_manader'] > 1).mean():.0%} |",
        f"| Andel stockar som når sågverk efter skördarens rapportmånad | {(logs['delivered'].dt.strftime('%Y-%m') > logs['reported']).mean():.0%} |",
        "",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("docs/exempelresor.md"))
    parser.add_argument("--seed", type=int, default=71)
    args = parser.parse_args()

    flow = simulate_flow(SimParams(months=12, seed=args.seed))
    flow.logs.attrs["seed"] = args.seed
    allocation, differences, truth = _run(flow, Model(mc_draws=200))
    work_orders = _work_orders(flow)

    lines = [
        "# Exempelresor från skördning till leverans",
        "",
        "Genererad av [example_journeys.py](../scripts/example_journeys.py) ur simulatorn. Varje resa visar vad som hände",
        "med stockarna och vad `treedist` skattade utan att se dem. Diametrar är klassbottnar, volymviktade. Felindex är",
        "andelen volym i fel diameterklass. Bedömningen av antagandena finns i [antaganden.md](antaganden.md).",
        "",
    ]
    for title, row in _pick(work_orders, flow):
        lines += _journey(title, row, flow, allocation, differences, truth)
    lines += _flow_statistics(flow, work_orders)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Skrev {args.out}")


if __name__ == "__main__":
    main()
