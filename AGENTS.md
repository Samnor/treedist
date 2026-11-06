# Instruktion: koppla treedist till en ny datakälla

Den här filen är skriven för en modell eller en person som ska få `treedist` att läsa data från ett nytt
system. Uppgiften är nästan alltid att beskriva källans format, inte att ändra metoden.

Kommandona nedan skrivs `treedist ...`, som efter `pip install` och `treedist init`. Arbetar du i en klon av
repot, skriv `uv run` före varje kommando. Ger `treedist` "Åtkomst nekad", stoppar datorns programkontroll
`.exe`-filer i användarkatalogen; skriv då `python -m treedist ...` i stället, med samma argument.

## Vad du får ändra

- **En källbeskrivning.** Helst en `.toml`-mappning, se [examples/kalla/kalla.toml](examples/kalla/kalla.toml).
  Den byter kolumnnamn, räknar om enheter, sätter konstanter, filtrerar rader och läser datumformat.
  Decimalkomma läses alltid rätt, så `enheter` behövs bara för omräkning. Varje tabell tar nycklarna `fil`,
  `separator`, `kodning` (förval `"utf-8"`, till exempel `"latin-1"`), `datumformat`, `kolumner`, `enheter`,
  `konstanter` och `filter`. Kolumner som redan har kontraktets namn läses som de är, så en fil i treedists
  format, som prislistan, behöver bara `fil`.
- **En `.py`-adapter** bara när mappningen inte räcker: filer som måste slås ihop, koder som ska bli namn,
  id som skiljer mellan källorna. Den definierar `read(period) -> dict[str, DataFrame]` med tabellerna i
  kontraktets kolumnnamn. Lägg den i en egen katalog, till exempel `kallor/<system>/`. Utgå från
  [examples/kalla/kalla.py](examples/kalla/kalla.py), som läser samma källa som mappningen.
- **Frågor, hjälpskript och tester** som hör till källan, i samma katalog `kallor/<system>/`. Lägg dem inte i
  `out/`, som är utdata. Håll `kallor/` och `AGENTS.md` i git, och säkerhetskopiera `state/`.

Varje körning skriver per sågverk i `bilagor/`: `.html`, en sida med bara matriserna, längd i dm som rader och
diameter i cm som kolumner, i procent av diameterklassens volym, gjord för att skrivas ut som PDF; `.xlsx`, raderna som matriserna bygger på och matriserna
som formler över dem, för den som vill kontrollera; `.md` och `.csv`. `treedist pdf --out <månadens utdata>`
skriver ut HTML-sidorna som PDF med Edge eller Chrome. `sakerhet.html` visar hur stor del av månadens volym som är
bestämd och hur stor som är approximerad, och hur stor andel av den rättade approximerade volymen som bytte klass. `--bilaga-langd 340,370,400` och `--bilaga-diameter` visar
klasserna i grupper med de nedre gränserna i cm, till exempel 10 cm eller produktens brytpunkter, och den sista
gruppen är öppen uppåt. Låt adaptern ge de fina klasserna, och låt en person bestämma grupperna; samma grupper
varje månad. Ändra aldrig det installerade paketet, inte heller för presentationen: en ominstallation tar bort
ändringen. Behövs en annan form, be en person.

Välj inte modell själv. Utan `--modell` körs standardmodellen. `treedist modeller` listar de sparade
modellerna, om en person ber om en annan.

## Vad du inte får ändra

Metoden och dess facit. Efter `pip install` ligger de i det installerade paketet; ändra inget där. I en klon
av repot är det `src/treedist/core/`, `src/treedist/contract.py`, `src/treedist/schema.py`,
`src/treedist/uncertainty/` och `tests/golden/`. Om du tror att något där måste ändras: stanna och fråga en
person. Ett test som slutar fungera ska inte skrivas om för att passera.

## Arbetsgång

1. `treedist selftest` ska skriva `OK` innan du börjar. I en klon: `uv sync` och sedan `uv run pytest -q`.
   Kör bara läsande frågor mot källan, och fråga en person innan den första körningen mot ett produktionssystem.
2. `treedist kontrakt` skriver ut de fem tabellerna med krav, enhet, rimliga värden och betydelse.
   Läs kolumnen Betydelse noga.
3. Kopiera `examples/kalla/kalla.toml` till `kallor/<system>/kalla.toml` och fyll i källans filer och
   kolumnnamn. Filnamnen räknas från källbeskrivningens katalog.
