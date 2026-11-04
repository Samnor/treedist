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

## Det som `check` ännu inte ser

- **Fel kolumn som id i arbetsordertabellen.** Missen i kontroll 2. Kan fångas genom att kräva att arbetsordrarna
  i skördardata och inmätning finns i arbetsordertabellen. Ett nytt steg behöver en ny kontrollkatalog, eftersom
  båda de hittillsvarande nu har använts för beslut.
- **Dag och månad bytta när inget `datumformat` anges.** Den automatiska tolkningen kan inte veta vilket som
  avses. AGENTS.md säger därför att formatet alltid ska anges.
