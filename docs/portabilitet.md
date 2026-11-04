# Portabilitet: hur väl går treedist att flytta till ny data?

Målet är att en enklare modell ska kunna koppla treedist till ett nytt källsystem genom att skriva en
källbeskrivning, utan att ändra metoden. [scripts/portability_bench.py](../scripts/portability_bench.py) mäter det
på två sätt, och första klättringen mot de måtten gjordes 2026-11-03.

## Måtten

- **Felkatalog.** Vanliga mappningsfel planteras i [exempelkällan](../examples/kalla/kalla.toml). Måttet är hur
  många `treedist check` upptäcker som `VARNING` eller `FEL`. Falsklarm är varningar på källor vars mappning är rätt.
- **Modellprov.** Simulerade månader skrivs som exporter med egna egenheter, och en modell får bara uppgiften och
  [AGENTS.md](../AGENTS.md). Godkänt betyder att tabellerna och fakturan blir exakt som facit, som modellen inte ser.

| Variant | Egenhet | Kräver |
|---|---|---|
| semikolon | Semikolon, decimalkomma, diameter i mm, kompakta datum, både transport- och bokföringsdatum | TOML |
| engelska | Tabb, latin-1, engelska namn, längd i dm, inmätt volym i dm³, datum som DD.MM.ÅÅÅÅ | TOML |
| lass | Inmätningen saknar arbetsorder; den finns i en separat fil per lass | `.py`, sammanslagning |
| koder | Sortiment som sifferkoder, arbetsorder utan prefix i inmätningen | `.py`, omkodning |

## Resultat

| Steg | Felkatalog | Falsklarm | Modellprov, Haiku |
|---|---|---|---|
| Baslinje | 8 av 12 | 10 på 5 källor | 4 av 4, cirka 93 000 tokens och 16 verktygsanrop per källa |
| Tom tabell med avslutade arbetsordrar och saknad liggare blir `INFO` | 8 av 12 | 0 | |
| Brutto lika med netto på varje rad | 9 av 12 | 0 | |
| Volym per lass, och lass som är kopior av andra | 11 av 12 | 0 | |
| Klasser som aldrig möter prislistans gränser tyder på klassmitt | 12 av 12 | 0 | |
| Lista över arbetsordrar utan skördardata, och tydligare dokumentation om decimalkomma och när `.py` behövs | 12 av 12 | 0 | |
| **Kontroll** med nya fel och nya månader som inget beslut sett | **2 av 6** | 1 på 5 källor | **4 av 4**, cirka 90 000 tokens och 16 verktygsanrop |

### Andra omgången

De fyra missarna från första kontrollen blev träningsfall, och en ny kontrollkatalog med fem andra fel frystes
innan något ändrades.

| Steg | Felkatalog | Falsklarm |
|---|---|---|
| Baslinje, med första kontrollens fel som träning | 14 av 18 | 0 |
| Datum som inte följer ett angivet `datumformat` är `FEL`, i stället för att tolkas automatiskt | 15 av 18 | 0 |
| Mottagningsplats och planerad destination ska i stort sett nämna samma sågverk | 17 av 18 | 0 |
| Skördad volym ska stämma med klasser och antal stockar, normalt cirka 1,3 gånger en cylinder på klassbottnarna | 18 av 18 | 0 |
| **Kontroll 2** med fem nya fel | **4 av 5** | 0 |

Kontrollen generaliserade bättre den här gången, 4 av 5 mot 2 av 6, eftersom stegen jämför uppgifter med varandra
i stället för att leta efter ett visst fel. Kvoten mellan skördad volym och klassernas cylinder var 1,28–1,36 i alla
nio korrekta källor, och gränsen sattes brett, 0,7–2,5, eftersom verklig data kan avvika från simulatorn.

### Sammanfattning

Haiku klarade alla åtta källor med bara AGENTS.md, varav fyra krävde en egen `.py`. Det som förbättrades är
alltså främst att `check` hittar fel som en modell annars inte märker, och att den slutar larma om sådant som
inte är fel. Agenternas tidsåtgång sjönk inte mätbart.

Första kontrollkatalogen visade att de första kontrollerna var specifika: de fångar felen de skrevs för men bara två av sex
nya. Falsklarmet i kontrollen är befogat: i den källan saknar två arbetsordrar skördardata, och varningen
pekar ut dem.

### Installerat med pip (2026-11-04)

Samma fyra källor, men modellen fick en katalog skapad med `treedist init` ur paketet och körde `treedist` från
en ren miljö, utan repot. Rättat med `portability_bench.py rätta`.

| Omgång | AGENTS.md | Modellprov, Haiku |
|---|---|---|
| 1 | Paketet byggt före omskrivningen: nämner `uv run`, `pytest` och `profil_enkel` | 4 av 4, 86 000–91 000 tokens, 13–17 verktygsanrop |
| 2 | Version 0.2.0: `treedist selftest`, ingen modell att välja | 4 av 4, 74 000–94 000 tokens, 10–18 verktygsanrop |

- **Installationen kostar inget i träffsäkerhet eller tokens.** Modellerna följde `selftest`, `kontrakt`, `check` och
  `run` i projektkatalogen utan att behöva repot.
