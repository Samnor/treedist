"""Does a source's data fit the contract, and does it look right?

A mapping can be valid in form and wrong in meaning: millimetres read as
centimetres, gross and net swapped, the accounting date taken for the transport
date. Validation stops the first kind. These checks look for the second, by
comparing the data with what Swedish sawlog flows look like, and by running the
month without saving anything to see where the volume ends up.

Each finding says what to look at. FEL stops a run; VARNING needs a person to
judge it; INFO is worth knowing but asks nothing; OK says a check passed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import sent
from .adapters import Raw, read_raw, validate
from .config import Config
from .contract import STEM, TABLES
from .core.allocate import CERTAINTY_TIERS, BrokenAssumption, close_month
from .core.ledger import Ledger, previous_period
from .schema import (AO, BRUTTO, DEST, DIA, LANDING, LEN, LOAD_ID, LOGS, NO_DESTINATION, PRODUCED, PRODUCED_FOR, SORT,
                     VINTAGE, VOL)

FEL, VARNING, INFO, OK = "FEL", "VARNING", "INFO", "OK"
# A closed contract object whose delivered and harvested volume differ by more than this.
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
        inputs = validate(raw, period)
    except ValueError as error:
        return findings + [Finding(FEL, "validering", str(error))]
    findings.append(Finding(OK, "validering", "alla tabeller följer kontraktet"))

    findings += _classes(inputs.harvest)
    findings += _midpoints(inputs.harvest)
    findings += _harvest_logs(inputs.harvest)
    findings += _gross_and_net(inputs.deliveries)
    findings += _loads(inputs.deliveries)
    findings += _unit_counts(raw.get("matning"))
    findings += _dates(inputs.harvest, inputs.deliveries)
    findings += _late(inputs.deliveries, period)
    findings += _destinations(inputs)
    findings += _no_value(inputs)
    if outside_text(inputs):
        findings.append(Finding(INFO, "matning", outside_text(inputs)))
    findings += _stems(raw.get("avverkningsformer"), inputs)

    ledger = None
    if state is not None and (state / previous_period(period)).exists():
        # Read only: later snapshots may exist, the check never writes.
        ledger = Ledger.load(state, previous_period(period))
    elif state is not None and not any(state.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]")):
        # A new ledger: the run would start from nothing, so the check does too.
        ledger = Ledger.empty()
    findings += _dry_run(inputs, period, cfg, ledger)
    if state is not None:
        # What a run would refuse or point out, from the files earlier months left beside the ledger.
        for level, text in sent.problems(state, period, inputs, cfg):
            findings.append(Finding(FEL if level == sent.FEL else VARNING, "tidigare månader", text))
    return findings


def _form(raw: Raw) -> list[Finding]:
    findings = []
    for key, frame in raw.items():
        if key not in TABLES:
            findings.append(Finding(VARNING, key, "tabellen finns inte i kontraktet och används inte"))
            continue
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


def _stems(measures: pd.DataFrame | None, inputs) -> list[Finding]:
    """Mean stem volumes that look like another unit."""
    if measures is None or STEM not in measures.columns:
        return []
    spec = TABLES["avverkningsformer"].column(STEM)
    numbers = pd.to_numeric(measures[STEM].astype(str).str.replace(",", ".", regex=False), errors="coerce").dropna()
    if not len(numbers):
        return []
    median = float(numbers.median())
    if median > spec.high:
        return [Finding(VARNING, "avverkningsformer", f"{STEM} har median {median:g}: ser ut som dm3, sätt enheter.{STEM} = 0.001")]
    if median < spec.low:
        return [Finding(VARNING, "avverkningsformer", f"{STEM} har median {median:g} m3fub: orimligt liten medelstam")]
    return [Finding(OK, "avverkningsformer", f"{STEM}: median {median:g} m3fub")]


def _numeric_classes(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").dropna()


def _midpoints(harvest: pd.DataFrame) -> list[Finding]:
    """A class is named by its bottom: a whole cm, and an even one when classes are 2 cm wide.

    Every class on a half cm is the middles of 1 cm classes; every class odd and 2 cm apart, of 2 cm classes."""
    classes = sorted(set(_numeric_classes(harvest[DIA])))
    if len(classes) < 3:
        return []
    if all(c % 1 == 0.5 for c in classes):
        shown = ", ".join(f"{c:g}".replace(".", ",") for c in classes[:3])
        return [Finding(VARNING, "produktion", f"{DIA} har bara klasser på halva cm ({shown} …); klasser börjar på "
                        "hela cm. Är det klassmitt i stället för nedre gräns?")]
    if any(c != int(c) for c in classes):
        return []
    steps = pd.Series(classes).diff().dropna()
    if steps.mode().iloc[0] == 2 and all(int(c) % 2 == 1 for c in classes):
        shown = ", ".join(f"{c:g}" for c in classes[:3])
        return [Finding(VARNING, "produktion", f"{DIA} har bara udda klasser 2 cm isär ({shown} …); klasser börjar på "
                        "jämna cm. Är det klassmitt i stället för nedre gräns?")]
    return []


def _classes(harvest: pd.DataFrame) -> list[Finding]:
    findings = []
    hints = {
        DIA: ("ser ut som mm, sätt enheter.diameterklass = 0.1", "ser ut som dm, sätt enheter.diameterklass = 10"),
        LEN: ("ser ut som mm, sätt enheter.langdklass = 0.1", "ser ut som dm eller m, sätt enheter.langdklass = 10 eller 100"),
    }
    for column in (DIA, LEN):
        spec = TABLES["produktion"].column(column)
        numbers = _numeric_classes(harvest[column])
        if numbers.empty:
            continue
        median = float(numbers.median())
        if median > spec.high:
            findings.append(Finding(VARNING, "produktion", f"{column} har median {median:g} {spec.unit}: {hints[column][0]}"))
        elif median < spec.low:
            findings.append(Finding(VARNING, "produktion", f"{column} har median {median:g} {spec.unit}: {hints[column][1]}"))
        else:
            outside = ((numbers < spec.low) | (numbers > spec.high)).mean()
            level = VARNING if outside > 0.01 else OK
            findings.append(
                Finding(level, "produktion", f"{column}: median {median:g} {spec.unit}, {outside:.1%} utanför {spec.low:g}–{spec.high:g}")
            )
    return findings


def _harvest_logs(harvest: pd.DataFrame) -> list[Finding]:
    counted = harvest[harvest[LOGS] > 0]
    if counted.empty:
        return [Finding(VARNING, "produktion", "antal_stockar saknas; osäkerheten skattas då grövre")]
    per_log = float(counted[VOL].sum() / counted[LOGS].sum())
    if not 0.02 <= per_log <= 2.0:
        return [Finding(VARNING, "produktion", f"{per_log:.3g} m3fub per stock är orimligt; är volymen i dm3, eller antalet fel kolumn?")]
    # A cylinder on the class bottoms; real logs taper and sit above the bottom, so about 1.3 times that.
    diameters = pd.to_numeric(counted[DIA], errors="coerce") / 100
    lengths = pd.to_numeric(counted[LEN], errors="coerce") / 100
    sized = diameters.notna() & lengths.notna()
    cylinders = float((np.pi / 4 * diameters[sized] ** 2 * lengths[sized] * counted.loc[sized, LOGS]).sum())
    if cylinders > 0:
        ratio = float(counted.loc[sized, VOL].sum()) / cylinders
        if not 0.7 <= ratio <= 2.5:
            return [Finding(VARNING, "produktion", f"volymen är {ratio:.2g} gånger vad klasserna och antalet stockar ger, "
                            "normalt cirka 1,3; är volym, antal stockar eller klasserna fel kolumn eller enhet?")]
    return [Finding(OK, "produktion", f"{per_log:.3f} m3fub per stock, i linje med klasserna")]


def _gross_and_net(deliveries: pd.DataFrame) -> list[Finding]:
    ratio = float(deliveries[VOL].sum() / deliveries[BRUTTO].sum())
    if len(deliveries) >= 10 and (deliveries[VOL] == deliveries[BRUTTO]).all():
        return [Finding(VARNING, "matning", "brutto är lika med netto på varje rad; är brutto_m3fub mappad till nettokolumnen?")]
    if ratio < 0.85:
        return [Finding(VARNING, "matning", f"netto är {ratio:.1%} av brutto; normalt 95–100 %. Är det fub och fub, och rätt kolumner?")]
    return [Finding(OK, "matning", f"netto är {ratio:.1%} av brutto")]


def _unit_counts(raw: pd.DataFrame | None) -> list[Finding]:
    """A count is never negative; a reversing row is easily given the volume's sign on every number.

    Read from the raw table: validation replaces counts that are not positive with the method's default.
    """
    if raw is None or "antal_matenheter" not in raw.columns:
        return []
    counts = pd.to_numeric(raw["antal_matenheter"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    negative = int((counts < 0).sum())
    if negative:
        return [Finding(FEL, "matning", f"antal_matenheter är negativt på {negative} rader; antalet är alltid positivt, "
                        "också på en rad som vänder ett lass. Bara volymerna byter tecken")]
    return []


def _loads(deliveries: pd.DataFrame) -> list[Finding]:
    """A truck carries about 40 m3fub of sawlogs; far from that the unit or the rows are wrong."""
    findings = []
    # Reversed loads and what was booked again under their ids are judged in the dry run instead.
    reversed_ids = set(deliveries.loc[deliveries[VOL] < 0, "leveransnummer"])
    deliveries = deliveries[~deliveries["leveransnummer"].isin(reversed_ids)]
    if deliveries.empty:
        return []
    per_load = deliveries.groupby("leveransnummer")[BRUTTO].sum()
    median = float(per_load.median())
    if not 2 <= median <= 100:
        findings.append(
            Finding(VARNING, "matning", f"median {median:.4g} m3fub per lass, normalt 20–60; är volymen i dm3 eller m3?")
        )
    # Two trucks rarely carry the same volume to the litre from the same contract object on the same day.
    same = [AO, SORT, DEST, "leveransdatum", VOL, BRUTTO]
    copies = int(deliveries.duplicated(same).sum())
    if copies:
        findings.append(
            Finding(VARNING, "matning", f"{copies} lass är kopior av andra lass med annat id; saknas ett filter på status, "
                    "till exempel makulerade lass?")
        )
    return findings or [Finding(OK, "matning", f"median {median:.1f} m3fub per lass, inga kopior")]


def _late(deliveries: pd.DataFrame, period: str) -> list[Finding]:
    """Loads driven in an earlier month are invoiced now, when they were measured in this month or reached the
    source late. A source selected on the delivery date would never send them, so a person should see that they do
    come."""
    start = pd.Period(period, freq="M").start_time

    def months(dates: pd.Series) -> str:
        return ", ".join(sorted(dates.dt.strftime("%Y-%m").unique()))

    late = deliveries[deliveries["leveransdatum"] < start]
    findings = []
    measured_now = late[late["matdatum"] >= start]
    if len(measured_now):
        findings.append(Finding(INFO, "matning", f"{len(measured_now)} lass, {measured_now[VOL].sum():.1f} m3fub, kördes "
                                f"före perioden ({months(measured_now['leveransdatum'])}) och mättes in i perioden; de "
                                "faktureras nu"))
    measured_before = deliveries[deliveries["matdatum"] < start]
    if len(measured_before):
        findings.append(Finding(INFO, "matning", f"{len(measured_before)} lass, {measured_before[VOL].sum():.1f} m3fub, "
                                f"mättes in före perioden ({months(measured_before['matdatum'])}) och faktureras "
                                "nu; de kom till källan efter förra körningen"))
    return findings


def _dates(harvest: pd.DataFrame, deliveries: pd.DataFrame) -> list[Finding]:
    findings = []
    days = deliveries["leveransdatum"].dt.normalize()
    if days.nunique() <= 3 and len(deliveries) > 20:
        findings.append(
            Finding(VARNING, "matning", f"bara {days.nunique()} olika leveransdatum; är det ett redovisnings- eller mätdatum i stället för dagen "
                    "lasset kördes?")
        )
    first = pd.to_datetime(harvest.groupby(AO)[VINTAGE].min())
    started = deliveries[AO].map(first)
    early = deliveries[started.notna() & (days < started)]
    share = float(early[VOL].sum() / deliveries[VOL].sum()) if len(deliveries) else 0.0
    if share > 0.05:
        findings.append(
            Finding(VARNING, "matning", f"{share:.1%} av volymen levererades före avtalsobjektets första avverkningsdag; fel datum eller "
                    "avtalsobjekt?")
        )
    elif not findings:
        findings.append(Finding(OK, "matning", "leveransdatum följer efter avverkningen"))
    return findings


def outside_text(inputs) -> str:
    """How much of the month's measured wood comes from no harvest and is left out of every matrix; empty when none."""
    outside = inputs.facts.outside
    if not len(outside):
        return ""
    apart, inside = float(outside[VOL].sum()), float(inputs.deliveries[VOL].sum())
    alone = sorted(set(outside[DEST]) - set(inputs.deliveries[DEST]))
    share = f", {apart / (apart + inside):.0%} av mätningen" if apart + inside > 0 else ""
    return (f"{apart:.1f} m3fub{share}, är märkt utan_avverkning och fördelas inte. Bilagan anger volymen utanför "
            "matrisen"
            + (f". Mottagningsplatser som bara fick sådant virke får ingen bilaga: {', '.join(alone[:5])}"
               + (f" och {len(alone) - 5} till" if len(alone) > 5 else "") if alone else ""))


