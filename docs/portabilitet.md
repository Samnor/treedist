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

Kontrollkatalogen visar att de nya kontrollerna är specifika: de fångar felen de skrevs för men bara två av sex
nya. Falsklarmet i kontrollen är befogat: i den källan saknar två arbetsordrar skördardata, och varningen
pekar ut dem.

## Det som `check` ännu inte ser

- **Fel kolumn som id i arbetsordertabellen.** Missen i kontroll 2. Kan fångas genom att kräva att arbetsordrarna
  i skördardata och inmätning finns i arbetsordertabellen. Ett nytt steg behöver en ny kontrollkatalog, eftersom
  båda de hittillsvarande nu har använts för beslut.
- **Dag och månad bytta när inget `datumformat` anges.** Den automatiska tolkningen kan inte veta vilket som
  avses. AGENTS.md och exemplet anger därför alltid formatet.
