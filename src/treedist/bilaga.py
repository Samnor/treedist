"""What an appendix says, built once per mill and month; each format draws it (the Builder pattern).

    build(...)              the content: the matrix's month and mill, the volume per source of its distribution, the
                            contract objects behind it with their marks, the measures and every text
    exempel                 the worked example of volume delivered beyond the stock, in words and as figures
    bilaga_html.render      the appendix as a printable page, with the diagram and the example
    bilaga_excel.add_sheets the same parts as sheets, with the numbers as formulas over the rows

What a reader sees in words, and which contract objects are marked, is decided here and nowhere else: a format chooses
which parts it shows and how, never what they say. The guide holds every part's explanation once; each format lists
the parts it explains, in its own order and with its own term.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .appendix import READER_NAMES, AppendixLayout, appendix_lead
from .contract import ORIGIN, STEM, TIER
from .core.allocate import CERTAINTY_TIERS
from .core.pipeline import MonthOutput
from .schema import AO, DEST, SORT, VOL
from .workorders import DRIFT, MEAN, PROGRESS, SO_FAR, Facts, mean_diameter, work_orders


# What the reader sees for each class: where its distribution comes from. The data, the ledger, Excel and CSV keep the
# codes S1 and S2.
NAMES = dict(READER_NAMES)


# What each source's distribution builds on. Volume beyond the stock is an estimate, and the appendix says so; it is
# never called provisional, since nothing on the appendix changes afterwards.
BASIS = {
    "S1": "Stockarna som finns kvar i avtalsobjektets lager, så som skördaren mätte dem.",
    "S2": "Allt skördaren har rapporterat för avtalsobjektet hittills. Används för volym som levererats utöver lagret.",
}


# Whether each source's distribution is the harvester's measurement or an estimate.
STATE = {"S1": "Mätt av skördaren", "S2": "Uppskattad"}


def tier_volumes(output: MonthOutput, mill: str | None = None) -> pd.DataFrame:
    """Delivered m3fub per certainty class for the month, from the allocation the invoice is built on: per mill, or for
    one mill per assortment."""
    allocation = output.step.allocation
    if mill is not None:
        allocation = allocation[allocation[DEST] == mill]
    if not len(allocation):
        return pd.DataFrame(columns=CERTAINTY_TIERS, dtype=float)
    by = DEST if mill is None else SORT
    volumes = allocation.pivot_table(index=by, columns="sakerhetsklass", values=VOL, aggfunc="sum", fill_value=0.0)
    return volumes.reindex(columns=CERTAINTY_TIERS, fill_value=0.0).clip(lower=0.0)


def sv(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


def volume_text(value: float) -> str:
    # Volume too small to show at one decimal is still volume, not zero.
    return "–" if value <= 0 else "<0,1" if value < 0.05 else sv(value)


def percent(part: float, whole: float) -> str:
    share = 100 * part / whole if whole > 0 else 0.0
    if 0 < share < 0.5:
        return "<1 %"
    # Not all of it is not all of it, even when it rounds to 100.
    return ">99 %" if 99.5 <= share < 100 - 1e-9 and part < whole else f"{share:.0f} %"


def plural(count: int) -> str:
    return f"{count} avtalsobjekt"


def share(part: float, whole: float) -> str:
    return percent(part, whole) if whole > 0.0005 and part > 0.0005 else "–"


def names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " och " + names[-1]


# A harvest whose mean diameter or length moved this much between its halves is marked: a month's delivery may differ
# from it. Length classes are usually 3 dm apart, so a move of one class is marked.
DRIFT_CM = 2.0


DRIFT_LENGTH_CM = 30.0


def overshipped(row: pd.Series) -> bool:
    return row[PROGRESS[0]] > 0.0005 and row[PROGRESS[1]] > row[PROGRESS[0]] * 1.005


def drifted(row: pd.Series) -> bool:
    moved = []
    for first, second, limit in ((DRIFT[2], DRIFT[3], DRIFT_CM), (DRIFT[4], DRIFT[5], DRIFT_LENGTH_CM)):
        early, late = row[first], row[second]
        moved.append(not (pd.isna(early) or pd.isna(late)) and abs(late - early) >= limit)
    return any(moved)


def planned(measures: pd.DataFrame) -> pd.Series:
    """Planned m3fub per contract object, the sum of its measures, where the source gives it."""
    given = measures.dropna(subset=[VOL]) if len(measures) else measures
    return given.groupby(AO)[VOL].sum() if len(given) else pd.Series(dtype=float)


def beyond_plan(row: pd.Series, planned: pd.Series) -> bool:
    whole = float(planned.get(row[AO], float("nan")))
    return not pd.isna(whole) and whole > 0 and not pd.isna(row[SO_FAR]) and float(row[SO_FAR]) > whole * 1.005


# A contract object whose measures differ this much in mean stem volume is marked: its parts may give different logs.
STEM_RATIO = 2.0


def differing_stems(held: pd.DataFrame) -> set[str]:
    """Contract objects with several measures whose largest mean stem volume is at least STEM_RATIO times the smallest."""
    if not len(held):
        return set()
    stems = held.dropna(subset=[STEM]).groupby(AO)[STEM].agg(["min", "max", "count"])
    return {str(a) for a, s in stems.iterrows() if s["count"] > 1 and s["min"] > 0 and s["max"] / s["min"] >= STEM_RATIO}


# What the appendix says where a month has nothing to show.
NOTHING_DELIVERED = ("Inget levererades till sågverket denna månad; bilagan visar bara krediterade lass från "
                     "tidigare månader.")


def certainty_lead(volumes: pd.DataFrame, mill: str, table: bool = False) -> str:
    """What the diagram shows in words: how much was delivered beyond the stock, and that it is an estimate. With
    `table`, the words open on the table of sources instead, for the workbook, which has no diagram."""
    total = float(volumes.to_numpy().sum()) if len(volumes) else 0.0
    if total <= 0.0005:
        return NOTHING_DELIVERED
    settled, beyond = float(volumes["S1"].sum()), float(volumes["S2"].sum())
    opening = (f"Tabellen visar hur matrisens {sv(total)} m3fub fördelades på klasser."
               if table else f"Diagrammet visar matrisens {sv(total)} m3fub per handelssortiment, till vänster, och hur "
               "volymen fördelades på klasser, till höger.")
    if beyond <= 0.0005:
        return (f"{opening} All volym ryms i avtalsobjektens eget lager och är fördelad så som skördaren mätte "
                "stockarna.")
    return (f"{opening} {percent(settled, total)} ryms i avtalsobjektens eget lager och är fördelad så som skördaren "
            f"mätte stockarna. Resten, {percent(beyond, total)}, levererades utöver lagret och är fördelad som "
            "avtalsobjektets hela skörd (egen skörd i snitt). Det är en uppskattning, inte en mätning.")


def _pull(rows: pd.DataFrame, matrix_mean: float) -> str:
    """Which contract objects move the matrix's mean diameter most, up and down: difference from it times volume."""
    sized = rows.dropna(subset=[MEAN])
    if sized[AO].nunique() < 2:
        return ""
    volume = sized.groupby(AO)[VOL].sum()
    mean = (sized[MEAN] * sized[VOL]).groupby(sized[AO]).sum() / volume
    pull = (mean - matrix_mean) * volume
    up, down = pull.idxmax(), pull.idxmin()
    parts = []
    if pull[up] > 0:
        parts.append(f"{up} ({sv(mean[up])} cm) drar den mest uppåt")
    if pull[down] < 0:
        parts.append(f"{down} ({sv(mean[down])} cm) {'' if parts else 'drar den '}mest nedåt")
    return " " + " och ".join(parts) + "." if parts else ""