- **Ingen valde modell själv.** Alla körde standardmodellen, som AGENTS.md säger.
- **`kodning` saknades i AGENTS.md.** En modell hittade nyckeln genom att prova efter ett UTF-8-fel; nu står
  tabellnycklarna uppräknade.
- **Provet var inte helt blint.** Agenterna startades i repot och fick därför också repots AGENTS.md från
  sessionens början, med `profil_enkel`. Två agenter i omgång 2 nämnde den fast den inte fanns i deras katalog.
  I riktig användning läser modellen bara katalogens AGENTS.md, som `init` lägger i roten där verktygen hittar den.

### Andra plattformar än filexporter (2026-11-04)

Fyra nya källor som ingen TOML-mappning klarar, skapade med `portability_bench.py skapa --plattform`. Haiku fick
en katalog från `treedist init` och treedist installerat med pip från GitHub, version 0.2.0. Innan provet löstes
varje uppgift med en referensadapter, och ett planterat fel per uppgift underkändes.

| Källa | Egenhet | Planterat fel, syns i `check`? | Haiku |
|---|---|---|---|
| `i_lager` | SQLite-datalager: surrogatnycklar, dimensioner, dm³, ommätta lass som ogiltiga versioner | Ogiltiga versioner med: `FEL`, dubblerat lass | Godkänd, 103 000 tokens, 15 anrop |
| `j_api` | REST-API: nästlad JSON, lass i sidor, tider i UTC | UTC-datum i stället för svensk dag: **tyst** | Godkänd, 93 000 tokens, 16 anrop |
| `k_rapport` | BI-rapport: förtext, BOM, skördad volym pivoterad per diameterklass, delsummor, sidfot | Delsummor som rader: `FEL` | Godkänd, 105 000 tokens, 20 anrop |
| `l_stordator` | Fast postlängd med posttyper, underförstådda decimaler, trailer | Två decimaler i stället för tre: `FEL` | Godkänd, 98 000 tokens, 15 anrop |

- **4 av 4 godkända,** till cirka 15 % fler tokens än filexporterna. Alla skrev en `.py`, och alla lade till egna
  kontroller mot källan: delsummor, antal poster i trailern, sidnummer i följd.
- **Den tysta fällan klarades.** API-agenten räknade transportdagen i svensk tid; 12 av 46 lass hade annars hamnat
  på fel dag.
- **Datalagrets `VARNING` är verklig.** 49 % S3 kommer av att en arbetsorder saknar skördardata, och
  referensadaptern ger samma. Agenten förklarade den och hittade inte på en omklassning.
- **Två val som inte syns i en månad.** Datalageragenten filtrerade skördardatan på fällningsdag, vilket skulle tappa
  sent rapporterade rader från månad två. Stordatoragenten härledde `producerat_handelssortiment` ur skördardatan.
  Båda står nu som fallgropar i AGENTS.md, tillsammans med UTC-datum.
- **Samma förbehåll som förut:** agenterna startades i repot och såg också dess AGENTS.md från sessionens början.

## Klättring av installationen (2026-11-04)

[scripts/setup_climb.py](../scripts/setup_climb.py) mäter hela vägen för en billig modell: treedist byggs från
arbetskatalogen som ett hjul i en ny miljö, `treedist init` görs i en tom katalog per uppgift och körning, och
Haiku kopplar in källan med Claude Code utan gränssnitt, från den katalogen. Modellen får bara uppgiftens text,
katalogens AGENTS.md och det installerade paketet. Källbeskrivningen rättas mot facit, och kostnad, turer och tid
loggas i `climb/setup_logg.jsonl`.

- **Uppgifter.** Utveckling: de fyra filexporterna, de fyra plattformarna och `m_lagerhistorik`, andra månaden ur
  ett datalager med alla månader, där sent rapporterade rader fälldes månaden före. Kontroll: andra frön och
  källor, `skapa --kontroll` med och utan `--plattform` och `--historik`, som inget beslut använt.
- **Poäng** per uppgift: kostnad plus 0,25 USD per underkänd körning. Ett steg tas om poängen sjunker med mer än
  två standardfel och minst 5 %.
- **Behörigheter.** Skalkommandon körs i Claude Codes sandlåda, som håller skrivningar i projektkatalogen; övrigt
  nekas. En körning som stannar utan källbeskrivning efter ett nekat kommando räknas som ogiltig, inte underkänd.

