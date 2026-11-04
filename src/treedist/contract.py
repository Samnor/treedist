"""The canonical input tables, as data.

Everything the method reads comes through these five tables. A new source
system is connected by an adapter that produces them (see adapters/), never by
changing the method. `treedist kontrakt` prints this as a table, and
`treedist check` tests an adapter's output against it, including whether the
values are plausible: a mapping can be valid in form and still wrong in meaning.

Column names are Swedish since they mirror the source systems.
"""

from __future__ import annotations

from dataclasses import dataclass

# Raised when a table changes in a way that old ledgers or adapters cannot follow.
CONTRACT_VERSION = 1

AO = "arbetsorder"
SORT = "handelssortiment"
PRODUCED = "producerat_handelssortiment"
BILLED = "fakturerat_handelssortiment"
DIA = "diametergrupp"
LEN = "langdgrupp"
VOL = "volym_m3fub"
BRUTTO = "brutto_m3fub"
DEST = "destination"
LOGS = "antal_stockar"
VINTAGE = "avverkningsdatum"
TIER = "sakerhetsklass"

NO_CLASS = "-"
NO_DESTINATION = "-"
UNKNOWN_CLASS = "OKÄND"

MEASURING_METHODS = ("stockmatning", "travmatning", "vagning", "skordarmatning", "okand")


@dataclass(frozen=True)
class Column:
    name: str
    kind: str  # text, tal, klass, datum
    required: bool
    meaning: str
    unit: str = ""
    # Plausible range for numbers and numeric classes; outside it `check` warns.
    low: float | None = None
    high: float | None = None


@dataclass(frozen=True)
class Table:
    name: str
    meaning: str
    columns: tuple[Column, ...]
    # An optional table may be left out of a source; the meaning says what is lost.
    optional: bool = False

    @property
    def required(self) -> list[str]:
        return [c.name for c in self.columns if c.required]

    def column(self, name: str) -> Column:
        return next(c for c in self.columns if c.name == name)


TABLES = {
    "skordning": Table(
        "Skördardata",
        "Skördarens produktionsrapportering: månadens nya rader, en rad per arbetsorder, sortiment, klass och dag.",
        (
            Column(AO, "text", True, "Arbetsorderns id, samma som i inmätningen"),
            Column(SORT, "text", True, "Handelssortimentet skördaren producerade"),
            Column(DIA, "klass", True, "Diameterklassens nedre gräns. Tom för sortiment utan klasser", "cm", 5, 80),
            Column(LEN, "klass", True, "Längdklassens nedre gräns. Tom för sortiment utan klasser", "cm", 150, 800),
            Column(VOL, "tal", True, "Skördarens volym under bark", "m3fub", 0, None),
            Column(LOGS, "tal", False, "Antal stockar. Ger bättre osäkerhetsskattning", "st", 0, None),
            Column(VINTAGE, "datum", False, "Fällningsdag. Får vara före perioden, aldrig efter"),
        ),
    ),
    "leverans": Table(
        "Inmätning",
        "Inmätning vid industri: en rad per lass, eller summerat per arbetsorder och sortiment. Inga dimensioner.",
        (
            Column(AO, "text", True, "Arbetsorderns id, samma som i skördardatan"),
            Column(SORT, "text", True, "Inmätt handelssortiment, det som faktureras"),
            Column(VOL, "tal", True, "Nettovolym, den som faktureras. Negativ på en rad som vänder ett lass", "m3fub"),
            Column(BRUTTO, "tal", False, "Bruttovolym, det som lämnade lagret. Saknas den antas netto. Samma tecken som netto",
                   "m3fub"),
            Column(PRODUCED, "text", False, "Sortimentet i skördardatan, om industrin klassat om virket"),
            Column("mottagningsplats", "text", False, "Faktisk destination. Saknas den används den planerade"),
            Column("leverans_id", "text", False, "Lassets nummer. Ett lass får ha flera arbetsordrar och sortiment"),
            Column("leveransdatum", "datum", False, "Transportdatum, inte redovisningsdatum. Saknas det antas månadens slut"),
            Column("matmetod", "text", False, "En av " + ", ".join(MEASURING_METHODS)),
            Column("antal_matenheter", "tal", False, "Antal stockar eller travar i leveransen", "st", 0, None),
        ),
    ),
    "prislista": Table(
        "Prislista",
        "Pris per sortiment och klassintervall. Halvöppna intervall [min, max), tomt betyder öppet. Utan prislista "
        "blir det matriser och bilagor per mottagare, men inget fakturaunderlag.",
        (
            Column(SORT, "text", True, "Handelssortiment"),
            Column("diameter_min", "tal", True, "Lägsta diameterklass som ingår", "cm"),
            Column("diameter_max", "tal", True, "Första diameterklass som inte ingår", "cm"),
            Column("langd_min", "tal", True, "Lägsta längdklass som ingår", "cm"),
            Column("langd_max", "tal", True, "Första längdklass som inte ingår", "cm"),
            Column("pris_kr_per_m3fub", "tal", True, "Pris", "kr/m3fub", 0, 5000),
            Column(DEST, "text", False, "Regler med destination ersätter de allmänna för den destinationen"),
        ),
        optional=True,
    ),
    "arbetsordrar": Table(
        "Arbetsordrar",
        "Det som är känt om arbetsordern innan virket mäts. Utan den saknas planerad destination och grupp, och "
        "lånad fördelning blir sämre.",
        (
            Column(AO, "text", True, "Arbetsorderns id"),
            Column(DEST, "text", True, "Planerad mottagningsplats"),
            Column("grupp", "text", False, "Jämförbar grupp, till exempel region och avverkningsform"),
        ),
        optional=True,
    ),
    "avslutade_ao": Table(
        "Avslutade arbetsordrar",
        "Arbetsordrar som är klara efter månaden. Kvarvarande lager skrivs av. Utan den skrivs inget av.",
        (Column(AO, "text", True, "Arbetsorderns id"),),
        optional=True,
    ),
}

REQUIRED_TABLES = [key for key, table in TABLES.items() if not table.optional]


def markdown() -> str:
    """The contract as Markdown tables, for people and for a model adapting a source."""
    lines = [f"Kontraktsversion {CONTRACT_VERSION}.", ""]
    for key, table in TABLES.items():
        meaning = f"Valfri tabell. {table.meaning}" if table.optional else table.meaning
        lines += [f"## {table.name} (`{key}`)", "", meaning, ""]
        lines += ["| Kolumn | Krav | Typ | Enhet | Rimligt | Betydelse |", "|---|---|---|---|---|---|"]
        for c in table.columns:
            plausible = "" if c.low is None and c.high is None else f"{_num(c.low)}–{_num(c.high)}"
            lines.append(
                f"| `{c.name}` | {'Ja' if c.required else 'Nej'} | {c.kind} | {c.unit} | {plausible} | {c.meaning} |"
            )
        lines.append("")
    return "\n".join(lines)


def _num(value: float | None) -> str:
    return "" if value is None else f"{value:g}"
