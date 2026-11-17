"""The canonical input tables, as data.

Everything the method reads comes through these tables. A new source
system is connected by an adapter that produces them (see adapters/), never by
changing the method. `treedist kontrakt` prints this as a table, and
`treedist check` tests an adapter's output against it, including whether the
values are plausible: a mapping can be valid in form and still wrong in meaning.

Column names are Swedish since they mirror the source systems.
"""

from __future__ import annotations

from dataclasses import dataclass

# Raised when a table changes in a way that old ledgers or adapters cannot follow.
CONTRACT_VERSION = 3

# The names are VIOL 3's (Biometria), so that a source in VIOL 3 maps onto them without translation of meaning.
AO = "avtalsobjekt"
SORT = "handelssortiment"
PRODUCED = "producerat_handelssortiment"
PRODUCED_FOR = "producerat_for_mottagningsplats"
DIA = "diameterklass"
LEN = "langdklass"
VOL = "volym_m3fub"
BRUTTO = "brutto_m3fub"
DEST = "mottagningsplats"
DONE = "transport_avslutad"
LOAD_ID = "leveransnummer"
DELIVERED = "leveransdatum"
MEASURED = "matdatum"
LOGS = "antal_stockar"
VINTAGE = "avverkningsdatum"
LANDING = "startplats"
TIER = "sakerhetsklass"
MEASURE = "avverkningsform"
STEM = "medelstam_m3fub"
OUTSIDE = "utan_avverkning"
ORIGIN = "anskaffningsform"

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
    "produktion": Table(
        "Produktion",
        "Skördarens produktion, rapporterad i hpr till VIOL 3: månadens nya rader, en rad per avtalsobjekt, producerat "
        "handelssortiment, producerat för mottagningsplats, klass och dag.",
        (
            Column(AO, "text", True, "Avtalsobjektet produktionen rapporterades på (hpr: ContractNumber). Samma id som i "
                   "mätningen"),
            Column(PRODUCED, "text", True, "Producerat handelssortiment, det skördaren kapade"),
            Column(PRODUCED_FOR, "text", True,
                   "Producerat för mottagningsplats, den skördaren kapade för. Samma id som mottagningsplatsen i "
                   "mätningen. Varje mottagningsplats har sitt eget lager; det är avtalsobjektets destinering per "
                   "handelssortiment"),
            Column(DIA, "klass", True, "Diameterklass: klassens nedre gräns enligt produktdefinitionen. Tom för sortiment "
                   "utan klasser", "cm", 5, 80),
            Column(LEN, "klass", True, "Längdklass: klassens nedre gräns enligt produktdefinitionen. Tom för sortiment utan "
                   "klasser", "cm", 150, 800),
            Column(VOL, "tal", True, "Skördarens volym", "m3fub", 0, None),
            Column(VINTAGE, "datum", True, "Avverkningsdatum, ur stammarnas datum. Får vara före perioden, aldrig efter"),
            Column(LOGS, "tal", False, "Antal stockar. Ger bättre osäkerhetsskattning", "st", 0, None),
            Column(LANDING, "text", False,
                   "Avlägget stammarna ligger närmast, ur stamkoordinaterna. Samma id som startplatsen i mätningen. "
                   "Ger ett lager per avlägg"),
        ),
    ),
    "matning": Table(
        "Mätning",
        "Redovisad mätning vid mottagningsplatsen, en rad per leverans, avtalsobjekt och handelssortiment. Inga "
        "dimensioner.",
        (
            Column(LOAD_ID, "text", True, "Leveransnummer. En leverans får ha flera avtalsobjekt och handelssortiment. En "
                   "rad som vänder leveransen en senare månad har samma nummer, och krediteras som den fakturerades"),
            Column(AO, "text", True, "Avtalsobjektet, samma id som i produktionen"),
            Column(SORT, "text", True, "Inmätt handelssortiment, det som faktureras"),
            Column(PRODUCED, "text", True, "Producerat handelssortiment, det skördaren kapade. Samma som det inmätta "
                   "när mottagningsplatsen inte mätt in virket som ett annat"),
            Column(DEST, "text", True, "Mottagningsplatsen leveransen mättes in vid"),
            Column(PRODUCED_FOR, "text", True, "Producerat för mottagningsplats: den skördaren kapade virket för, och "
                   "därmed lagret leveransen hämtades ur. Samma id som i produktionen"),
            Column(DELIVERED, "datum", True, "Leveransdatum: dagen lasset kördes"),
            Column(MEASURED, "datum", True, "Mätdatum: dagen leveransen mättes in, samma som leveransdatum eller senare. "
                   "En rad som vänder en leverans har leveransens mätdatum. Månadens rader väljer källan efter när "
                   "de redovisades; ordningen ur lagret följer leveransdatum"),
            Column(VOL, "tal", True, "Nettokvantitet, den som faktureras. Negativ på en rad som vänder en leverans",
                   "m3fub"),
            Column(BRUTTO, "tal", True, "Bruttokvantitet, det som lämnade avlägget. Samma tecken som netto", "m3fub"),
            Column(LANDING, "text", False, "Startplatsen, det avlägg leveransen hämtades från"),
            Column("matmetod", "text", False, "Mätmetod, en av " + ", ".join(MEASURING_METHODS)),
            Column("antal_matenheter", "tal", False, "Antal stockar eller travar i leveransen", "st", 0, None),
            Column(OUTSIDE, "logisk", False, "true när virket inte kommer från någon avverkning i underlaget: köpt "
                   "virke, import eller virke från terminal. Annars false. Sätts ur avtalsobjektets typ, aldrig för "
                   "att skördardata saknas. Leveransen fördelas inte, och bilagan anger dess volym utanför matrisen"),
            Column(ORIGIN, "text", False, "Anskaffningsform, som källan vill att den visas, till exempel egen skog, "
                   "virkesköp eller import. En per avtalsobjekt. Visas i bilagan; metoden läser den inte"),
        ),
    ),
    "avtalsobjekt": Table(
        "Avtalsobjekt",
        "Läget för avtalsobjekten vid månadens slut, en rad per avtalsobjekt, varje månad. Utan den avslutas inget "
        "avtalsobjekt.",
        (
            Column(AO, "text", True, "Avtalsobjektets id"),
            Column(DONE, "logisk", True, "true när transporten från avtalsobjektet är avslutad, annars false. Lagret "
                   "skrivs av efter första månaden där transporten är avslutad och ingen leverans mätts in"),
        ),
        optional=True,
    ),
    "avverkningsformer": Table(
        "Avverkningsformer",
        "Avverkningsformerna i ett avtalsobjekt, en rad per avverkningsform, med medelstam. Visar i bilagan om ett "
        "avtalsobjekt har flera avverkningsformer med olika medelstam. Utan den visas inga avverkningsformer.",
        (
            Column(AO, "text", True, "Avtalsobjektets id, samma som i tabellen avtalsobjekt"),
            Column(MEASURE, "text", True, "Avverkningsformen, till exempel slutavverkning eller gallring"),
            Column(STEM, "tal", False, "Medelstam: genomsnittlig volym per avverkat träd", "m3fub", 0.02, 2.5),
            Column(VOL, "tal", False, "Planerad volym för avverkningsformen", "m3fub", 0, None),
        ),
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
