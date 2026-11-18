# treedist

Tar fram matriser per destination och handelssortiment som beskriver hur månadens levererade virke fördelar sig över
diameter och längd. Matriserna för ett sågverk samlas i en bilaga till månadens faktura,
`bilagor/<mottagningsplats>.html`, med raderna bakom i en Excelfil. Bilagan visar volym per klass; treedist sätter inga
priser och räknar inga belopp. Den körs första dagen i en ny månad, för månaden innan, och en bilaga som skickats
ändras inte av senare månader.

Produktionen, skördarens rapportering i hpr, vet fördelningen men mäter vid avverkning. Mätningen vid mottagningsplatsen
vet volymen, brutto och netto, men inget om dimensioner. Leveransen kommer dessutom efter skörden, så månadens skörd beskriver inte månadens leveranser. Därför
håller `treedist` en liggare över skördat men olevererat virke per avtalsobjekt och fördelar leveransvolymen utifrån den.
Volym som ryms i avtalsobjektets lager får lagrets klasser, så som skördaren mätte stockarna. Volym utöver lagret får
klasserna i avtalsobjektets hela skörd, och visas i bilagan som en uppskattning. Varje lass antas ha skördardata för
sitt avtalsobjekt och sitt sortiment; ett lass utan stoppar månaden, se [antagandena](docs/antaganden.md).

- [Metod](docs/metod.md): hur det fungerar, parametrar och begränsningar
- [Metodjämförelse](docs/metodjamforelse.md): tre metoder, akademiska begrepp och jämförelse med forskningen
- [Underlag för simulering](docs/simuleringsunderlag.md): vad årsredovisningar och Biometria säger om data
- [Exempelresor](docs/exempelresor.md) och [antaganden](docs/antaganden.md): virkets väg från skördare till sågverk,
  och hur rimliga antagandena är
- [Källor](docs/kallor.md): alla källor efter ämne, med vad var och en visar och var den används
- [Kraven mot VIOL 3](docs/krav.md): vilka krav som håller mot Biometrias dokument och verklig data, och vilka som inte gör det
- [AGENTS.md](AGENTS.md): hur en ny datakälla kopplas in, skrivet så att en modell kan göra det
- [Portabilitet](docs/portabilitet.md): hur väl en enklare modell kopplar in nya källor, och vad `check` fångar, och klättringen av installationen med billiga modeller

## Installera

Med pip, direkt från GitHub. Ange en version, så att metoden och de sparade modellerna inte byts ut under en
pågående serie månader:

```bash
pip install "treedist @ git+https://github.com/Samnor/treedist@v0.10.2"
```

Den raden kräver Git. Utan Git, till exempel på en nyinstallerad Windows-dator, installeras samma version från
versionens zip-arkiv:

```bash
pip install https://github.com/Samnor/treedist/archive/refs/tags/v0.10.2.zip
```

`treedist init` lägger [AGENTS.md](AGENTS.md) och exemplen i en katalog, och `treedist selftest` kör demons
fyra månader och jämför med facit. Det ska stå `OK` innan riktiga månader körs:

```bash
treedist init mitt-projekt
```

```bash
treedist selftest
```

Utan uv eller klon skrivs kommandona nedan utan `uv run`. Stoppar datorns programkontroll `treedist.exe` med
"Åtkomst nekad", fungerar `python -m treedist` med samma argument.

## Kom igång i en klon av repot