def _destinations(inputs) -> list[Finding]:
    """Most wood is measured at the mottagningsplats it was produced for, and the ids are the production's: if they
    hardly meet, a column is mapped from the wrong one, or written another way."""
    deliveries, harvest = inputs.deliveries, inputs.harvest
    total = float(deliveries[VOL].abs().sum())
    if total <= 0:
        return []
    findings = []
    same = float(deliveries.loc[deliveries[DEST] == deliveries[PRODUCED_FOR], VOL].abs().sum()) / total
    if same < 0.5:
        findings.append(Finding(VARNING, "matning", f"bara {same:.0%} av volymen mättes in vid den mottagningsplats den "
                                "producerades för. Är mottagningsplats eller producerat_for_mottagningsplats mappad från "
                                "fel kolumn?"))
    else:
        findings.append(Finding(OK, "matning", f"{same:.0%} av volymen mättes in där den producerades för"))
    known = set(harvest[PRODUCED_FOR]) - {NO_DESTINATION}
    unknown = sorted(set(deliveries[PRODUCED_FOR]) - known)
    if unknown and known:
        share = float(deliveries.loc[deliveries[PRODUCED_FOR].isin(unknown), VOL].abs().sum()) / total
        findings.append(Finding(VARNING, "matning", f"{share:.0%} av volymen är producerad för en mottagningsplats som "
                                f"inte finns i månadens produktion: {unknown[:3]}, produktionen har {sorted(known)[:3]}. "
                                "Skrivs id olika i produktion och mätning?"))
    return findings + _without_destination(inputs)


