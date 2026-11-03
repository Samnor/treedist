"""Does a source's data fit the contract, and does it look right?

A mapping can be valid in form and wrong in meaning: millimetres read as
centimetres, gross and net swapped, the accounting date taken for the transport
date. Validation stops the first kind. These checks look for the second, by
comparing the data with what Swedish sawlog flows look like, and by running the
month without saving anything to see where the volume ends up.

Each finding says what to look at. FEL stops a run; VARNING needs a person to
judge it; OK says a check passed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .adapters import Raw, read_raw, validate
from .config import Config
from .contract import TABLES
from .core.allocate import CERTAINTY_TIERS, close_month
from .core.ledger import Ledger, previous_period
from .schema import AO, BRUTTO, DIA, LEN, LOGS, SORT, VINTAGE, VOL

FEL, VARNING, OK = "FEL", "VARNING", "OK"
# More delivered volume than this without harvester data nearly doubled the price error in simulation.
MAX_UNBACKED_SHARE = 0.30
# A closed work order whose delivered and harvested volume differ by more than this.
MAX_CLOSING_GAP = 0.15


@dataclass(frozen=True)
class Finding:
    level: str
    table: str
    message: str

    def __str__(self) -> str:
        return f"{self.level:7s} {self.table:12s} {self.message}"


def check(
    period: str,
    cfg: Config,
    source: Path | None = None,
    files: dict[str, Path | None] | None = None,
    state: Path | None = None,
) -> list[Finding]:
    try:
        raw, _ = read_raw(period, source, files)
    except (ValueError, FileNotFoundError) as error:
        return [Finding(FEL, "källa", str(error))]

    findings = _form(raw)
    if any(f.level == FEL for f in findings):
        return findings
    try:
        inputs = validate(raw, period, cfg)
    except ValueError as error:
        return findings + [Finding(FEL, "validering", str(error))]
    findings.append(Finding(OK, "validering", "alla tabeller följer kontraktet"))

    findings += _classes(inputs.harvest)
    findings += _harvest_logs(inputs.harvest)
    findings += _gross_and_net(raw.get("leverans"), inputs.deliveries)
    findings += _dates(inputs.harvest, inputs.deliveries)
    findings += _prices(inputs)

    ledger = None
    if state is not None and (state / previous_period(period)).exists():
        # Read only: later snapshots may exist, the check never writes.
        ledger = Ledger.load(state, previous_period(period))
    findings += _dry_run(inputs, period, cfg, ledger)
    return findings


def _form(raw: Raw) -> list[Finding]:
    findings = []
    for key, frame in raw.items():
        table = TABLES[key]
        missing = [c for c in table.required if c not in frame.columns]
        if missing:
            findings.append(Finding(FEL, key, f"obligatoriska kolumner saknas: {missing}"))
        extra = [c for c in frame.columns if c not in {c.name for c in table.columns}]
        if extra:
            findings.append(Finding(VARNING, key, f"kolumnerna {extra} finns inte i kontraktet och används inte"))
        if frame.empty:
            findings.append(Finding(VARNING, key, "tabellen är tom"))
    return findings


def _numeric_classes(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").dropna()


def _classes(harvest: pd.DataFrame) -> list[Finding]:
    findings = []
    hints = {
        DIA: ("ser ut som mm, sätt enheter.diametergrupp = 0.1", "ser ut som dm, sätt enheter.diametergrupp = 10"),
        LEN: ("ser ut som mm, sätt enheter.langdgrupp = 0.1", "ser ut som dm eller m, sätt enheter.langdgrupp = 10 eller 100"),
    }
    for column in (DIA, LEN):
        spec = TABLES["skordning"].column(column)
        numbers = _numeric_classes(harvest[column])
        if numbers.empty:
            continue
        median = float(numbers.median())
        if median > spec.high:
            findings.append(Finding(VARNING, "skordning", f"{column} har median {median:g} {spec.unit}: {hints[column][0]}"))
        elif median < spec.low:
            findings.append(Finding(VARNING, "skordning", f"{column} har median {median:g} {spec.unit}: {hints[column][1]}"))
        else:
            outside = ((numbers < spec.low) | (numbers > spec.high)).mean()
            level = VARNING if outside > 0.01 else OK
            findings.append(
                Finding(level, "skordning", f"{column}: median {median:g} {spec.unit}, {outside:.1%} utanför {spec.low:g}–{spec.high:g}")
            )
    return findings


def _harvest_logs(harvest: pd.DataFrame) -> list[Finding]:
    counted = harvest[harvest[LOGS] > 0]
    if counted.empty:
        return [Finding(VARNING, "skordning", "antal_stockar saknas; osäkerheten skattas då grövre")]
    per_log = float(counted[VOL].sum() / counted[LOGS].sum())
    if not 0.02 <= per_log <= 2.0:
        return [Finding(VARNING, "skordning", f"{per_log:.3g} m3fub per stock är orimligt; är volymen i dm3, eller antalet fel kolumn?")]
    return [Finding(OK, "skordning", f"{per_log:.3f} m3fub per stock")]


def _gross_and_net(raw: pd.DataFrame | None, deliveries: pd.DataFrame) -> list[Finding]:
    if raw is None or BRUTTO not in raw.columns:
        return [Finding(VARNING, "leverans", "brutto_m3fub saknas; lagret minskas då med nettovolymen")]
    ratio = float(deliveries[VOL].sum() / deliveries[BRUTTO].sum())
    if ratio < 0.85:
        return [Finding(VARNING, "leverans", f"netto är {ratio:.1%} av brutto; normalt 95–100 %. Är det fub och fub, och rätt kolumner?")]
    return [Finding(OK, "leverans", f"netto är {ratio:.1%} av brutto")]


def _dates(harvest: pd.DataFrame, deliveries: pd.DataFrame) -> list[Finding]:
    findings = []
    days = deliveries["leveransdatum"].dt.normalize()
    if days.nunique() <= 3 and len(deliveries) > 20:
        findings.append(
            Finding(VARNING, "leverans", f"bara {days.nunique()} olika leveransdatum; är det redovisningsdatum i stället för transportdatum?")
        )
    first = pd.to_datetime(harvest.groupby(AO)[VINTAGE].min())
    started = deliveries[AO].map(first)
    early = deliveries[started.notna() & (days < started)]
    share = float(early[VOL].sum() / deliveries[VOL].sum()) if len(deliveries) else 0.0
    if share > 0.05:
        findings.append(
            Finding(VARNING, "leverans", f"{share:.1%} av volymen levererades före arbetsorderns första avverkningsdag; byt datum eller arbetsorder-id?")
        )
    elif not findings:
        findings.append(Finding(OK, "leverans", "leveransdatum följer efter avverkningen"))
    return findings


def _prices(inputs) -> list[Finding]:
    findings = []
    priced = inputs.prices.rules
    unpriced = sorted(set(inputs.deliveries[SORT]) - set(priced))
    if unpriced:
        findings.append(Finding(VARNING, "prislista", f"sortiment utan pris: {unpriced}"))
    harvest = inputs.harvest
    missing = harvest[
        [inputs.prices.price_ore(s, d, l) is None for s, d, l in zip(harvest[SORT], harvest[DIA], harvest[LEN])]
    ]
    share = float(missing[VOL].sum() / harvest[VOL].sum()) if len(harvest) else 0.0
    if share > 0.01:
        findings.append(Finding(VARNING, "prislista", f"{share:.1%} av skördad volym hamnar i klasser utan pris"))
    elif not findings:
        findings.append(Finding(OK, "prislista", "alla sortiment och klasser har pris"))
    return findings


def _dry_run(inputs, period: str, cfg: Config, ledger) -> list[Finding]:
    """Close the month without saving, and see where the delivered volume found its distribution."""
    start = ledger or Ledger.empty()
    if start.period is not None and start.period >= period:
        return [Finding(VARNING, "provkörning", f"liggaren är redan stängd för {start.period}; provkörningen hoppas över")]
    step = close_month(start, inputs.harvest, inputs.deliveries, period, inputs.closed_aos, cfg, inputs.work_orders)
    findings = []
    volume = step.allocation.groupby("sakerhetsklass")[VOL].sum().reindex(list(CERTAINTY_TIERS), fill_value=0.0)
    total = float(volume.sum())
    if total > 0:
        shares = ", ".join(f"{t} {v / total:.0%}" for t, v in volume.items())
        unbacked = float(volume[["S3", "S4"]].sum() / total)
        level = VARNING if unbacked > MAX_UNBACKED_SHARE else OK
        hint = "; matchar arbetsorder-id och sortiment mellan skördardata och inmätning?" if level == VARNING else ""
        findings.append(Finding(level, "provkörning", f"levererad volym per säkerhetsklass: {shares}{hint}"))
        if start.period is None:
            findings.append(Finding(VARNING, "provkörning", "ingen liggare (--state); virke skördat före perioden blir S3/S4"))

    closed = step.reconciliation[step.reconciliation[AO].isin(inputs.closed_aos)]
    harvested = step.ledger.history.groupby([AO, SORT])[VOL].sum()
    if len(closed):
        keys = list(zip(closed[AO], closed[SORT]))
        base = np.array([harvested.get(k, 0.0) for k in keys])
        gap = (closed["avskrivet"].to_numpy() + closed["underskott"].to_numpy()) / np.where(base > 0, base, np.nan)
        off = int(np.sum(gap > MAX_CLOSING_GAP))
        level = VARNING if off else OK
        findings.append(
            Finding(level, "provkörning", f"{off} av {len(keys)} avslutade arbetsordrar och sortiment skiljer mer än "
                    f"{MAX_CLOSING_GAP:.0%} mellan skördat och levererat")
        )
    return findings