def _marked(rows: pd.DataFrame, planned: pd.Series) -> str:
    """What the marks in the table point at, counted in contract objects."""
    if not len(rows):
        return ""
    over = rows[rows.apply(overshipped, axis=1)][AO].nunique()
    moved = rows[rows.apply(drifted, axis=1)][AO].nunique()
    beyond = rows[rows.apply(lambda r: beyond_plan(r, planned), axis=1)][AO].nunique() if len(planned) else 0
    parts = []
    if over:
        parts.append(f"{plural(over)} levererade mer i månaden än skördaren har rapporterat hittills (det som går "
                     "utöver är fördelat som egen skörd i snitt)")
    if beyond:
        parts.append(f"{plural(beyond)} har levererat mer än planerad volym")
    if moved:
        parts.append(f"{plural(moved)} ändrade diameter eller längd tydligt under skörden")
    if not parts:
        return ""
    return " Markerat i tabellen: " + "; ".join(parts) + "."


def orders_lead(rows: pd.DataFrame, matrix_mean: float, planned: pd.Series) -> str:
    """What the table of contract objects says in words: how many, whether a few dominate, which move the mean diameter,
    and what is marked."""
    total = float(rows[VOL].sum())
    per_order = rows.groupby(AO)[VOL].sum().sort_values(ascending=False)
    count = len(per_order)
    lead = f"Matrisen bygger på virke från {plural(count)}."
    if count > 1:
        half = int((per_order.cumsum() < total / 2).sum()) + 1
        lead += (f" Den största, {per_order.index[0]}, står för {percent(float(per_order.iloc[0]), total)} av volymen"
                 + (f", och de {half} största tillsammans för minst hälften." if half > 1 else "."))
    if not pd.isna(matrix_mean):
        lead += f" Matrisens medeldiameter är {sv(matrix_mean)} cm." + _pull(rows, matrix_mean)
    return lead + _marked(rows, planned)