Installera med [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Stäng en månad med exempeldatat:

```bash
uv run treedist run --period 2026-01 --produktion examples/demo/produktion_2026-01.csv --matning examples/demo/matning_2026-01.csv --avtalsobjekt examples/demo/avtalsobjekt_2026-01.csv --state state --out out/2026-01
```

Har källsystemet ett eget format beskrivs det i en TOML-fil i stället för fem filargument, och `check` prövar
datan mot kontraktet och mot rimliga värden innan något körs:

```bash
uv run treedist check --period 2026-01 --kalla examples/kalla/kalla.toml
```

```bash
uv run treedist run --period 2026-01 --kalla examples/kalla/kalla.toml --state state --out out/2026-01
```

Månader körs i följd eftersom varje månad bygger vidare på föregående liggare i `state/`. Att köra om senaste månaden
är säkert: den utgår från liggaren före. Saknas en månad, eller finns senare månader, stoppas körningen. Den första
månaden i en ny liggare behöver all skördardata som rapporterats till och med månaden, också för virke som fälldes
tidigare; annars saknar månadens lass skördardata och körningen stoppar.

Bredvid liggaren sparar varje månad vad den fick: alla leveransnummer hittills (`lass.csv`), månadens skördarrader
(`produktion.csv`), modellens parametrar och bilagans grupper (`korning.json`), avskrivna avtalsobjekt
(`avslutade.csv`) och avtalsobjekt vars transport är avslutad men som ännu inte skrivits av (`transport_avslutad.csv`). Nästa månad jämförs med dem, och körningen stoppar utan att spara något om ett lass från en
tidigare månad kommer igen utan att vändas, om mer än hälften av skördarvolymen är förra månadens rader igen (en
kumulativ export), eller om kalibreringen (`harvester_bias`, `handling_loss`) har ändrats, eftersom lagret i
liggaren då skulle blanda två skalor; `--tillat-ny-kalibrering` kör ändå. Andra ändrade parametrar och grupper, en
del upprepade skördarrader och avslutade avtalsobjekt som levererar igen skrivs som OBS. `treedist check --state`
visar samma sak. Ett avtalsobjekt med flera rader som säger olika destination stoppar alltid.

Utvärdera metoden mot simulerat facit, och skapa egen syntetisk indata. De två kommandona är för utveckling och
listas i hjälpen bara med `--utvecklare`:

```bash
uv run treedist backtest --manader 12
```

```bash
uv run treedist simulate --out examples/egen --manader 6
```

Klättra mot en bättre metod, en bedömd ändring i taget. Varje kandidat jämförs med den bästa hittills på samma
simuleringar och tas bara om skillnaden är större än bruset. Utvecklingsfrön används för besluten och kontrollfrön för
att pröva resultatet. Försöken loggas i `climb/logg.jsonl`, och processen för strukturella ändringar beskrivs i
[.claude/skills/metod-klattring](.claude/skills/metod-klattring/SKILL.md).

```bash
uv run python scripts/climb.py params --budget 30
```

```bash
uv run python scripts/climb.py holdout
```

En förenkling tar bort en del i stället för att lägga till en, och får kosta lite. `forenkla` prövar flera
borttagningar mot samma baslinje; varje steg får kosta högst 0,25 i poäng och en hel klättring högst 1,0.

```bash
uv run python scripts/climb.py forenkla volume_error=false 'design_effect=100,pool_remaining_share=0'
```

Sparade modeller ligger i [modeller/](modeller), en TOML-fil per modell med kod, antal delar och resultat i
tabellen `[modell]`, och följer med paketet. Utan `--modell` körs standardmodellen. `--modell enkel` har 2 av 15
delar och 83 % av standardmodellens förbättring mot den naiva skattningen, men inga intervall. `--modell halv`
har 6 av 15 delar, 87 % av förbättringen och lätta intervall, och `--modell halv-volym` samma med 5 delar och
utan att läsa antal stockar. De enkla modellerna tappar mest när ett avtalsobjekt levererar till flera sågverk, se
[metodjämförelsen](docs/metodjamforelse.md#resultat). `--config` tar en egen fil i stället, eller ändrar
tillsammans med `--modell` bara de parametrar filen anger.

```bash
uv run treedist modeller
```

```bash
uv run python scripts/modell.py spara NAMN --beskrivning "vad som ändrats" --utvardera
```

Stresstestet kör modellerna på simuleringar som skiljer sig från dem de valdes på, till exempel sen rapportering,
stor skillnad mellan brutto och netto eller klumpiga avlägg, se
[metodjämförelsen](docs/metodjamforelse.md#stresstest-när-verkligheten-skiljer-sig-från-simulatorn):

```bash
uv run python scripts/stresstest.py
```

[Flödesrapporten](docs/flodesrapport.html) visar demons månader steg för steg som en graf, från indata via liggaren,
dragningen och säkerhetsklasserna till matriser, bilagerader och facit. Klicka på ett steg för detaljerna. Skapa den på
nytt efter en ändring i metoden, eller för annan data med `--data` eller `--kalla` och `--perioder`:

```bash
uv run python scripts/flodesrapport.py
```

Kör testerna:

```bash
uv run pytest
```

## Arkitektur

När treedist flyttas till ny data ändras nästan alltid bara en adapter, som översätter källans format till de
kanoniska tabellerna. Räcker inte det får koden ändras i en egen kopia av den installerade versionen; AGENTS.md
beskriver trappan, från mappning till egen kopia, och hur kopian görs.

```
källans export ──> adapter ──> kanoniska tabeller ──> kärna ──> matriser och bilagor
                   (ändras)    contract.py                       ▲
                                                                 └── bilagan: innehåll en gång, sida och arbetsbok
```

| Del | Innehåll | Ändras vid flytt |
|---|---|---|
| `adapters/` | Kanoniska CSV-filer, TOML-mappning eller egen `.py` | Ja, genom en ny källbeskrivning |
| `contract.py` | Tabellerna: kolumner, krav, enhet, rimliga värden, betydelse | Sist, i en egen kopia |
| `check.py` | Formkontroll, rimlighetskontroller och provkörning utan att spara | Sist, i en egen kopia |
| `core/` | Liggare, fördelning, matriser och bilagans rader. Deterministisk | Sist, i en egen kopia; ändrar siffrorna |
| `bilaga.py` | Vad bilagan säger, byggt en gång per sågverk: siffror, markeringar och alla texter | Sist, i en egen kopia |
| `bilaga_html.py`, `bilaga_excel.py` | Ritar bilagan som utskrivbar sida och som arbetsbok; väljer delar, aldrig ord | Sist, i en egen kopia |
| `dev/` | Simulator och utvärdering: Monte Carlo och en exempelprislista som väger felen. Behövs inte i drift | Nej |

`treedist run` drar inga Monte Carlo-intervall: bilagan visar inga, utan säger vad som är mätt av skördaren och
vad som är uppskattat. Intervallen används bara när metoden utvärderas mot simulatorn. Golden-testet i
`tests/test_portability.py` kontrollerar att demons bilagerader och matriser inte ändras av omstruktureringar, och
liggaren sparar sin kontraktsversion så att en gammal liggare inte läses med ett nytt format.

## Indata

CSV med en rad per observation, eller källans egna filer genom en adapter. `uv run treedist kontrakt` skriver ut
tabellerna med enhet, rimliga värden och betydelse. Decimalkomma och decimalpunkt fungerar båda.

Tabellerna och kolumnerna har VIOL 3:s termer (Biometria). Källans egna termer, till exempel ett företags arbetsorder,
översätts i källbeskrivningen. Bara data från VIOL 3 stöds; VIOL 2 tog emot leveranser till 17 oktober 2025. De
VIOL 3-uppgifter metoden vilar på är obligatoriska, och treedist gissar inte i deras ställe. Varifrån varje definition
kommer står i [docs/kallor.md](docs/kallor.md#viol-3-kontraktets-termer-och-vad-de-vilar-på).

**Produktion** (`--produktion`). Skördarens produktion, hpr: månadens nya rader ur en tabell utan dubbletter. En rad
får bara förekomma i en månad.

| Kolumn | Krav | Beskrivning |
|---|---|---|
| `avtalsobjekt` | Ja | Samma id som i mätningen |
| `producerat_handelssortiment` | Ja | Det skördaren kapade |
| `producerat_for_mottagningsplats` | Ja | Mottagningsplatsen skördaren kapade för. Varje mottagningsplats har sitt eget lager |
| `diameterklass` | Ja | Klassens nedre gräns i cm. Tom för sortiment utan klasser |
| `langdklass` | Ja | Klassens nedre gräns i cm. Tom för sortiment utan klasser |
| `volym_m3fub` | Ja | |
| `avverkningsdatum` | Ja | Ur stammarnas datum. Får vara tidigare än perioden, aldrig senare |
| `antal_stockar` | Nej | Ger bättre osäkerhetsskattning |
| `startplats` | Nej | Avlägget stammarna ligger närmast. Ger ett lager per avlägg |

**Mätning** (`--matning`). Redovisad mätning, en rad per leverans, avtalsobjekt och sortiment. Får inte innehålla
diameter- eller längdklass.

| Kolumn | Krav | Beskrivning |
|---|---|---|
| `leveransnummer` | Ja | En leverans får ha flera avtalsobjekt och sortiment. En rad som vänder den har samma nummer |
| `avtalsobjekt` | Ja | Samma id som i produktionen |
| `handelssortiment` | Ja | Inmätt sortiment, det som faktureras |
| `producerat_handelssortiment` | Ja | Det skördaren kapade. Samma som inmätt, om virket inte mättes in som ett annat |
| `mottagningsplats` | Ja | Där leveransen mättes in |
| `producerat_for_mottagningsplats` | Ja | Den skördaren kapade för: lagret leveransen hämtades ur |
| `leveransdatum` | Ja | Dagen lasset kördes. Får vara före perioden |
| `matdatum` | Ja | Dagen leveransen mättes in, samma som leveransdatum eller senare. Månadens rader väljer källan efter när de redovisades |
| `volym_m3fub` | Ja | Nettokvantitet, det som faktureras. Negativ på en rad som vänder en leverans, med samma tecken på brutto |
| `brutto_m3fub` | Ja | Bruttokvantitet, det som lämnade avlägget. Används för lagret |
| `startplats` | Nej | Avlägget leveransen hämtades från |
| `matmetod` | Nej | `stockmatning`, `travmatning`, `vagning`, `skordarmatning` eller `okand` |
| `antal_matenheter` | Nej | Antal stockar eller travar i leveransen |
| `utan_avverkning` | Nej | `true` för virke som inte kommer från någon avverkning i underlaget: virke köpt färdigavverkat, import eller virke från terminal. Det fördelas inte, och bilagan anger volymen utanför matrisen |
| `anskaffningsform` | Nej | Anskaffningsformen som bilagan ska visa den, till exempel egen skog, virkesköp eller import. En per avtalsobjekt. Ger bilagan en del som visar varifrån virket kommer |

Ett lass tar ur lagret för den mottagningsplats det producerades för och bokas där det mättes in. Räcker inte det
lagret är resten volym utöver lagret (S2); ett lass tar aldrig virke som kapades för en annan mottagningsplats.
Skörd och lager redovisas på den mottagningsplats de producerades för.

**Avtalsobjekt** (`--avtalsobjekt`), valfritt, en fil per månad: `avtalsobjekt` och `transport_avslutad` (`true`
eller `false`). Ett avtalsobjekt vars transport är avslutad skrivs av efter första månaden utan inmätta leveranser: kvarvarande lager skrivs av, och volym som levererats
utöver lagret räknas inte längre av mot skördardata som kommer senare.

**Avverkningsformer** (`--avverkningsformer`), valfritt: `avtalsobjekt`, `avverkningsform`, `medelstam_m3fub` och
planerad `volym_m3fub`. Visas i bilagan; ändrar inga siffror.

**Konfiguration**, valfritt: en TOML-fil till `--config` med parametrarna i [docs/metod.md](docs/metod.md).
En sparad modell har också Monte Carlo-parametrarna, som bara utvärderingen läser; körningen läser förbi dem.

## Utdata

```
out/2026-01/
  bilagor/<mottagningsplats>.html         bilaga till fakturan: matrisen, sedan hur den togs fram, A4 liggande för PDF
  bilagor/<mottagningsplats>.xlsx         bilagan som arbetsbok, i samma ordning, med siffrorna som formler över raderna
  faktura_rader.csv                  bilagans rader: leveranser och krediteringar av vända lass, i hela liter
  sammanfattning.md                  volymer och andel per säkerhetsklass
  avtalsobjekt.csv                   avtalsobjekten bakom matriserna, som på sidan Avtalsobjekten bakom matriserna
  manifest.json                      parametrar, bilagans form och kontrollsummor för indata och källbeskrivning
```

Det är allt en månad behöver. Med `--utvecklare` skriver `run` också det bilagorna byggdes av, i en egen katalog,
utan att ändra någon av filerna ovan:

```
out/2026-01/utveckling/
  matriser/<mottagningsplats>/<sortiment>/*.csv   matriser med diameter som rader, längd som kolumner
  matriser_lang.csv                  samma matriser i långt format
  leverans_ao_lang.csv               fördelningen per avtalsobjekt och säkerhetsklass
  krediteringar_ao_lang.csv          krediteringar av vända lass per avtalsobjekt
  avstamning_ao.csv                  lagerbalans per avtalsobjekt och sortiment
  uppskattning_mot_skordardata.csv   uppskattad volym jämförd med skördardata som kom senare; ändrar ingen bilaga
  bilagor/<mottagningsplats>.md           bilagans matriser som text, i m3fub eller procent
  bilagor/<mottagningsplats>.csv          samma volymer i långt format, med andel per säkerhetsklass
```

Flaggan står före kommandot eller efter `run` och `check`. Körningen skriver då också volymen per källa och
sågverk och de parametrar som skiljer från standardmodellen, och ett stopp visar hela felspårningen före raden
`Fel:`. `treedist --utvecklare --help` listar även `simulate` och `backtest`.

```bash
uv run treedist run --utvecklare --period 2026-01 --kalla examples/kalla/kalla.toml --state state --out out/2026-01
```

HTML-sidan visar en matris: stockarnas längd i dm som rader och diameter i cm som kolumner, för alla
handelssortiment tillsammans. Inledningen anger volymen per sortiment. Varje cell är procent av diameterklassens volym i hela procent, `<1` under en
halv procent och `–` utan volym; summakolumnen är m3fub och summaraden m3fub, eller tusen m3fub när kolumnerna är
stora. Krediterade lass från tidigare månader, lass som krediterats efter att de fakturerats, visas i en egen matris i
m3fub, även den för alla sortiment. Efter matrisen förklarar bilagan hur den togs fram: ett Sankeydiagram från
sågverkets handelssortiment till fördelningens två källor, samma volymer i en tabell, ett exempel i tre steg på hur
volym utöver lagret fördelas, avtalsobjekten bakom matrisen och en förklaring av varje del (se nedan).
`treedist pdf --out out/2026-01` skriver
ut månadens HTML-sidor som PDF med Edge eller Chrome och räknar sidorna; `TREEDIST_BROWSER` pekar ut en annan
webbläsare. Markdown-filen, som skrivs med `--utvecklare`, visar m3fub, eller procent med `--bilaga andel`.

Excelfilen följer bilagan flik för flik: matrisen, räknad med SUMIFS ur fliken Bilagans rader och under den samma
matris i procent; Källor, volymen per fördelningens källa och sortiment; Avtalsobjekt, med volym, andel och källor
räknade ur fliken Fördelning och bilagans markeringar som tonade celler; Avverkningsformer; och Förklaring, bilagans ord
för det som finns i filen, med exemplet i text (diagrammet och exemplets figurer finns bara i bilagan). Varje flik
börjar med bilagans egen text. Bakom finns Fördelning (volym per avtalsobjekt, klass och källa, med koden S1 eller
S2), Krediteringar, Mätning, Avstämning per avtalsobjekt och månadens
Skördardata. Fliken Läs först jämför inmätt volym med bilagan per sortiment; skillnaden ska vara 0,000. Varje formel
sparas med sitt värde, så att en förhandsvisning i Outlook, på en telefon eller i Excels skyddade vy visar siffrorna;
Excel räknar ändå om allt när filen öppnas. Flikarna skrivs ut liggande på A4, så breda som sidan, med rubrikraden
på varje sida.

Matrisen har en kolumn per cm i diameter, från 13 till 49. Allt under 13 cm står i kolumnen `<13` och allt från
50 cm i kolumnen `50+`. En klass utan volym får ingen kolumn. `--bilaga-langd` och `--bilaga-diameter` tar andra nedre
gränser i cm, till exempel `--bilaga-langd 340,370,400`, och visar klasserna i grupper i alla tre formerna utan att
någon summa ändras; den sista gruppen är öppen uppåt. En grupp som är en enhet bred, 1 dm eller 1 cm, visas med bara
sin nedre gräns, så `--bilaga-langd 300,310,...,510` ger raderna `<30`, `30`, `31` och så vidare till `51+`.
`--bilaga-diameter klasser` visar diameterklasserna som underlaget har dem, utan grupper. Valet sparas i
`manifest.json`.

Diagrammet i bilagan visar sågverkets volym per handelssortiment och hur den fördelades på klasser: ur avtalsobjektens
eget lager (S1), mätt av skördaren, eller som avtalsobjektets hela skörd, egen skörd i snitt (S2), en uppskattning. Under diagrammet
står samma volymer i en tabell. Sidan efter förklarar uppskattningen med ett exempel i tre steg, vart och ett med en
figur: skördaren rapporterar 100 m3fub av ett handelssortiment i tre diameterklasser, månadens lass mäts in till
50 m3fub fast lagret bara har 40, och de 10 m3fub utöver lagret får samma andelar per diameter- och längdklass som
hela skörden hittills, som i matrisen. Handelssortimentet är det inmätta och uppskattas aldrig. Under exemplet står hur mycket av månadens
volym till sågverket som fördelades så. Sist i bilagan förklaras varje del för den som vill läsa. Bilagan hämtar
inget från nätet och skrivs ut på A4.

Avtalsobjekten bakom en matris står i en tabell: hur många de är, om några få dominerar, vad var och en
levererade och dess andel av matrisen, medeldiametern i leveransen jämfört med matrisens, hur stor del av
leveransen som ligger i en annan klass än avtalsobjektets hela skörd, fördelningens källa, hur mycket avtalsobjektet
skördat, hur stor del av det som levererades under månaden, vad som ligger kvar, hur mycket av den planerade volymen
som levererats hittills (när `avverkningsformer` har planerad volym), när den avverkades och medeldiameter och medellängd för
första och andra halvan av skörden. Levererat över 100 % av det skördade, levererat mer än planerat och en ändring på minst 2 cm eller
3 dm under skörden är markerade. Samma rader skrivs till `avtalsobjekt.csv`.

Den valfria tabellen `avverkningsformer` (`--avverkningsformer`, eller `[avverkningsformer]` i en mappning) har en rad
per avverkningsform i ett avtalsobjekt, med medelstam i m3fub; bilagan visar dem och markerar ett avtalsobjekt vars avverkningsformer skiljer mer än
dubbelt i medelstam. Metoden läser inte avverkningsformerna; de förklarar bara matrisen.

En källa som bara har den kumulativa skörden, utan datum för när en rad rapporterades, ansluts med en
`.py`-adapter som skickar skörden genom `treedist.adapters.snapshot.new_rows`. Den fryser varje månad första
gången den läses och skickar bara tillväxten sedan förra månaden; minskningar loggas i en egen fil.

Matriserna per destination och sortiment:

| Fil | Innehåll |
|---|---|
| `levererat` | Bästa skattning, m3fub. Summerar till nettovolymen hos destinationen |
| `levererat_S1`, `levererat_S2` | Samma volym uppdelad efter källa. Summerar till `levererat` |
| `andel` | Andel av sortimentets levererade volym |
| `skordat_ra` | Månadens skördarrapport utan kalibrering, på mottagningsplatsen den producerades för |
| `lager_utgaende` | Skördat men inte levererat vid månadens slut, på mottagningsplatsen det producerades för |
| `kreditering` | Lass från tidigare månader som vänts, med negativ volym |

## Säkerhetsklasser

| Klass | I bilagan | Fördelningen kommer från | Sägs i bilagan |
|---|---|---|---|
| S1 | Eget lager | Avtalsobjektets eget skördarlager | Mätt av skördaren |
| S2 | Egen skörd i snitt | Avtalsobjektets hela skörd, när mer levererats än lagret räcker till | Uppskattad |

Bilagan visar bara namnen; data, liggare, Excel och CSV använder koderna. Det finns inga fler källor: ett lass vars
avtalsobjekt och sortiment saknar skördardata stoppar månaden, och meddelandet säger vilka det gäller och vad som
brukar vara felet. Samma sak gäller ett vänt lass med mer volym än som fakturerats för avtalsobjektet och sortimentet.

Bilagans volym är alltid mätningens. En uppskattning står kvar som uppskattning: kommer skördardata för virket
senare ändras ingen bilaga och inget läggs på en senare faktura. Liggaren räknar av den levererade volymen mot den
nya skördardatan, så att samma virke inte kan levereras två gånger. Ett lass som vänds efter att det fakturerats
krediteras med `KREDITERING`-rader i månaden då det vänds.

## Viktigt att veta

Metoden är bara prövad mot simulerad data, och simulatorn bygger på samma antagande som metoden: varje lass har
skördardata för sitt avtalsobjekt och sitt sortiment. Där placerar den cirka 3,6 % av volymen fel per månad, destination
och sortiment, mot 14 % för att bara använda månadens skörd (`treedist backtest --manader 12`). Flera parametrar
bygger på antaganden. Se [begränsningarna](docs/metod.md#medvetna-begränsningar) innan siffrorna används skarpt.
