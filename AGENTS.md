# Instruktion: koppla treedist till en ny datakälla

Den här filen är skriven för en modell eller en person som ska få `treedist` att läsa data från ett nytt
system. Uppgiften är nästan alltid att beskriva källans format, inte att ändra koden. Koden får ändras om det
behövs för miljön, men först när de stabilare sätten nedan inte räcker.

Kommandona nedan skrivs `treedist ...`, som efter `pip install` och `treedist init`. Installera med adressen i
README, aldrig med bara `pip install treedist`: paketet med det namnet på PyPI är ett annat. Arbetar du i en klon av
repot, skriv `uv run` före varje kommando. Ger `treedist` "Åtkomst nekad", stoppar datorns programkontroll
`.exe`-filer i användarkatalogen; skriv då `python -m treedist ...` i stället, med samma argument.

## treedist talar VIOL 3

Tabellerna och kolumnerna har Biometrias termer från VIOL 3: `produktion` (skördarens produktion, hpr),
`matning` (redovisad mätning), `avtalsobjekt` och `avverkningsformer`, med kolumner som `avtalsobjekt`,
`producerat_handelssortiment`, `producerat_for_mottagningsplats`, `leveransnummer` och `matdatum`. Källans egna
termer översätts i källbeskrivningen, aldrig i treedist: ett företags arbetsorder blir `avtalsobjekt`, och dess
värden för avslutad transport blir `true` eller `false`. Bara data från VIOL 3 stöds. VIOL 3 tog emot leveranser
från 2 maj 2025, men VIOL 2 gjorde det till 17 oktober 2025, så data från de månaderna kan vara från båda.