# The wood outside the matrix, as a source beside S1 and S2 where the appendix shows where the wood comes from.
APART = "UTANFOR"
APART_NAME = "Utanför matrisen"
NO_ORIGIN = "Anskaffningsform saknas"
ORIGIN_COLUMNS = [ORIGIN, SORT, TIER, VOL]


def origin_rows(output: MonthOutput, mill: str, facts: Facts) -> pd.DataFrame:
    """m3fub at one mill per anskaffningsform, measured assortment and source of the distribution, with the wood
    outside the matrix as a source of its own. Empty when the source has no anskaffningsform."""
    if not len(facts.origin):
        return pd.DataFrame(columns=ORIGIN_COLUMNS)
    allocation = output.step.allocation
    inside = allocation.loc[allocation[DEST] == mill, [AO, SORT, TIER, VOL]]
    outside = facts.outside.loc[facts.outside[DEST] == mill, [AO, SORT, VOL]].assign(**{TIER: APART})
    rows = pd.concat([inside, outside], ignore_index=True)
    rows[ORIGIN] = rows[AO].map(facts.origin).fillna(NO_ORIGIN)
    summed = rows.groupby(ORIGIN_COLUMNS[:-1], as_index=False)[VOL].sum()
    return summed[summed[VOL] > 0.0005].reset_index(drop=True)


def origin_table(rows: pd.DataFrame) -> pd.DataFrame:
    """m3fub per anskaffningsform, largest first, and what became of it: a column per source, the wood outside the
    matrix last."""
    sources = [t for t in (*CERTAINTY_TIERS, APART) if (rows[TIER] == t).any()]
    table = rows.pivot_table(index=ORIGIN, columns=TIER, values=VOL, aggfunc="sum", fill_value=0.0)
    table = table.reindex(columns=sources, fill_value=0.0)
    return table.loc[table.sum(axis=1).sort_values(ascending=False, kind="stable").index]


def source_name(tier: str) -> str:
    return APART_NAME if tier == APART else NAMES[tier]