def _without_destination(inputs) -> list[Finding]:
    """Harvest reported without the mottagningsplats it was produced for, which hpr leaves optional. It is taken by
    the avtalsobjekt's loads once their own stock is empty, which is right where an assortment has one mill; where it
    is cut for several, which mill the wood was for is not known."""
    harvest, deliveries = inputs.harvest, inputs.deliveries
    total = float(harvest[VOL].sum())
    missing = harvest[harvest[PRODUCED_FOR] == NO_DESTINATION]
    if total <= 0 or missing.empty:
        return []
    findings = [Finding(INFO, "produktion", f"{float(missing[VOL].sum()) / total:.0%} av volymen saknar producerat för "
                        "mottagningsplats. Det virket tas av avtalsobjektets lass när deras egna lager är slut")]
    mills = deliveries.groupby([AO, PRODUCED])[PRODUCED_FOR].nunique()
    shared = missing.merge(mills[mills > 1].rename("mills"), left_on=[AO, PRODUCED], right_index=True)
    if len(shared):
        findings.append(Finding(VARNING, "produktion", f"{float(shared[VOL].sum()) / total:.0%} av volymen saknar "
                                "producerat för mottagningsplats i avtalsobjekt och sortiment vars lass är producerade "
                                f"för flera mottagningsplatser, till exempel {sorted(set(shared[AO]))[:3]}. Där går det "
                                "inte att veta vilken mottagningsplats virket kapades för, och lassen delar på det. "
                                "Hämta uppgiften ur VIOL 3 om den finns"))
    return findings