treedist kräver de VIOL 3-uppgifter metoden vilar på, och gissar inte i deras ställe: avverkningsdatum och producerat
för mottagningsplats per rad i produktionen, och leveransnummer, leveransdatum, mätdatum, bruttovolym, producerat
handelssortiment och både inmätt och producerat för mottagningsplats per leverans. Två av dem är frivilliga i hpr:
producerat för mottagningsplats och stammens avverkningstid. Saknar källans export någon av dem, hämta den ur VIOL 3
hellre än att härleda den; `treedist check` säger vilken som saknas. Var varje definition kommer ifrån står i
[docs/kallor.md](docs/kallor.md#viol-3-kontraktets-termer-och-vad-de-vilar-på). En källa som läser VIOL 3
direkt har samma id och koder i produktion och mätning och behöver varken `koder` eller `format` nedan; de finns för
företagens egna system.

## Välj det stabilaste sättet som räcker

Gå uppifrån och ta nästa steg först när du kan säga vad det förra inte klarar. Ett högre steg är inte bättre,
bara friare: det kontrolleras mindre av treedist, och det måste göras om vid nästa version.

1. **Filer i treedists eget format** behöver bara `fil` i en mappning.
2. **En källbeskrivning.** Helst en `.toml`-mappning, se [examples/kalla/kalla.toml](examples/kalla/kalla.toml).
   Den byter kolumnnamn, räknar om enheter, sätter konstanter, filtrerar rader och läser datumformat.
   Decimalkomma läses alltid rätt, så `enheter` behövs bara för omräkning. Varje tabell tar nycklarna `fil`,
   `separator`, `kodning` (förval `"utf-8"`, till exempel `"latin-1"`), `datumformat`, `kolumner`, `enheter`,
   `konstanter` och `filter`. Kolumner som redan har kontraktets namn läses som de är, så en fil i treedists
   format behöver bara `fil`. Tre nycklar till täcker det mappningar oftast
   saknade, och stoppar hellre än gissar:
   - `[[tabell.koppla]]` med `fil` och `nyckel` hämtar kolumner ur en annan fil, till exempel avtalsobjektet per
     lass. Varje rad måste få exakt en träff. Se [examples/kalla_lass/kalla.toml](examples/kalla_lass/kalla.toml).
   - `[tabell.koder.kolumn]` översätter koder till de namn de andra tabellerna använder, i mappningen
     (`"110" = "TALL_SAG"`) eller ur en fil (`fil`, `fran`, `till`). En kod utan namn stoppar.
   - `[tabell.format.kolumn]` skriver om ett id till de andra tabellernas form: `ta_bort` ett prefix, `bredd` med
     nollor framför, `prefix` där det saknas. Se [examples/kalla_koder/kalla.toml](examples/kalla_koder/kalla.toml).
3. **En `.py`-adapter** bara när mappningen inte räcker: en databas eller ett API i stället för filer, rader som
   måste summeras eller vändas från breda till långa, flera filer som tillsammans är en tabell, eller en
   kumulativ skörd. Den definierar `read(period) -> dict[str, DataFrame]` med tabellerna i
   kontraktets kolumnnamn. Lägg den i en egen katalog, till exempel `kallor/<system>/`. Utgå från
   [examples/kalla/kalla.py](examples/kalla/kalla.py), som läser samma källa som mappningen.
4. **Bilagans inställningar** innan koden: `--bilaga-langd` och `--bilaga-diameter` för grupperna, och avverkningsformer i
   källan (se nedan).
5. **En egen kopia av treedist**, när 1–4 inte räcker: bilagan behöver en annan form, en kolumn eller kontroll
   saknas, eller miljön kräver något som paketet inte gör. Se [Ändra koden](#ändra-koden).

Frågor, hjälpskript och tester som hör till källan, i samma katalog `kallor/<system>/`. Lägg dem inte i
`out/`, som är utdata. Håll `kallor/` och `AGENTS.md` i git, och säkerhetskopiera `state/`.

Varje körning skriver per sågverk i `bilagor/`: `.html`, bilagan till fakturan, först matrisen för all volym till
sågverket, längd i dm som rader och diameter i cm som kolumner, i procent av diameterklassens volym, sedan hur den
togs fram (Sankeydiagram, ett exempel på hur volym utöver lagret fördelas, avtalsobjekten bakom den och en förklaring), gjord för att skrivas ut som PDF; `.xlsx`, samma bilaga som arbetsbok med siffrorna som formler över raderna, och raderna som matriserna bygger på och matriserna
som formler över dem, för den som vill kontrollera. `treedist pdf --out <månadens utdata>`
skriver ut HTML-sidorna som PDF med Edge eller Chrome. Avtalsobjekten bakom matriserna står också i
`avtalsobjekt.csv`. Behöver du se vad bilagan byggdes av, lägg till `--utvecklare`: då skrivs matriserna,
fördelningen och avstämningen per avtalsobjekt och bilagan som text till `utveckling/` i månadens utdata, körningen
skriver volymen per källa, och ett stopp visar hela felspårningen. Flaggan ändrar inga siffror och ingen av de andra
filerna. Har källan avverkningsformer med medelstam, ta med dem: bilagan visar dem. Avverkningsformerna ändrar ingen
volym, men `producerat_for_mottagningsplats` i mätningen gör det: lasset tar ur det lagret. Matrisen har en kolumn per cm i diameter från 13 till 49, med allt
under 13 cm i kolumnen `<13` och allt från 50 cm i `50+`. `--bilaga-langd 340,370,400` och `--bilaga-diameter` visar
klasserna i andra grupper med de nedre gränserna i cm, till exempel 10 cm eller produktens brytpunkter, och den sista
gruppen är öppen uppåt. Låt adaptern ge de fina klasserna, och låt en person bestämma grupperna; samma grupper
varje månad. Behövs en annan form på bilagan än grupperna ger, är det steg 5.

Välj inte modell själv. Utan `--modell` körs standardmodellen. `treedist modeller` listar de sparade
modellerna, om en person ber om en annan. `--modell dag` är dagmetoden: varje dags lass tar bara virke som är fällt
senast den dagen. Byt inte metod mitt i en följd av månader utan att en person vet om det; körningen säger när
modellen har ändrats sedan förra månaden.

treedist körs första dagen i en ny månad, för månaden innan, och en bilaga som skickats ändras inte av senare
månader. Volym som ryms i avtalsobjektets lager fördelas som skördaren mätte den (S1, Eget lager). Volym utöver lagret
fördelas som avtalsobjektets hela skörd (S2, Egen skörd i snitt) och står i bilagan som en uppskattning, och så står
den kvar: kommer skördardatan senare räknar liggaren av volymen, men ingen bilaga ändras och inget läggs på en
senare faktura.

Varje lass antas ha skördardata för sitt avtalsobjekt och sitt sortiment (de sex antagandena i
`docs/antaganden.md`). Ett lass utan stoppar månaden, och meddelandet säger vilka avtalsobjekt och sortiment det
gäller. Rätta källan efter antagandet som brast: id eller sortiment som skrivs olika i produktion och mätning, eller
skördardata som inte kommit in. Ingen inställning kommer förbi stoppet.

Virke som inte kommer från någon avverkning i underlaget, som köpt virke, import och virke från terminal, har ingen
skördardata att fördelas efter. Ta med det i mätningen och sätt `utan_avverkning` till `true` på dess rader, och
`false` på de andra. Då hålls det utanför matriserna, och bilagan säger hur stor del av sågverkets inmätta volym
matrisen gäller. Filtrera inte bort det i källan: då tror bilagan att matrisen är all volym. Sätt värdet ur
avtalsobjektets eller arbetsorderns typ, översatt med `koder`, aldrig ur att skördardata saknas: ett avtalsobjekt som
är en avverkning men saknar skördardata ska stoppa. Ett avtalsobjekt är märkt på alla sina rader eller inga, och
treedist stoppar ett märkt avtalsobjekt som har skördardata eller har fördelats en tidigare månad.

Har källan anskaffningsform, ta med den i mätningens kolumn `anskaffningsform`, som den text bilagan ska visa, en
per avtalsobjekt och på alla rader. Bilagan får då en del som visar sågverkets inmätta volym per anskaffningsform
och hur mycket av varje som står utanför matrisen. Metoden läser den inte. Delar källan in virket på flera
uppgifter, till exempel anskaffningsform och arbetsordertyp, slå ihop dem till en text i källbeskrivningen.
En äldre fil till `--config` med `own_harvest_only = true` eller `correction_on_invoice = false` läses som förut;
de motsatta värdena, och inställningarna för lånad fördelning, stoppar med besked om vilka rader som ska bort.

## Ändra koden

Fritt fram när steg 1–4 inte räcker, men aldrig i det installerade paketet: en ominstallation eller
uppgradering tar bort ändringen utan att säga något. Gör en egen kopia av exakt den version som är installerad,
i projektkatalogen och i git:

```bash
treedist --version
```

Hämta källkoden för den versionen, till exempel `https://github.com/Samnor/treedist/archive/refs/tags/v0.10.1.zip`,
packa upp den till `treedist-lokal/` i projektet och installera kopian i stället för paketet:

```bash
pip install -e ./treedist-lokal
```

Därefter läser `treedist` kopian. Ändra så lite som möjligt, i den del som behöver det:

- **Läsning och kontroller** finns i `src/treedist/adapters/`, `src/treedist/schema.py` och
  `src/treedist/check.py`.
- **Bilagans form** finns i `src/treedist/bilaga_html.py` och `src/treedist/bilaga_excel.py`. Dess ord och
  markeringar finns i `src/treedist/bilaga.py`. En ändring här ändrar inga siffror.
- **Metoden** finns i `src/treedist/core/`, `src/treedist/config.py` och `src/treedist/contract.py`. En ändring här
  ändrar bilagans siffror.

Efter varje ändring: `treedist selftest`, och `pytest` i `treedist-lokal/`. Skriver `selftest` att siffrorna
skiljer från facit, har ändringen flyttat volym mellan klasser. Är det inte meningen, rätta ändringen. Är det
meningen, fråga en person innan facit i `treedist-lokal/tests/golden/` skrivs om. Ett test som slutar fungera
ska inte skrivas om bara för att passera.

Skriv i `kallor/<system>/ANPASSNING.md` vad som ändrades, varför steg 1–4 inte räckte och vilken version
kopian bygger på. Vid en ny version av treedist: gör om kopian från den nya versionen och för över ändringarna.

## Arbetsgång

1. `treedist selftest` ska skriva `OK` innan du börjar. I en klon: `uv sync` och sedan `uv run pytest -q`.
   Kör bara läsande frågor mot källan, och fråga en person innan den första körningen mot ett produktionssystem.
2. `treedist kontrakt` skriver ut tabellerna med krav, enhet, rimliga värden och betydelse.
   Läs kolumnen Betydelse noga.
3. Kopiera den prototyp som liknar källan mest till `kallor/<system>/kalla.toml` och fyll i källans filer och
   kolumnnamn: `examples/kalla` för egna kolumnnamn, enheter och datum, `examples/kalla_lass` när en kolumn
   finns i en annan fil, `examples/kalla_koder` för koder och id som skrivs olika. Filnamnen räknas från
   källbeskrivningens katalog.
4. Kör tills inget `FEL` återstår:

   ```bash
   treedist check --period 2026-01 --kalla kallor/system/kalla.toml
   ```

   Varje `VARNING` ska antingen rättas eller förklaras för en person. `INFO` kräver inget. Med `--state`
   provkörs månaden mot liggaren utan att något sparas, och ett lass utan egen skördardata är då `FEL`. Utan
   `--state` vet `check` inte vad tidigare månader rapporterat och kan bara varna för det.
5. Kör månaderna i ordning, med samma `--state` varje månad. Den första månaden behöver all skördardata som
   rapporterats till och med månaden, också för virke som fälldes tidigare; annars saknar månadens lass skördardata
   och körningen stoppar. Börja minst sex månader före den första som ska faktureras, så att liggaren vet vad som
   redan levererats och har de lass som senare vänds. Annars räknas virke som redan levererats in i lagret, och ett
   vänt lass som inte finns i liggaren stoppar månaden.

   ```bash
   treedist run --period 2026-01 --kalla kallor/system/kalla.toml --state state --out out/2026-01
   ```

## Fallgropar som ger fel siffror utan felmeddelande

| Fråga | Rätt | Vanligt fel |
|---|---|---|
| Vilken volym är `volym_m3fub`? | Nettovolym som faktureras, fast under bark | Brutto, volym på bark (m3sk) eller toppcylindervolym (m3to). m3to är under bark men räknar stocken som en cylinder med toppdiametern. Varken bark eller m3to kan räknas om med en fast faktor, eftersom omräkningen beror på diameter och längd |
| Vad är `brutto_m3fub`? | Volymen som lämnade avlägget, före avdrag | Samma kolumn som netto |
| Vad är `avtalsobjekt`? | VIOL 3:s avtalsobjekt: det id som både produktionen (hpr) och mätningen bär, i den form tabellen `avtalsobjekt` har. Ett företags arbetsorder kan mappas hit när den är ett till ett med avtalsobjektet. Skriv om de andra källornas id till samma form, med `format` i mappningen | En intern arbetsorder som delar eller slår ihop avtalsobjekt, eller inledande nollor och prefix som skiljer. Ett lass vars id inte finns i produktionen stoppar månaden; `check --state` visar det som `FEL` |
| Vad är `diameterklass`? | Klassens nedre gräns i cm, till exempel 24 | Millimeter (240), klassens mitt (25) eller övre gräns (26) |
| Vad är `leveransdatum`? | Dagen lasset kördes. Mätdatum hör hemma i `matdatum` | Redovisnings- eller mätdatum, som kan ligga en annan månad |
| Vilka lass hör till månaden? | De rader som redovisades i månaden och inte skickats tidigare: välj på datumet raden kom till, till exempel redovisningsdatum. Dit hör lass som kördes eller mättes in en tidigare månad, och raden som vänder ett lass, som har lassets egna datum. `check` visar dem, och treedist stoppar ett lass som redan skickats | Att välja på leveransdatum eller mätdatum i månaden. Ett lass som kördes i slutet av förra månaden kommer då aldrig med, och inte heller en korrigering som görs efter att lassets månad körts |
| När är `transport_avslutad` true? | När inga fler lass ska köras från avtalsobjektet. treedist skriver av lagret först efter en månad utan inmätta leveranser, så ett lass som mäts in månaden efter tar ändå lagret | När avverkningen är klar men lass återstår, till exempel ur skördarens eller skotarens slutsignal: färdigskotat betyder att virket ligger vid vägen, inte att det är kört. Lagret skrivs då av medan virke ligger kvar, och senare lass fördelas som avtalsobjektets hela skörd. Körningen påpekar det |
| Vad betyder en negativ volym? | Ett lass som vänds, till exempel vid ommätning. Raden har lassets leveransnummer, avtalsobjekt, sortiment och mottagningsplats. Ta med raden; treedist räknar samman den med lasset eller krediterar. Ett undantag: vänder raden ett lass som redovisades före liggarens första månad, ta inte med den, eftersom lasset inte finns i liggaren | Att filtrera bort negativa rader, så att vända lass faktureras två gånger, eller att ge vändningen ett eget nummer, så att månaden stoppar |
| Hur läses datum? | Ange alltid `datumformat`, till exempel `"%Y%m%d"` eller `"%d.%m.%Y"`; då ger avvikande värden `FEL` | Utan format kan dag och månad tolkas omvänt utan att något märks |
| Vilket sortiment är `handelssortiment` i mätningen? | Det inmätta, som faktureras | Det skördaren producerade. Det hör hemma i `producerat_handelssortiment` |
| Vilken mottagningsplats? | `mottagningsplats` i mätningen är den där leveransen mättes in. `producerat_for_mottagningsplats`, i både produktion och mätning, är den skördaren kapade för: avtalsobjektets destinering per handelssortiment, och lagret lasset tar ur | Den destinerade i `mottagningsplats`, eller den inmätta i `producerat_for_mottagningsplats`, så att ett omdirigerat lass tar ur fel lager. `check` varnar när under hälften av volymen mättes in där den producerades för |
| Vilka skördarrader hör till månaden? | De som rapporterades under månaden, även om virket fälldes tidigare. Har källan bara den kumulativa skörden, utan datum för när en rad rapporterades: låt adaptern läsa skörden fram till månadens slut och skicka den genom `treedist.adapters.snapshot.new_rows`, som fryser varje månad och bara skickar tillväxten | Att filtrera på `avverkningsdatum`, så att sent rapporterade rader aldrig kommer med, eller att skicka hela den kumulativa skörden varje månad, så att den räknas igen |
| Vad är `producerat_handelssortiment` i mätningen? | Leveransens egen uppgift om vad skördaren kapade; VIOL 3 har den per leverans. Samma som `handelssortiment` när virket mättes in som det producerades. Har källan en kodlista för det producerade och en annan för det inmätta, skriv om dem till samma namn med `koder` | Att härleda det ur produktionen, att sätta det inmätta när källan har det producerade, eller att lämna två kodlistor för samma sortiment, så att allt virke ser omklassat ut |
| Vilken dag gäller en tidpunkt i UTC? | Dagen i svensk tid | Datumet i UTC, så att nattlass hamnar dagen före |
| Vilken medelstam? | Volym per avverkat träd i m3fub, per avverkningsform i `avverkningsformer` | dm3, eller en enda medelstam för hela avtalsobjektet när den har flera avverkningsformer |
| Vad gör jag med köpt virke, import och terminalvirke? | Ta med raderna och sätt `utan_avverkning` till `true`, ur avtalsobjektets typ. Bilagan anger då volymen utanför matrisen | Att filtrera bort dem, så att bilagan säger sig visa all volym till sågverket, eller att märka avverkningar som saknar skördardata, så att ett fel i källan döljs |
| Vad skriver jag där källan saknar en uppgift? | Tomt värde. En obligatorisk uppgift som saknas stoppar då kontrollen, och hämtas ur VIOL 3 | Källans eget värde för saknas, som `-1`, `0` eller `Okänd`. treedist läser det som ett id: skörd utan producerat för mottagningsplats blir ett lager som inga lass tar ur, och mer volym blir uppskattning. `check` varnar för det |
| Hur läser egna skript utdata och liggare? | Med alla kolumner som text, `dtype=str` | Att låta pandas gissa, så att ledande nollor försvinner och klasser blir flyttal |

## Klart betyder

- `treedist check` visar inget `FEL`, och varje `VARNING` är rättad eller förklarad.
- `treedist selftest` skriver `OK`, och i en klon passerar `uv run pytest -q`.
- Ändrades koden står det i `kallor/<system>/ANPASSNING.md`, och en person vet om det innan månaderna körs.
- En körd månad har en bilaga per sågverk i `bilagor/`, med en matris för alla handelssortiment vars summa är
  mätningens volym, utom den som är märkt `utan_avverkning`. Excelfilens flik Läs först visar skillnaden 0,000 per sortiment. Körningen stoppar själv om den inte stämmer.
- Säger körningen att källbeskrivningen, modellens parametrar eller bilagans grupper har ändrats sedan förra månaden,
  är ändringen förklarad för en person. Stoppar körningen för att ett lass eller skördarrader kommer igen, för att
  ett lass saknar egen skördardata, eller för att ett vänt lass inte finns i liggaren, rätta källan; stoppar den för ny kalibrering, fråga en person. Använd aldrig `--tillat-ny-kalibrering` på eget initiativ.

treedist läser inga priser och räknar inga belopp: bilagan visar volym per klass. Mappa ingen prislista.