| Steg | Ändring | Utfall | Beslut |
|---|---|---|---|
| Baslinje | v0.2.0 med fallgroparna, `ab0adf3` | 36 av 36, 0,029 USD och 22,9 turer per körning | |
| A | Kolumner som redan har kontraktets namn läses utan `kolumner`; prislistan behöver bara `fil` | 36 av 36; felet "prislistans kolumner saknas" kom i 5 av 81 körningar före och 0 av 54 efter | Tagen: tar bort en felklass, kostar inget |
| Exempel | `examples/kalla/kalla.py`, samma källa som `.py`-adapter, nämnd i AGENTS.md | −20 % kostnad, −4,8 turer; lästa filer ur det installerade paketet från 2,7 till 0,3 per körning | Tagen: −0,006 USD i två oberoende mätningar, tillsammans cirka 3 standardfel |
| Månadsrader | Utan rapportmånad är exporten månadens rader | Inget mätbart; vägran i datalagret försvann redan med sandlådan | Inte tagen |
| Låt `check` leta | AGENTS.md: leta inte avvikelser för hand | Grep från 4,5 till 2,5 per körning, −2,9 turer, men inom bruset | Inte tagen |
| Avstämt | `run` skriver att fakturan är avstämd mot inmätningen | Färre öppnade utdatafiler, men inom bruset | Inte tagen |
| Id-form | Arbetsorder-id i arbetsordertabellens form | Riktat på `d_koder`: 12 av 12 mot 9 av 12; alla körningar 0 av 16 fel mot 5 av 28 | Tagen: varje fel var just fel form |

**Kontroll**, slutlig version mot baslinjen på nio uppgifter som inget beslut använt, tre körningar var:
kostnaden −27 % (−0,0083 ± 0,0022 USD per körning), −4,0 turer och 21 s kortare, 27 av 27 godkända i båda.
Kontrollen bekräftar alltså vinsten i kostnad och turer. Träffsäkerheten kunde den inte pröva, eftersom baslinjen
inte heller föll på kontrolluppgifterna.

- **Billigt.** En körning kostar cirka 0,02 USD och tar en och en halv minut; en utvärdering med 36 körningar
  kostar under en dollar.
- **Bruset är stort.** Tre till fyra körningar per uppgift skiljer bara större steg. Sällsynta fel prövas bäst
  riktat på den uppgift där de uppträder.
- **Läckor.** Testkatalogens sökväg innehåller repots namn, och två körningar försökte läsa repot; båda nekades.

### Andra omgången: hela skalet och svåra fällor

Varje nekat kommando fick Haiku att ge upp skalet och leta i filerna för hand, så testet mätte sina egna
behörigheter. Nu tillåts alla skalkommandon i sandlådan, som fortfarande håller skrivningar i projektkatalogen och
saknar nätverk. Då klarades alla nio utvecklingsuppgifter, 36 av 36, till 0,020 USD, 11 turer och 78 s per
körning, och de gav ingen signal längre.

Fyra nya uppgifter bygger på fällor ur AGENTS.md, `skapa --svara`. Referensadaptern klarar var och en, och det
lockande felet underkänns i alla, två av dem utan att `check` säger något:

| Uppgift | Fälla | Lockande fel, syns i `check`? |
|---|---|---|
| `s_omklassat` | Industrin har klassat om en del lass; bokföringsdag ibland i månaden efter | Skördarens sortiment som `handelssortiment`: **tyst** |
| `t_kredit` | Volymer utan tecken, kolumn för debet och kredit; ommätta lass krediteras och debiteras igen | Kreditraderna som positiva: `FEL`, dubblerat lass |
| `u_per_bruk` | En fil per sågverk, sågverket bara i filnamnet, planerat sågverk på varje rad | Planerat sågverk som mottagningsplats: **tyst** |
| `v_kalkylblad` | Datum som serienummer, tusentalsavgränsare, summarad | Fel epok för serienumren: `FEL`, datum efter perioden |

Baslinjen klarade 22 av 24. Båda missarna var i `t_kredit`: adaptern gav också `antal_matenheter` kreditradens
tecken. Valideringen ersätter tyst ett antal som inte är positivt, så felet syntes inte.

| Steg | Ändring | Utfall | Beslut |
|---|---|---|---|
| H | `check` ger `FEL` när `antal_matenheter` är negativt i källan: antalet är alltid positivt, bara volymerna byter tecken | `t_kredit` 12 av 12 mot 9 av 12; i 3 av körningarna kom felet och modellen rättade | Tagen |

**Kontroll** på alla 13 kontrolluppgifter, tre körningar var: 39 av 39 mot baslinjens 38 av 39, där missen var
samma fel i `x_kredit`. Kostnaden är oförändrad, cirka 0,02 USD per körning. Sammantaget över alla körningar med
kreditfällan: 11 av 15 före, 18 av 18 efter. Utvecklingsuppgifterna klarades 39 av 39 med den slutliga versionen.

Haiku klarade alltså de tysta fällorna i omklassning och per sågverk varje gång. Det som fällde den var ett tal
som kontraktet anger men som ingen kontroll såg.

```bash
uv run python scripts/setup_climb.py prova --not "vad som ändrats" --korningar 4
```

```bash
uv run python scripts/setup_climb.py jamfor BAS KANDIDAT
```

## Det som `check` ännu inte ser

- **Fel kolumn som id i arbetsordertabellen.** Missen i kontroll 2. Kan fångas genom att kräva att arbetsordrarna
  i skördardata och inmätning finns i arbetsordertabellen. Ett nytt steg behöver en ny kontrollkatalog, eftersom
  båda de hittillsvarande nu har använts för beslut.
- **Dag och månad bytta när inget `datumformat` anges.** Den automatiska tolkningen kan inte veta vilket som
  avses. AGENTS.md säger därför att formatet alltid ska anges.