def origin_lead(rows: pd.DataFrame) -> str:
    """What the diagram of anskaffningsformer shows, in words."""
    total = float(rows[VOL].sum())
    apart = float(rows.loc[rows[TIER] == APART, VOL].sum())
    lead = (f"Diagrammet visar de {sv(total)} m3fub som mättes in vid sågverket under månaden per anskaffningsform, "
            "till vänster, och vad som hände med volymen, till höger.")
    if apart <= 0.0005:
        return lead + " All volym kommer från avverkning med skördardata och ingår i matrisen."
    return (lead + f" {percent(total - apart, total)} kommer från avverkning med skördardata och ingår i matrisen. "
            f"Resten, {sv(apart)} m3fub, har ingen avverkning i underlaget och står utanför matrisen.")


def coverage(b: Bilaga) -> str:
    """How much of the wood measured at the mill the matrix stands for, when some of it comes from no harvest."""
    if b.outside <= 0.0005:
        return ""
    measured = b.total + b.outside
    held = b.outside_by[b.outside_by > 0.0005]
    per = ", ".join(f"{sortiment} {sv(volume)}" if len(held) > 1 else str(sortiment) for sortiment, volume in held.items())
    return (f"Matrisen gäller virke från avverkning med skördardata: {sv(b.total)} av de {sv(measured)} m3fub som "
            f"mättes in vid sågverket under månaden, {percent(b.total, measured)}. Resten, {sv(b.outside)} m3fub "
            f"({per}), är virke utan avverkning i underlaget, till exempel köpt virke, import eller virke från "
            "terminal. Mätningen anger dess handelssortiment men inga diameter- och längdklasser, så det ingår inte i "
            "matrisen.")


def intro(b: Bilaga) -> str:
    """The appendix's first words: what was delivered, from how many contract objects, and how much of it the stock held."""
    count = b.rows[AO].nunique()
    found = (" All volym ryms i avtalsobjektens eget lager och är fördelad på klasser så som skördaren mätte stockarna."
             if b.total - b.settled <= 0.0005 else
             f" {percent(b.settled, b.total)} av volymen ryms i avtalsobjektens eget lager och är fördelad på klasser "
             "så som skördaren mätte stockarna. Resten levererades utöver lagret och är fördelad som avtalsobjektets "
             "hela skörd (egen skörd i snitt), en uppskattning.")
    return (appendix_lead(b.output, b.mill)
            + (" " + coverage(b) if coverage(b) else "")
            + (f" Virket kommer från {plural(count)}." + found if count and b.total > 0.0005 else "")
            + " Bilagan visar först matrisen, sedan "
            + ("varifrån virket kommer, hur matrisen togs fram" if len(b.origins) else "hur den togs fram")
            + ", ett exempel på hur volym utöver lagret "
            "fördelas, avtalsobjekten bakom matrisen och sist en förklaring av varje del.")


def measures_lead(held: pd.DataFrame, order: list[str]) -> str:
    """The measures in words, for the page: how many contract objects have them, and which have very different stems."""
    shown = held[AO].nunique()
    multi = int((held.groupby(AO).size() > 1).sum())
    differing = [str(a) for a in order if str(a) in differing_stems(held)]
    lead = f"Underlaget har avverkningsformer för {plural(shown)}."
    if multi:
        lead += f" Av dem har {multi} flera avverkningsformer"
        lead += (f", och för {names(differing)} är den största medelstammen minst dubbelt så stor som den minsta."
                 if differing else ", med likartad medelstam.")
    return lead


def measures_sheet_lead(held: pd.DataFrame) -> str:
    """The measures in words, for the workbook, where the marked rows are found by their fill."""
    return (f"Underlaget har avverkningsformer för {held[AO].nunique()} av avtalsobjekten. Markerade är avtalsobjekt med flera "
            "avverkningsformer där den största medelstammen är minst dubbelt så stor som den minsta."
            if len(held) else "Underlaget har inga avverkningsformer för avtalsobjekten bakom matrisen.")


