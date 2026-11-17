"""What earlier months sent, kept beside the ledger, so that a month cannot quietly repeat or contradict them.

The ledger keeps volumes, not where they came from, so by itself it cannot tell a load or a harvest row it has
already counted. These files, written next to each month's ledger, can:

    state/<period>/lass.csv        every load id delivered so far, with the month it was first delivered (the
                                   ledger writes it, since a reversed load is credited by its month)
    state/<period>/produktion.csv  the month's harvest rows, to compare with the next month's
    state/<period>/korning.json    the model's parameters and the appendix's groups the month ran with
    state/<period>/avslutade.csv   every contract object closed so far, with the month it closed

`problems` compares a month's input with the previous month's files. A FEL stops the run:

- a load id that was delivered in an earlier month and comes again without a reversal (it would be billed twice)
- harvest rows that repeat most of the previous month's (a cumulative export, which would count the harvest twice)
- a calibration other than the one the ledger's stock was calibrated with (the ledger would mix two scales),
  unless the run is told to accept it

OBS asks a person to look: other changed parameters or groups, harvest rows that repeat some of last month's, and
contract objects that deliver again after they were closed. A ledger written before these files existed is not checked.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .config import Config
from .core.ledger import LOAD_KEY, previous_period
from .contract import OUTSIDE
from .schema import AO, DIA, LEN, PRODUCED, VINTAGE, VOL, period_bounds

FEL, OBS = "FEL", "OBS"
LOADS, HARVEST, RUN, CLOSED = "lass.csv", "produktion.csv", "korning.json", "avslutade.csv"
HARVEST_COLUMNS = [AO, PRODUCED, DIA, LEN, VINTAGE, VOL]
# The model's parameters that scale the stock the ledger carries from month to month.
CALIBRATION = ("harvester_bias", "handling_loss")
# Above this share of the month's harvest volume repeated from last month, the export is cumulative.
CUMULATIVE_SHARE = 0.5
# Above this share, enough repeats to ask a person; below it, chance matches of small rows.
REPEATED_SHARE = 0.10


def _read(path: Path) -> pd.DataFrame | None:
    # Text, so that ids keep their leading zeros and classes stay as written.
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""]) if path.exists() else None


def _harvest_key(harvest: pd.DataFrame) -> pd.DataFrame:
    """The rows as text, compared whole."""
    return harvest[HARVEST_COLUMNS].astype(str).assign(**{VOL: harvest[VOL].astype(float).round(6).astype(str)})


def _run(cfg: Config, layout) -> dict:
    groups = None if layout is None else {"diameter": list(layout.diameter), "langd": list(layout.length)}
    return {"modell": asdict(cfg), "bilaga": groups}


def problems(state: Path, period: str, inputs, cfg: Config, layout=None, new_calibration: bool = False
             ) -> list[tuple[str, str]]:
    """(FEL or OBS, what to look at) for the month's input against what earlier months sent. Without `layout`, the
    appendix's groups are not compared."""
    before = state / previous_period(period)
    found: list[tuple[str, str]] = []
    deliveries = inputs.deliveries

    loads = _read(before / LOADS)
    if loads is not None and len(loads):
        rows = deliveries[LOAD_KEY + [VOL]].astype({c: str for c in LOAD_KEY})
        earlier = loads.drop_duplicates(LOAD_KEY).set_index(LOAD_KEY)["period"]
        seen = rows.set_index(LOAD_KEY).index.isin(earlier.index)
        again = rows[seen]
        reversed_ = set(again.loc[again[VOL] < 0].set_index(LOAD_KEY).index)
        repeated = again[(again[VOL] > 0) & ~again.set_index(LOAD_KEY).index.isin(reversed_)]
        if len(repeated):
            keys = list(repeated.set_index(LOAD_KEY).index.unique())
            listed = ", ".join(f"{k[0]} ({earlier.loc[k]})" for k in keys[:5])
            more = f" och {len(keys) - 5} till" if len(keys) > 5 else ""
            found.append((FEL, f"{len(keys)} lass levererades redan en tidigare månad och kommer igen utan att vändas: "
                               f"{listed}{more}. De skulle faktureras två gånger; filtrera bort dem i källan, eller "
                               "vänd lasset med en negativ rad om det mätts om"))

    harvest = _read(before / HARVEST)
    outside = set(inputs.facts.outside[AO]) if len(inputs.facts.outside) else set()
    for earlier_rows, what in ((loads, "har leveranser som fördelats"), (harvest, "har skördardata från")):
        known = sorted(outside & set(earlier_rows[AO].astype(str))) if earlier_rows is not None and len(earlier_rows) else []
        if known:
            listed = ", ".join(known[:5]) + (f" och {len(known) - 5} till" if len(known) > 5 else "")
            found.append((FEL, f"{len(known)} avtalsobjekt är märkta {OUTSIDE} men {what} en tidigare månad: {listed}. "
                               f"Sätt {OUTSIDE} ur avtalsobjektets typ, aldrig för att skördardata saknas"))

    if harvest is not None and len(harvest) and len(inputs.harvest):
        harvest[VOL] = pd.to_numeric(harvest[VOL])
        previous = _harvest_key(harvest)
        current = _harvest_key(inputs.harvest)
        common = [c for c in current.columns if c in previous.columns]
        repeated = current[common].merge(previous[common].drop_duplicates(), on=common, how="inner")
        share = float(repeated[VOL].astype(float).sum()) / float(inputs.harvest[VOL].sum())
        if share > CUMULATIVE_SHARE:
            found.append((FEL, f"{share:.0%} av skördarvolymen är rader som skickades redan {previous_period(period)}. "
                               "Skördardatan ser kumulativ ut och skulle räknas två gånger; skicka bara månadens nya "
                               "rader, till exempel med treedist.adapters.snapshot.new_rows"))
        elif share > REPEATED_SHARE:
            found.append((OBS, f"{share:.0%} av skördarvolymen är rader som är exakt lika rader från "
                               f"{previous_period(period)}; kontrollera att skördardatan bara har månadens nya rader"))

    earlier_run = json.loads((before / RUN).read_text(encoding="utf-8")) if (before / RUN).exists() else None
    if earlier_run is not None:
        now = json.loads(json.dumps(_run(cfg, layout)))
        # Only what this run reads: a month saved before the Monte Carlo left the run also lists its parameters.
        changed = sorted(k for k in now["modell"] if now["modell"][k] != earlier_run["modell"].get(k, now["modell"][k]))
        scale = [k for k in changed if k in CALIBRATION]
        if scale and not new_calibration:
            values = ", ".join(f"{k} {earlier_run['modell'].get(k)} → {now['modell'].get(k)}" for k in scale)
            found.append((FEL, f"kalibreringen har ändrats sedan {previous_period(period)} ({values}). Liggarens lager är "
                               "kalibrerat med den gamla, så lagret skulle blanda två skalor. Kör med samma modell, "
                               "eller kör om historiken med den nya; --tillat-ny-kalibrering kör ändå"))
        others = [k for k in changed if k not in CALIBRATION]
        if others or scale:
            found.append((OBS, f"modellens parametrar har ändrats sedan {previous_period(period)}: "
                               f"{', '.join(scale + others)}; kontrollera att ändringen är avsedd"))
        # `check` has no groups to compare: it does not write appendices.
        if layout is not None and now["bilaga"] != earlier_run["bilaga"]:
            found.append((OBS, f"bilagans grupper har ändrats sedan {previous_period(period)}; samma grupper varje "
                               "månad gör bilagorna jämförbara"))

    closed = _read(before / CLOSED)
    if closed is not None and len(closed):
        delivering = deliveries.groupby(AO)[VOL].sum()
        again = sorted(set(delivering[delivering > 0].index) & set(closed[AO]))
        # A delivery driven by the end of the month its avtalsobjekt was written off was measured after it: the stock
        # was written off before the delivery came, and transport_avslutad was set too early.
        closing = closed.drop_duplicates(AO).set_index(AO)["period"]
        driven = deliveries[deliveries[AO].isin(again) & (deliveries[VOL] > 0)]
        closed_end = driven[AO].map(lambda ao: period_bounds(closing[ao])[1])
        early = sorted(set(driven.loc[driven["leveransdatum"].dt.normalize() <= closed_end, AO]))
        later = [ao for ao in again if ao not in early]

        def listed(aos: list[str]) -> str:
            return ", ".join(aos[:5]) + (f" och {len(aos) - 5} till" if len(aos) > 5 else "")

        if early:
            found.append((OBS, f"{len(early)} avtalsobjekt skrevs av innan alla deras leveranser var inmätta: "
                               f"{listed(early)} har leveranser som kördes senast den månad de skrevs av. Lagret är "
                               "avskrivet, så leveranserna fördelas som avtalsobjektets hela skörd, en uppskattning. Sattes "
                               "transport_avslutad för tidigt?"))
        if later:
            found.append((OBS, f"{len(later)} avtalsobjekt som skrivits av levererar igen: {listed(later)}. Lagret är "
                               "avskrivet, så leveranserna fördelas som avtalsobjektets hela skörd, en uppskattning; "
                               "stämmer transport_avslutad?"))
    return found


def save(state: Path, period: str, inputs, cfg: Config, layout, closed_now: frozenset[str] = frozenset()) -> None:
    """Write the month's files next to its ledger, carrying the avtalsobjekt written off in earlier months and adding
    `closed_now`, those written off after this one. The deliveries are the ledger's."""
    target = state / period
    target.mkdir(parents=True, exist_ok=True)
    before = state / previous_period(period)

    inputs.harvest[HARVEST_COLUMNS].to_csv(target / HARVEST, index=False)
    (target / RUN).write_text(json.dumps(_run(cfg, layout), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    closed = _read(before / CLOSED)
    frames = [closed] if closed is not None else []
    frames.append(pd.DataFrame({AO: sorted(closed_now), "period": period}))
    pd.concat(frames, ignore_index=True).drop_duplicates(AO, keep="first").to_csv(target / CLOSED, index=False)
