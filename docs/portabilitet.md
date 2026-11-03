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

Haiku klarade alla åtta källor med bara AGENTS.md, varav fyra krävde en egen `.py`. Det som förbättrades är
alltså främst att `check` hittar fel som en modell annars inte märker, och att den slutar larma om sådant som
inte är fel. Agenternas tidsåtgång sjönk inte mätbart.

Kontrollkatalogen visar att de nya kontrollerna är specifika: de fångar felen de skrevs för men bara två av sex
nya. Falsklarmet i kontrollen är befogat: i den källan saknar två arbetsordrar skördardata, och varningen
pekar ut dem.

## Det som `check` ännu inte ser

Från kontrollkatalogen, i ordning efter hur troliga felen är i verklig data:

- **Dag och månad bytta i datumformatet.** Ger rimliga datum fram till den tolfte. Kan fångas genom att jämföra
  transportdatum med fällningsdatum per arbetsorder, eller genom att se att dagarna aldrig passerar 12.
- **Fel kolumn som mottagningsplats eller planerad destination.** Kan fångas genom att jämföra mottagningsplatser
  med planerade destinationer och prislistans destinationer: helt olika mängder tyder på fel kolumn.
- **Antal stockar mappat som skördad volym.** Ger ungefär 1 m³ per stock, som ligger inom gränsen. Kan fångas
  genom att jämföra skördad och inmätt volym för arbetsordrar som avslutats.