def _words(per_day: bool = False, coverage: str = "") -> dict[str, str]:
    """Every text the appendix and the workbook explain their parts with, by part. `per_day` when each day's loads
    took only wood felled by that day."""
    cells = ("Varje cell är andelen i procent av diameterklassens volym, så varje kolumn summerar till 100. Ett streck "
             "betyder ingen volym, och <1 mindre än en halv procent.")
    axes = ("Raderna är stockarnas längd i dm och kolumnerna diametern i cm, med klassens nedre gräns. En kolumn "
            "eller rad som börjar med <, till exempel <13, är allt under gränsen, och en som slutar med +, till "
            "exempel 50+, är gränsen och allt över.")
    estimate = ("Volym som avtalsobjektet levererade utöver det som fanns kvar i lagret. Varje diameter- och längdklass "
                "får samma andel av den volymen som klassen har av avtalsobjektets hela skörd hittills: allt skördaren "
                "har rapporterat för avtalsobjektet och sortimentet, även det som redan levererats. Fördelningen är "
                "en uppskattning, inte en mätning. Exemplet om volym utöver lagret visar hur det går till.")
    if per_day:
        estimate += (" Varje dags lass har bara tagit virke som skördaren avverkat senast den dagen, så volym utöver "
                     "lagret är också det som kördes innan skördaren hade rapporterat virke som räckte.")
    whole = ("Volym från avverkning med skördardata som levererats till sågverket under månaden" if coverage else
             "All volym som levererats till sågverket under månaden")
    apart = f" {coverage}" if coverage else ""
    source_rows = ("En rad per källa: om fördelningen är mätt av skördaren eller uppskattad, vad den bygger på, "
                   "volymen per handelssortiment, summan och andelen av matrisen.")
    orders = ("Varje avtalsobjekt som levererat till sågverket under månaden, en rad per avtalsobjekt och sortiment. "
              "Summan av m3fub är matrisens summa. Andel av matrisen visar om några få avtalsobjekt dominerar.")
    marks = "Markerade celler står i fetstil på tonad botten."
    halves = ("En stor skillnad betyder att stockarna ändrades under skörden, så att en månads leverans kan skilja sig "
              "från avtalsobjektets hela skörd. En skillnad på minst 2 cm eller 3 dm är markerad.")
    limits = ("Källan säger vad fördelningen bygger på, inte hur stort felet är i en enskild bilaga. Även eget lager "
              "bygger på skördarens mätning av stockarna och på ett antagande om vilka stockar som lämnade lagret.")
    return {
        "matrix": (f"{whole}, alla handelssortiment tillsammans.{apart} "
                   f"{axes} {cells} Summorna är i m3fub. Krediterade lass från tidigare månader står i en egen matris "
                   "i m3fub."),
        "origin": ("Allt virke som mättes in vid sågverket under månaden, per anskaffningsform enligt underlaget. Till "
                   "höger står vad som hände med volymen: fördelad ur avtalsobjektens eget lager, fördelad som egen "
                   "skörd i snitt, eller utanför matrisen. Utanför matrisen står virke utan avverkning i underlaget, "
                   "till exempel köpt virke, import eller virke från terminal; det har ingen skördardata att fördelas "
                   "efter. Båda sidorna summerar till den inmätta volymen, och andelarna är andelar av den."),
        "diagram": ("Diagrammet läses från vänster till höger. Till vänster står handelssortimenten och till höger "
                    "fördelningens källor; båda sidorna summerar till matrisens volym. Ett bands bredd visar hur stor "
                    "volym det gäller. Vid varje stapel står volymen i m3fub, och till höger även andelen av matrisen. "
                    "Blått är eget lager, orange egen skörd i snitt och mörkgrått sortimenten; tabellen under "
                    "diagrammet och exemplet har samma färger. På skärmen visas volymen när markören hålls över ett "
                    "band eller en stapel."),
        "assortments": ("Volymen av varje inmätt handelssortiment som levererats till sågverket under månaden, i "
                        "m3fub. Tillsammans är de matrisens summa. Lass från tidigare månader som krediterats denna "
                        "månad ingår inte."),
        "S1": ("Volym som ryms i avtalsobjektets lager, det vill säga det skördaren har rapporterat och som ännu inte "
               "levererats. Den är fördelad på diameter och längd så som skördaren mätte stockarna."),
        "S2": estimate,
        "example": ("Ett räkneexempel med runda tal, steg för steg: vad skördaren har rapporterat, vad som mäts in, "
                    "och hur volymen utöver lagret får samma andelar som hela skörden hittills per diameter- och "
                    "längdklass. Handelssortimentet är det inmätta och uppskattas aldrig. Under exemplet "
                    "står månadens verkliga volym utöver lagret för sågverket, med de avtalsobjekt som levererade mest "
                    "utöver sitt lager."),
        "orders": (f"{orders} Fördelningens källa visar hur avtalsobjektets volym är fördelad, med andelen per källa "
                   f"när det är båda. {marks}"),
        "mean": ("Medeldiametern är den volymvägda diameterklassen i avtalsobjektets leverans till sågverket. Den visar "
                 "om avtalsobjektet drar matrisen uppåt eller nedåt. Annan klass än hela skörden jämför månadens "
                 "leverans med avtalsobjektets hela skörd hittills: andelen av leveransen som ligger i en annan "
                 "diameter- och längdklass än om den hade fördelats som hela skörden. 0 % betyder att månadens virke "
                 "har samma fördelning som hela skörden. Jämförelsen bygger på bilagans fördelning av leveransen."),
        "progress": ("Skördat hittills är allt skördaren har rapporterat för avtalsobjektet och det sortiment virket "
                     "producerades som, räknat om till väntad inmätt volym. Levererat i månaden är avtalsobjektets hela leverans i månaden, till "
                     "alla sågverk, som andel av det skördade. Över 100 % betyder att mer levererades än skördaren "
                     "har rapporterat; det som går utöver är fördelat som egen skörd i snitt. Kvar i lager är det "
                     "skördade som ännu inte levererats. När underlaget har planerad volym per avverkningsform visar Levererat "
                     "hittills hur mycket hela avtalsobjektet har levererat sedan beräkningarna började, alla sortiment "
                     "och sågverk, som andel av den planerade volymen. Ett värde över 100 % är markerat."),
        "felled": ("Första och sista avverkningsdag enligt skördaren. I kolumnen bredvid står medeldiametern i cm och "
                   "medellängden i dm, volymvägda, för första och andra halvan av skörden i den ordning den "
                   f"avverkades. {halves} Ett streck betyder att avverkningsdag eller klass saknas."),
        "measures": ("Avverkningsformerna i varje avtalsobjekt enligt underlaget, med medelstam i m3fub och planerad volym. En "
                     "avtalsobjekt med flera avverkningsformer där den största medelstammen är minst dubbelt så stor som den "
                     "minsta är markerad: dess delar kan ge olika stockar, så att en månads leverans kan skilja sig "
                     "från avtalsobjektets hela skörd."),
        "sources": f"{source_rows} Ett streck betyder ingen volym.",
        "limits": f"{limits} Avverkningsformerna visas bara när underlaget har dem.",
        "matrix_sheet": (f"Matrisen: {whole[0].lower()}{whole[1:]}, i m3fub.{apart} "
                         f"{axes} Under den står samma matris som procent av diameterklassens volym, så att "
                         "varje kolumn summerar till 100 %. Krediterade lass från tidigare månader ingår inte; de står "
                         "i fliken Krediteringar."),
        "sources_sheet": f"{source_rows} Kod är källans kod i fliken Fördelning.",
        "orders_sheet": (f"{orders} Kolumnerna Eget lager och Egen skörd i snitt visar hur stor del av avtalsobjektets "
                         f"volym som är fördelad ur varje källa. {marks}"),
        "felled_sheet": ("Första och sista avverkningsdag enligt skördaren, och medeldiametern i cm och medellängden i "
                         "dm, volymvägda, för första och andra halvan av skörden i den ordning den avverkades. "
                         f"{halves} En tom cell betyder att avverkningsdag eller klass saknas."),
        "limits_file": limits,
    }