4. Kör tills inget `FEL` återstår:

   ```bash
   treedist check --period 2026-01 --kalla kallor/system/kalla.toml
   ```

   Varje `VARNING` ska antingen rättas eller förklaras för en person. `INFO` kräver inget. Med `--state`
   provkörs månaden mot liggaren utan att något sparas.
5. Kör månaderna i ordning, med samma `--state` varje månad. Börja några månader före den första som ska
   faktureras. Annars saknar liggaren virke som skördats tidigare och fördelningen blir lånad, eller, med en
   kumulativ källa, räknas virke som redan levererats in i lagret.

   ```bash
   treedist run --period 2026-01 --kalla kallor/system/kalla.toml --state state --out out/2026-01
   ```

## Fallgropar som ger fel siffror utan felmeddelande

| Fråga | Rätt | Vanligt fel |
|---|---|---|
| Vilken volym är `volym_m3fub`? | Nettovolym som faktureras, fast under bark | Brutto, eller volym på bark (m3to, m3sk). Bark kan inte räknas om med en fast faktor |
| Vad är `brutto_m3fub`? | Volymen som lämnade avlägget, före avdrag | Samma kolumn som netto |
| Vad är `diametergrupp`? | Klassens nedre gräns i cm, till exempel 24 | Millimeter (240), klassens mitt (25) eller övre gräns (26) |
| Vad är `leveransdatum`? | Dagen lasset kördes | Redovisningsdatum eller mätdatum en annan månad |
| Vad betyder en negativ volym? | Ett lass som vänds, till exempel vid ommätning. Ta med raden; treedist nettar eller krediterar | Att filtrera bort negativa rader, så att vända lass faktureras två gånger |
| Hur läses datum? | Ange alltid `datumformat`, till exempel `"%Y%m%d"` eller `"%d.%m.%Y"`; då ger avvikande värden `FEL` | Utan format kan dag och månad tolkas omvänt utan att något märks |
| Vilket sortiment är `handelssortiment` i inmätningen? | Det inmätta, som faktureras | Det skördaren producerade. Det hör hemma i `producerat_handelssortiment` |
| Vilken destination? | `mottagningsplats` är den faktiska, `arbetsordrar.destination` den planerade | Planerad destination i `mottagningsplats` |
| Är arbetsorder-id samma i båda källorna? | Ja, exakt samma sträng, i den form arbetsordertabellen har. Skriv om de andra källornas id till den | Inledande nollor eller prefix som skiljer, eller att skriva om alla källor till en egen form. `check` visar skillnader som hög andel S3 |
| Vilka skördarrader hör till månaden? | De som rapporterades under månaden, även om virket fälldes tidigare. Har källan bara den kumulativa skörden, utan datum för när en rad rapporterades: låt adaptern läsa skörden fram till månadens slut och skicka den genom `treedist.adapters.snapshot.new_rows`, som fryser varje månad och bara skickar tillväxten | Att filtrera på `avverkningsdatum`, så att sent rapporterade rader aldrig kommer med, eller att skicka hela den kumulativa skörden varje månad, så att den räknas igen |
| När fylls `producerat_handelssortiment` i? | Bara när källan anger det per lass | Att härleda det ur skördardatan. Saknas kolumnen, lämna den tom |
| Vilken dag gäller en tidpunkt i UTC? | Dagen i svensk tid | Datumet i UTC, så att nattlass hamnar dagen före |
| Hur läser egna skript utdata och liggare? | Med alla kolumner som text, `dtype=str` | Att låta pandas gissa, så att ledande nollor försvinner och klasser blir flyttal |

## Klart betyder

- `treedist check` visar inget `FEL`, och varje `VARNING` är rättad eller förklarad.
- `treedist selftest` skriver `OK`, och i en klon passerar `uv run pytest -q`.
- En körd månad har en bilaga per sågverk i `bilagor/`, med en matris per handelssortiment vars summa är
  inmätningens volym. Excelfilens flik Läs först visar skillnaden 0,000 per sortiment. Körningen stoppar själv om den inte stämmer.
- Säger körningen att källbeskrivningen har ändrats sedan förra månaden, är ändringen förklarad för en person.

Prislistan är valfri. Saknar källan priser, lämna tabellen ute; då blir det matriser och bilagor men inget
fakturaunderlag. Hitta inte på priser.