# What a source writes where it has no value: a data warehouse's key for a missing row (-1, 0) or a word for it. An
# empty value stops the month; one of these is read as an id, and the wood is booked on a stock, an avtalsobjekt or a
# mill that does not exist.
NO_VALUE = re.compile(r"-\d+|0+|-+|\?+|#?n/?a|nan|null|none|nil|saknas|okänd|okand|unknown|missing|ej angiven",
                      re.IGNORECASE)


def _no_value(inputs) -> list[Finding]:
    findings = []
    tables = (("produktion", inputs.harvest, [AO, PRODUCED, PRODUCED_FOR, LANDING]),
              ("matning", inputs.deliveries, [LOAD_ID, AO, SORT, PRODUCED, DEST, PRODUCED_FOR, LANDING]))
    for table, frame, columns in tables:
        total = float(frame[VOL].abs().sum())
        for column in columns:
            text = frame[column].astype(str).str.strip()
            # The validation writes its own mark where an optional place is missing.
            optional = column == LANDING or (table == "produktion" and column == PRODUCED_FOR)
            hit = text.str.fullmatch(NO_VALUE) & ~(optional & (text == NO_DESTINATION))
            if not hit.any():
                continue
            share = f", {float(frame.loc[hit, VOL].abs().sum()) / total:.0%} av volymen" if total > 0 else ""
            values = ", ".join(repr(v) for v in sorted(set(text[hit]))[:3])
            findings.append(Finding(VARNING, table, f"{column} är {values} på {int(hit.sum())} rader{share}. Det ser ut "
                                    "som källans värde för en uppgift som saknas, och treedist läser det som ett id: "
                                    "virket bokas på ett lager, ett avtalsobjekt eller en mottagningsplats som inte "
                                    "finns. Gör värdet tomt i källan: då stoppar kontrollen där uppgiften krävs, och skörd utan producerat "
                                        "för mottagningsplats tas av avtalsobjektets lass när deras egna lager är slut"))
    return findings