# The parts each format explains, in its order, with the term it uses: the appendix (HTML) and the workbook.
PAGE_GUIDE = [
    ("Matrisen", "matrix"),
    ("Diagrammet", "diagram"),
    ("Handelssortimenten, till vänster", "assortments"),
    ("Eget lager, till höger", "S1"),
    ("Egen skörd i snitt, till höger", "S2"),
    ("Tabellen under diagrammet", "sources"),
    ("Exemplet", "example"),
    ("Avtalsobjekten bakom matrisen", "orders"),
    ("Medeldiameter och Annan klass än hela skörden", "mean"),
    ("Hela avtalsobjektet", "progress"),
    ("Avverkad och skördens halvor", "felled"),
    ("Avverkningsformer och medelstam", "measures"),
    ("Vad bilagan inte säger", "limits"),
]
FILE_GUIDE = [
    ("Alla handelssortiment", "matrix_sheet"),
    ("Källor", "sources_sheet"),
    (f"{NAMES['S1']} (S1)", "S1"),
    (f"{NAMES['S2']} (S2)", "S2"),
    ("Avtalsobjekt", "orders_sheet"),
    ("Medeldiameter och Annan klass än hela skörden", "mean"),
    ("Skörd och leverans", "progress"),
    ("Avverkad och skördens halvor", "felled_sheet"),
    ("Avverkningsformer och medelstam", "measures"),
    ("Vad filen inte säger", "limits_file"),
]