# Above this share of the delivered volume estimated by the day method although later wood was in the stock, the
# dates are more likely wrong than the wood missing.
FELLED_AFTER_SHARE = 0.05


def felled_after_text(felled_after: dict, delivered: float) -> str:
    """What the day method estimated although wood felled after the loads lay in the stock: the dates to look at."""
    late = sum(felled_after.values())
    largest = sorted(felled_after.items(), key=lambda item: -item[1])[:5]
    listed = ", ".join(f"{ao} {sortiment} {volume:.1f}" for (ao, sortiment), volume in largest)
    share = f" ({late / delivered:.1%} av leveransen)" if delivered > 0 else ""
    return (f"dagmetoden: {late:.1f} m3fub{share} kördes innan skördaren hade avverkat nog och är uppskattning, fast "
            f"virke som avverkades senare i månaden låg kvar i lagret: {listed}. Är avverkningsdatum rapportdagen, "
            "eller leveransdatum en annan dag än transporten, till exempel i UTC?")


def _dry_run(inputs, period: str, cfg: Config, ledger) -> list[Finding]:
    """Close the month without saving, and see where the delivered volume found its distribution."""
    start = ledger or Ledger.empty()
    if start.period is not None and start.period >= period:
        return [Finding(VARNING, "provkörning", f"liggaren är redan stängd för {start.period}; provkörningen hoppas över")]
    try:
        step = close_month(start, inputs.harvest, inputs.deliveries, period, inputs.transport_done, cfg)
    except BrokenAssumption as error:
        if ledger is not None:
            return [Finding(FEL, "provkörning", str(error))]
        # Without earlier months the check cannot tell a load without harvester data from one harvested before the period.
        return [Finding(VARNING, "provkörning", f"{error}. Provkörningen har ingen liggare: skördardata och fakturor från "
                        "tidigare månader saknas här. Kör med --state för att pröva månaden mot liggaren")]
    except ValueError as error:
        return [Finding(FEL, "provkörning", str(error))]
    findings = []
    volume = step.allocation.groupby("sakerhetsklass")[VOL].sum().reindex(list(CERTAINTY_TIERS), fill_value=0.0)
    total = float(volume.sum())
    if total > 0:
        shares = ", ".join(f"{t} {v / total:.0%}" for t, v in volume.items())
        findings.append(Finding(OK, "provkörning", f"levererad volym per säkerhetsklass: {shares}"))
        if len(step.credits):
            credited = -float(step.credits[VOL].sum())
            reversed_rows = int((inputs.deliveries[VOL] < 0).sum())
            findings.append(
                Finding(INFO, "provkörning", f"{reversed_rows} negativa rader; {credited:.0f} m3fub krediteras som lass "
                        "fakturerade tidigare månader")
            )

    if step.felled_after:
        delivered = float(inputs.deliveries.loc[inputs.deliveries[VOL] > 0, VOL].sum())
        late = sum(step.felled_after.values())
        level = VARNING if delivered > 0 and late / delivered > FELLED_AFTER_SHARE else INFO
        findings.append(Finding(level, "provkörning", felled_after_text(step.felled_after, delivered)))

    closed = step.reconciliation[step.reconciliation[AO].isin(step.closed)]
    harvested = step.ledger.history.groupby([AO, PRODUCED])[VOL].sum()
    if len(closed):
        keys = list(zip(closed[AO], closed[PRODUCED]))
        base = np.array([harvested.get(k, 0.0) for k in keys])
        gap = (closed["avskrivet"].to_numpy() + closed["avskrivet_underskott"].to_numpy()) / np.where(base > 0, base, np.nan)
        off = int(np.sum(gap > MAX_CLOSING_GAP))
        level = VARNING if off else OK
        findings.append(
            Finding(level, "provkörning", f"{off} av {len(keys)} avskrivna avtalsobjekt och sortiment skiljer mer än "
                    f"{MAX_CLOSING_GAP:.0%} mellan skördat och levererat")
        )
    return findings