# The part that shows where the wood comes from, for a source that has anskaffningsform.
ORIGIN_GUIDE = ("Varifrån virket kommer", "origin")


def guide(parts: list[tuple[str, str]], per_day: bool = False, coverage: str = "",
          origins: bool = False) -> list[tuple[str, str]]:
    """(term, explanation) for the parts a format shows, in its order. `coverage` when the matrix leaves out wood that
    comes from no harvest, `origins` when the appendix shows the anskaffningsformer."""
    words = _words(per_day, coverage)
    if origins:
        parts = [parts[0], ORIGIN_GUIDE, *parts[1:]]
    return [(term, words[key]) for term, key in parts]


@dataclass(frozen=True)
class Bilaga:
    """One mill's appendix for one month, as every format draws it."""

    output: MonthOutput
    mill: str
    layout: AppendixLayout
    volumes: pd.DataFrame  # m3fub per assortment and source of the distribution
    rows: pd.DataFrame  # the contract objects behind the matrix, one row per contract object and assortment
    mean: float  # the matrix's volume weighted mean diameter class
    planned: pd.Series  # planned m3fub per contract object, where the source has it
    measures: pd.DataFrame  # the measures of the contract objects behind the matrix
    # m3fub measured at the mill from no harvest, per assortment: it has no classes, so the matrix leaves it out
    outside_by: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    # m3fub per anskaffningsform, assortment and source, with the wood outside the matrix; empty without anskaffningsform
    origins: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=ORIGIN_COLUMNS))

    @property
    def period(self) -> str:
        return self.output.step.period

    @property
    def total(self) -> float:
        return float(self.volumes.to_numpy().sum())

    @property
    def outside(self) -> float:
        return float(self.outside_by.sum())

    @property
    def settled(self) -> float:
        return float(self.volumes["S1"].sum()) if len(self.volumes) else 0.0


def build(output: MonthOutput, mill: str, layout: AppendixLayout = AppendixLayout(),
          facts: Facts | None = None) -> Bilaga:
    facts = facts or Facts()
    rows = work_orders(output)
    rows = rows[rows[DEST] == mill].reset_index(drop=True)
    held = facts.measures
    return Bilaga(
        output=output,
        mill=mill,
        layout=layout,
        volumes=tier_volumes(output, mill),
        rows=rows,
        mean=float(mean_diameter(output.step.allocation, [DEST]).get(mill, float("nan"))),
        planned=planned(held),
        measures=held[held[AO].isin(set(rows[AO]))] if len(held) else held,
        outside_by=facts.outside_at(mill),
        origins=origin_rows(output, mill, facts),
    )
