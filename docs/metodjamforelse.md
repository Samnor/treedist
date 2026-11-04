# Jämförelse av metoder

Uppgiften: skatta en matris över diameter och längd per destination och handelssortiment för en månads leveranser. Vid
leverans finns bara inmätt brutto- och nettovolym per arbetsorder eller lastbil. Skördardatan ger stockar, diameter och
längd. Varje arbetsorder har en planerad destination, och skörd och leverans är var sin kampanj om 1–3 veckor. På sommaren
börjar leveranserna medan skördaren är kvar, se [antaganden](antaganden.md).

**Slutsats: metod C, lagerliggare med mjuk matchning, är standard i `treedist`.** Den ger lägst fel i alla scenarier. I
basscenariot är prisfelet 9,1 kr/m3fub mot 41,7 om man bara använder månadens skörd.

## Metoderna

**A. Lagerliggare.** Massbalans per arbetsorder och sortiment: skördat virke läggs i lager, leverans dras ur lagret och
fördelas som lagret. Virke utan skördardata lånar från alla arbetsordrar i sortimentet.

**B. Faltning på sortimentsnivå.** Ingen koppling till enskilda arbetsordrar. Skörden per planerad destination viktas med
hur stor andel som enligt en lagringstidsfördelning levererades just den månaden. Finns bara i jämförelseskriptet.

**C. Lagerliggare med mjuk matchning.** A, men virke utan skördardata lånar från alla arbetsordrar med vikter efter
likhet: samma destination väger 16 gånger mer, samma grupp 4 gånger mer, och arbetsorderns andra sortiment används som
ledtråd när det finns.

## Resultat

Medelvärden från 8 nya simuleringar om 12 månader, med 3 destinationer, som inte använts till något tidigare. Felindex är
andelen volym i fel cell per månad, destination och sortiment. Kumulativt är samma mått över hela perioden. Skriptet
[compare_methods.py](../scripts/compare_methods.py) återskapar [resultaten](metodjamforelse_resultat.csv).

| Scenario | Metod | Felindex | Prisfel, kr/m3fub | Kumulativt prisfel | Värdetäckning | Celltäckning |
|---|---|---|---|---|---|---|
| Bas | Naiv (månadens skörd) | 17,1 % | 41,7 | – | – | – |
| | B Faltning | 11,7 % | 26,7 | – | – | – |
| | A Liggare | 6,4 % | 11,7 | 8,2 | 91 % | 98 % |
| | **C Mjuk matchning** | **5,5 %** | **8,6** | **4,8** | 93 % | 98 % |
| 30 % utan skördardata | Naiv | 18,8 % | 44,8 | – | – | – |
| | B Faltning | 13,8 % | 30,6 | – | – | – |
| | A Liggare | 11,2 % | 26,5 | 22,2 | 85 % | 96 % |
| | **C Mjuk matchning** | **8,8 %** | **16,5** | **8,6** | 87 % | 97 % |
| Stora skillnader inom arbetsorder | Naiv | 22,2 % | 52,8 | – | – | – |
| | B Faltning | 16,0 % | 37,2 | – | – | – |
| | A Liggare | 8,8 % | 15,6 | 9,1 | 91 % | 95 % |
| | **C Mjuk matchning** | **8,5 %** | **14,5** | **6,9** | 88 % | 95 % |

Värdetäckning är hur ofta månadens värde låg inom 90 %-intervallet, och celltäckning motsvarande per cell. Fröna 81–88
är nya för den här körningen, som också är den första med säsongens lagringstider. Med kortare lagring blir den naiva
metoden bättre, men C har fortfarande en fjärdedel av dess fel. Skillnaden mellan frön är av samma storlek som skillnaden
mellan A och C i scenariot med stora skillnader inom arbetsorder.

Bas-scenariot har 10 % virke helt utan skördardata, 10 % sen rapport, 5 % omdirigerat virke, och cirka 44 % av
arbetsordrarna levererar i mer än en månad. Med eget lager är felindexet per arbetsorder 0,04, utan skördardata 0,21.

**Felet är i hög grad ett månadsskiftesfel.** Över tolv månader är prisfelet bara 4,8 kr/m3fub mot 9,1 per månad, eftersom
en arbetsorder som delas över ett skifte blir rätt i summan. Det som återstår över tid är virke utan skördardata.

## Experiment

Alla idéer prövades på egna utvecklingsfrön innan slutkontrollen. Prisfel i kr/m3fub.

| Idé | Effekt | Beslut |
|---|---|---|
| FIFO ur lagret | Sämre än proportionellt | Förkastad |
| Viktning efter lagringstid | Cirka 1 % bättre | Förkastad, kräver antagen lagringstid |
| Datumstyrd dragning | Ingen skillnad när leverans följer efter skörd | Behållen, utesluter omöjliga dragningar |
| Hård hierarki till mjuk matchning | 10,9 → 9,4, och 18,9 → 14,6 med 30 % utan data | Behållen |
| Arbetsorderns andra sortiment | 9,4 → 8,9, och 14,6 → 13,7 | Behållen |
| Volymbalans som avslöjar diameterfel | 1–2 %, försämrar ibland kumulativt | Förkastad |
| Faktisk mottagningsplats i stället för planerad | 16,0 → 8,6 med 5 % omdirigerat virke | Stöds, starkt rekommenderad |
| Rest efter månadsskifte räknas som osäker | Värdetäckning 77 → 82 % | Felrättning |
| Bredare blandning av skördeblock | Värdetäckning 82 → 86 % | Behållen |
| Bandbredd efter förutsägelsens skattade fel | Spridning i värdet 1,57 → 1,39 gånger intervallets, prisfel oförändrat | Behållen |
| S2 och S3 som en slumpad del av skörden, inte hela | Värdetäckning med C på samma frön: 88 → 89 %, 79 → 84 % och 85 → 88 % | Behållen, ersätter två fasta konstanter |
| Automatisk parameterklättring, 30 kandidater i 10 parametrar | Inget steg slog bruset. Närmast `min_forwarding_days` 3: −0,15 ± 0,08 i poäng. `cluster_volume` från 2400 och uppåt, och `donor_sibling_cm` under 1,5, saknar effekt | Parametrarna ligger i ett lokalt optimum |
| Designeffekt 40 i stället för 20 efter säsongsbasen | Värdetäckning 88 → 90 %, 86 → 86 % och 88 → 91 %, prisfel oförändrat | Behållen |
| Stockantal per leverans | 7,7 → 2,1 i tidigare simulering | Uppgiften finns inte |
| Klättring: givare viktade efter inmätt medelstockvolym | Poäng −4,96 ± 0,57 | Förkastad, kräver stockantal som inmätningen saknar |
| Klättring: destinations- och gruppvikt skattade varje månad ur givarnas egna medeldiametrar | Hela vägen −0,06 ± 0,28, halvvägs −0,20 ± 0,18. Prisfel −1,0 och −0,9 när destinationen är oberoende av grovlek, men +0,1 till +0,6 i övriga | Förkastad. Visar att vikten 16 för destination bara stämmer om sågverken verkligen väljs efter grovlek; kontrollera det i verklig data |
| Klättring: äldsta virket först när leveranserna började under skörden | Poäng −1,05 ± 0,20, prisfel 11,9 → 10,9 och bättre i alla fyra scenarier. Håller på kontrollfröna: −0,71 ± 0,20 | Behållen. Till skillnad från FIFO ovan gäller den bara när lastbilarna följer skördaren |
| Klättring: smalare blandning av skördeblock när lastbilarna följde skördaren | Poäng −0,02 ± 0,07, värdetäckning 92,1 → 91,5 % | Förkastad |
| Parameterklättring efter föregående steg, 24 kandidater | Inget steg slog bruset | Parametrarna ligger kvar i ett lokalt optimum |

### Förenkling

Därefter klättrade metoden åt andra hållet: varje del prövades borttagen och fick kosta högst 0,25 i poäng, och hela
förenklingen högst 1,0. Poängen är prisfel plus 0,3 per procentenhet som värdetäckningen avviker från 90 %. Skillnad i
poäng mot metoden före förenklingen, på utvecklingsfröna, där plus är sämre.

| Borttagen del | Skillnad i poäng | Värdetäckning | Beslut |
|---|---|---|---|
| Datum per leverans och skotningstid; kvar är bara äldsta först om leveranserna började under skörden, annars pro rata | ±0,000 | 92,1 % | Borttagen. Exakt samma resultat |
| Tolerans på 3 % innan överleverans blir S2 | +0,06 | 92,2 % | Borttagen. Prisfel oförändrat |
| Delar av givarens skörd i S3; kvar är en hel givare per dragning | +0,00 | 90,6 % | Borttagen |
| Diameterbias i Monte Carlo | −0,02 | 88,5 % | Borttagen tillsammans med skördeblocken |
| Skördeblock i S1 och S2 | +0,68 | 85,4 % | För dyr ensam. Borttagen när `design_effect` samtidigt gick från 40 till 200 |
| Dirichlet med fast styrka när färre än fem givare finns, prövad efter de andra | ±0,000 | 91,2 % | Borttagen |
| Syskonsortimentet i givarvikten | +0,48 | 92,1 % | Behållen |
| Gruppvikten | +0,39 | 92,2 % | Behållen |
| Destinationsvikten | +1,66, och +4,0 kr/m3fub med 30 % utan skördardata | 91,6 % | Behållen |
| Pro rata i stället för äldsta först | +1,69 | 89,9 % | Behållen |
| **Allt borttaget ovan, med `design_effect` 200** | **+0,14** när koden tagits bort (+0,08 bakom flaggor; skillnaden är att slumptalsföljden ändrades), på kontrollfröna +0,14 ± 0,18 | 90,8 %, på kontrollfröna 90,5 % | **Standard sedan 2026-11-03** |

Prisfelet är detsamma som före förenklingen, 10,9 kr/m3fub i snitt över klättringens scenarier, eftersom alla
borttagna delar utom toleransen bara rörde osäkerheten. Det som försvann är tio parametrar och tre lager i Monte
Carlo-modellen: skördeblock, delar av givare och diameterbias. Intervallen styrs nu av en parameter, `design_effect`.
Fakturorna i demot blev identiska på öret.

### En femtedel av delarna

Hur liten kan metoden bli och ändå göra det mesta av jobbet? Komplexitet räknas som antal delar en läsare måste känna
till för att följa en skattning: varje regel och varje tal, 23 i standardmodellen, listade i
[modell.py](../scripts/modell.py). Bokföring som varje modell behöver för en korrekt faktura räknas inte: vända lass,
korrigeringar, omklassning, flera destinationer och avskrivning. Prestanda är hur stor del av avståndet till den naiva
skattningen, månadens skörd, som modellen stänger, som andel av vad standardmodellen stänger. Målet var högst 20 % av
delarna och minst 80 % av prestandan i varje scenario, inte bara i snitt.

`modell.py sok` började från den minsta modellen, tre delar: liggaren, sortimentets medel för det som inte ryms i lagret
och `OKÄND` när sortimentet saknar skördardata. Sedan lade den tillbaka den grupp av delar som gav mest prestanda per del.
Prisfel i kr/m3fub på utvecklingsfröna; naivt är det 44,0 och standardmodellens 10,9.

| Modell | Delar | Prisfel | Prestanda | Sämsta scenario |
|---|---|---|---|---|
| Minsta: liggare, pro rata, sortimentets medel, `OKÄND` | 3 (13 %) | 16,5 | 83 % | 66 %, 30 % utan skördardata |
| + bruttovolym ur lagret | 4 | 16,6 | 83 % | 66 % |
| + kalibrering | 5 | 16,6 | 83 % | 66 % |
| + AO-historik för överleverans (S2) | 4 | 16,2 | 84 % | 67 % |
| + syskonsortimentet | 6 | 15,4 | 87 % | 74 % |
| + äldsta först | 4 | 15,1 | 87 % | 71 % |
| + gruppvikten | 4 | 15,1 | 87 % | 75 % |
| + intervall, tio delar | 13 | 16,5 | 83 % | 66 % |
| **+ destinationsvikten: `enkel`** | **4 (17 %)** | **13,5** | **92 %** | **90 %, basscenariot** |
| `enkel` + äldsta först | 5 (22 %) | 12,0 | 97 % | 95 % |

**Modellen [enkel](../modeller/enkel.toml) har 4 av 23 delar och stänger 92 % av avståndet**, minst 90 % i varje scenario.
På kontrollfröna, som inget beslut använt, är prisfelet 13,8 mot standardens 11,3, och prestandan 93 %. Den är liggaren
med pro rata-dragning och nettovolym, och allt som inte ryms i lagret får ett volymviktat medel av sortimentets
arbetsordrar där samma destination väger 16 gånger mer. Destinationsvikten är den enda del som ensam räddar scenariot
med 30 % utan skördardata.

Det som går förlorat:

- **Intervallen.** `enkel` har ingen Monte Carlo och inga `std`, `p05` eller `p95`. Säkerhetsklasserna visar fortfarande
  hur säker fördelningen är. Intervallen kostar tio delar och påverkar inte skattningen alls.
- **Kalibreringen och bruttovolymen** ändrar nästan inte prisfelet. De styr hur länge lagret räcker och därmed hur
  mycket som blir preliminärt och korrigeras senare, inte fördelningen.
- **Äldsta först** är den enda utelämnade del som är värd sitt pris om en femte del tillåts: prisfelet går från 13,5 till
  12,0 kr/m3fub. Den betyder mest på sommaren, när leveranserna börjar under skörden.

Allt är prövat mot simulatorn. Att destinationen säger så mycket om grovleken bygger på hur simulatorn kopplar
sågverk och dimension; i scenariot där destinationen är oberoende av grovlek ger `enkel` ändå 91 %.
[Flödesrapporten för enkel](flodesrapport_enkel.html) visar demots månader med modellen.

### Hälften av delarna, med intervall

Med högst halva delarna, 11 av 23, ryms intervall om de görs lättare. Standardmodellens intervall kostar tio delar.
Lätta intervall är tre: Dirichletbrus kring fördelningen efter effektivt antal stockar (`design_effect`, och
`default_log_volume` där antal saknas). Ändlighetskorrektionen, en hel givare per dragning i S3 och volymens mätfel
lämnas ute, med brytarna `finite_population`, `donor_draws` och `volume_error`. Med samma `design_effect`, 200, träffar
de lätta intervallen 89 % ensamma och 92 % i den färdiga modellen, så ingen ny parameter behövdes.

`modell.py sok --delar 0.5 --intervall` började från den minsta modellen med lätta intervall, sex delar, och lade till
den grupp som sänkte poängen mest per del. Poängen är klättringens, prisfel plus 0,3 per procentenhet som
värdetäckningen avviker från 90 %, så att intervallens kalibrering räknas. Standardmodellen har 12,11.

| Steg | Delar | Prisfel | Täckning | Poäng | Prestanda |
|---|---|---|---|---|---|
| Minsta med lätta intervall | 6 (26 %) | 16,5 | 85 % | 18,70 | 83 % |
| + destinationsvikten | 7 | 13,5 | 89 % | 14,80 | 92 % |
| + äldsta först | 8 | 12,0 | 91 % | 13,17 | 97 % |
| **+ gruppvikten: `halv`** | **9 (39 %)** | **11,4** | **92 %** | **12,55** | **99 %** |
| + AO-historik (S2) | 10 | 11,3 | 92 % | 12,54 | 99 % |
| + bruttovolym | 11 (48 %) | 11,2 | 92 % | 12,44 | 99 % |

De två sista stegen slår inte bruset mellan fröna: elva delar är −0,11 ± 0,08 bättre i poäng än nio. Därför sparades
nio delar. **[halv](../modeller/halv.toml) har 9 av 23 delar och stänger 99 % av avståndet** till den naiva
skattningen, minst 97,9 % i varje scenario. På kontrollfröna är prisfelet 12,0 mot standardens 11,3, prestandan 98 % och
värdetäckningen 90,8 %. Den är `enkel` med äldsta först, gruppvikten och lätta intervall.

Vad de övriga delarna gör, sett från `halv`:

- **Syskonsortimentet** är det enda som når standardens nivå, poäng 12,16, men kostar tre delar och spräcker budgeten.
- **Ändlighetskorrektionen** ensam gör intervallen för smala, täckning 81 %. Den hör ihop med volymfelet och
  `design_effect` 200 i standardmodellen; utan de andra är det bättre att lämna den.
- **En hel givare per dragning** gör intervallen för breda, täckning 97 %.
- **Volymfelet** ändrar täckningen mindre än en procentenhet. Fakturans intervall, `std_fordelning`, påverkas inte
  av det alls, eftersom fakturans volym är inmätningens.
- **Kalibreringen och bruttovolymen** påverkar fortfarande nästan bara hur länge lagret räcker.

[Flödesrapporten för halv](flodesrapport_halv.html) visar demots månader med modellen.

### Åtta delar: bruset efter volymen

Läses inte antalet stockar blir koncentrationen volym / (`default_log_volume` × `design_effect`). Då spelar bara
produkten roll, och de två talen blir ett: 50 m3fub per oberoende enhet. Brytaren är `log_counts`. Det tar bort en del
och dessutom ett krav på indatan, eftersom `antal_stockar` inte längre behövs för intervallen.

| Modell | Delar | Prisfel | Täckning | Poäng | Prestanda | Mot `halv` |
|---|---|---|---|---|---|---|
| `halv` | 9 | 11,4 | 92 % | 12,55 | 99 % | |
| **`halv` med bruset efter volymen: `halv-volym`** | **8 (35 %)** | **11,4** | **92 %** | **12,67** | **99 %** | **+0,12 ± 0,10** |
| … med `design_effect` 400 | 8 | 11,4 | 96 % | 13,08 | 99 % | +0,53 |
| … och utan gruppvikten | 7 (30 %) | 12,0 | 92 % | 13,22 | 97 %, minst 95 % | +0,67 ± 0,19 |
| … och utan äldsta först | 6 | 13,5 | 90 % | 14,90 | 92 % | +2,35 |

**[halv-volym](../modeller/halv-volym.toml) har 8 av 23 delar** och samma prisfel som `halv`; bara intervallen ändras,
och det kostar 0,12 i poäng, inom de 0,25 som ett förenklingssteg får kosta. På kontrollfröna är prisfelet 12,0,
prestandan 98 % och värdetäckningen 91,3 %. Att också ta bort gruppvikten kostar 0,55 till och klarar inte den regeln.
Samma `design_effect`, 200, fungerar här också.

[Flödesrapporten för halv-volym](flodesrapport_halv-volym.html) visar demots månader med modellen.

### Stresstest: när verkligheten skiljer sig från simulatorn

Kontrollfröna är nya dragningar ur samma simulator. En del som förenklingen tog bort kan ha sett onyttig ut bara för
att simulatorn aldrig gav den något att göra. `scripts/stresstest.py` vrider upp en sak i taget som verkligheten kan ha
mer av, och kör de sparade modellerna på samma simuleringar, med frön 501–506 som inget beslut har använt.
Prestanda är andelen av standardmodellens förbättring mot den naiva skattningen i samma scenario.

| Scenario | Prisfel standard | `halv-volym` mot standard | Prestanda `halv-volym` | `enkel` | Täckning standard | Täckning `halv-volym` |
|---|---|---|---|---|---|---|
| bas | 8,65 | +0,19 ± 0,10 | 99 % | 96 % | 91 % | 95 % |
| skördaren mäter 5 % för mycket | 8,71 | +0,21 ± 0,08 | 99 % | 96 % | 93 % | 95 % |
| 5 % spill vid hantering | 8,74 | +0,22 ± 0,09 | 99 % | 96 % | 93 % | 95 % |
| 10 % skillnad brutto–netto | 8,67 | **+0,46 ± 0,11** | 98 % | 96 % | 91 % | 95 % |
| lång eftersläpning | 8,90 | +0,06 ± 0,08 | 100 % | 98 % | 90 % | 97 % |
| 40 % rapporteras sent | 11,90 | **+0,80 ± 0,17** | **97 %** | 93 % | 89 % | 89 % |
| 25 % omdirigeras | 9,78 | +0,29 ± 0,06 | 99 % | 97 % | 92 % | 93 % |
| mest travmätning | 8,64 | +0,18 ± 0,10 | 99 % | 96 % | 92 % | 95 % |
| klumpiga avlägg | 10,91 | +0,04 ± 0,17 | 100 % | **89 %** | **88 %** | 95 % |
| små arbetsordrar | 6,58 | **+0,39 ± 0,08** | 98 % | 95 % | 98 % | 99 % |
| stora diameterfel | 11,32 | +0,16 ± 0,10 | 99 % | 96 % | **79 %** | 94 % |

- **`halv-volym` behåller minst 97 % av förbättringen i varje scenario.** Gapet mot standard växer bara där en
  borttagen del får något att göra: historiken när 40 % rapporteras sent (+0,8), bruttovolymen när brutto och netto
  skiljer 10 % (+0,5), och delarna för små arbetsordrar (+0,4).
- **Kalibreringen betyder nästan inget för prisfelet**, inte ens när skördaren mäter 5 % fel eller 5 % spills.
  Liggaren skalar om till inmätt volym, så ett jämnt volymfel ändrar inte fördelningen. Att ta bort
  `harvester_bias` och `handling_loss` är alltså robust här.
- **Intervallen i de enkla modellerna är bredare och tål mer.** Standardmodellens täckning faller till 79 % med stora
  diameterfel och 88 % med klumpiga avlägg; `halv-volym` ligger mellan 89 % och 99 %. Priset är för breda intervall,
  95 % i de flesta scenarier och 99 % för små arbetsordrar.
- **`enkel` faller till 89 %** med klumpiga avlägg (+3,4 ± 1,2). Den saknar äldsta först, som är det som följer
  avläggen när de körs ut ett i taget.
- **Testet kan inte vrida på** fler sortiment, säsongsskillnader i grovlek eller arbetsorder-id som inte stämmer
  mellan källorna. Simulatorn har inga parametrar för dem.

```bash
uv run python scripts/stresstest.py
```

## För- och nackdelar

| | Fördelar | Nackdelar |
|---|---|---|
| **A Liggare** | Volymen stämmer per arbetsorder. Fördelningen blir rätt i summan när arbetsordern är tömd. Bara antaganden som går att förklara. Ger säkerhetsklass per volym. | Kräver liggare över månader och en körning i taget. Svagt för virke utan skördardata. Kräver att arbetsordernumret stämmer mellan systemen. |
| **B Faltning** | Enkel, kräver ingen liggare och ingen koppling till arbetsorder. Bra rimlighetskontroll. Fungerar om kopplingen saknas helt. | Två till tre gånger så stort prisfel som C. Bygger på en antagen lagringstid. Kan inte se omdirigerat virke på arbetsordernivå. Ger ingen säkerhetsklass eller korrigering. |
| **C Mjuk matchning** | Bäst i alla scenarier, framför allt när mycket virke saknar skördardata. Motsvarar vedertagen imputering i skogsforskningen. Tål tunna grupper, eftersom ingen hård gräns behövs. | Vikterna är inställda mot simulatorn. Vinsten är ett bästa fall, eftersom destination och grupp i simulatorn är just det som skapar skillnaderna. |

## Vad heter uppgiften?

Jag hittade inget etablerat namn på hela problemet, och ingen studie som gör exakt detta. Delarna har däremot namn:

| Del av uppgiften | Akademiskt begrepp | Fält |
|---|---|---|
| Sprida känd total över fina klasser med hjälp av en annan datakälla | **Disaggregering**, även nedskalning. Dasymetrisk kartering är geografins version av samma idé. | Statistik, geografi |
| Fördelning saknas och lånas från liknande enheter | **Imputering**, särskilt k-NN och *most similar neighbour* (MSN) | Skoglig inventering |
| Följa material genom lager och blandning | **Massbalans**, *residence time distribution*, *lot genealogy* | Processindustri |
| Förlorad koppling mellan stock och mätvärde | **Spårbarhet**, *forest-to-mill traceability* | Skoglig logistik |

Närmast är därför *disaggregering med skördardata som hjälpvariabel, med massbalans över lager och imputering vid
saknade data*. Ekologisk inferens och statistisk matchning är besläktade men passar sämre: den första skattar samband
ur enbart aggregat, och den andra länkar två datakällor utan att fördela en känd total.

Skogforsk är närmast i praktiken. Verktyget *hprImputation* använder kMSN på lagrade skördardata, men för att prognostisera
utfall i planerade bestånd före avverkning, inte för att fördela levererad volym.

## Liknar våra resultat andras?

Ja i riktning, men siffrorna går bara delvis att jämföra.

| Studie | Uppgift | Fel |
|---|---|---|
| Noordermeer m.fl. 2023 | k-NN med laserdata och skördardata som referens, 49 bestånd | 0,13 för diameter, 0,10 för sågad volym |
| Maltamo m.fl. 2019 | Samma ansats, 47 bestånd | Under 0,2 |
| Vårt virke utan skördardata | Mjuk matchning, utan laserdata, simulerat | 0,21–0,31 |
| Vårt virke med eget lager | Egna skördardata, simulerat | 0,03–0,05 |
| Vår månadsmatris | Per destination och sortiment | 0,06–0,09 |

**Det stämmer överens:**

- Felet för virke utan skördardata ligger i närheten av forskningens men över det bästa, vilket är väntat. De har
  laserdata från just det aktuella beståndet.
- Forskningen har funnit att hela uppmätta fördelningar från närmaste grannar slår parametriska Weibull-fördelningar
  (Packalén och Maltamo 2008). Samma sak såg vi: donatorer gav bättre intervall än oberoende klasser.
- Malinen och Maltamo fann skördardata lämpligare som referens än inventeringsdata, i linje med att skördardata räcker
  för att bära hela metoden.
- Skördaren mäter ungefär lika bra som mätramar (Skogforsk 2021), så mätfelet är inte det stora problemet.

**Skillnader som gör jämförelsen osäker:** studierna mäter stamfrekvenser per bestånd i en variant av Reynolds index,
och formeln i Noordermeer m.fl. kunde jag inte läsa. Vi mäter volym per arbetsorder. Alla våra tal är simulerade,
medan deras är verkliga. Jämförelsen visar storleksordning, inte att vi är bättre eller sämre.

## Kvarstående svagheter

- **Värdeintervallet är något smalt när mycket virke saknar skördardata.** Månadens värde låg inom 90 %-intervallet i
  87–93 % av fallen, lägst med 30 % utan skördardata. Det som återstår är enstaka stora missar när mer levererats än
  skördardatan visar: den del av beståndet som inte rapporterats kan vara helt olik resten. Per cell är intervallen i
  stället något breda, 94–98 %.
- **Inget verkligt facit.** Eftersom dimensioner saknas vid leverans går metoden inte att validera direkt i drift.
- **Simulatorn är antaganden.** Andel virke utan skördardata, andel omdirigerat virke, hur starkt destination styr
  dimensionerna och skillnader inom arbetsordrar är påhittade. Den ordning metoderna hamnar i är mer pålitlig än de
  exakta talen.
- **Det mesta av kvarvarande fel går inte att ta bort.** Utan skördardata eller stockantal finns inget som skiljer en
  arbetsorder från dess liknande grannar, och vid månadsskiften finns inget som säger vilket avlägg som kördes först.

## Källor

- [Noordermeer, Ørka och Gobakken 2023, Silva Fennica](https://silvafennica.fi/article/23023)
- [Maltamo m.fl. 2019, Silva Fennica](https://www.silvafennica.fi/article/10075)
- [Malinen och Maltamo, International Journal of Forest Engineering](https://journals.lib.unb.ca/index.php/IJFE/article/download/30024/1882525273?inline=1)
- [Packalén och Maltamo 2008, Canadian Journal of Forest Research](https://next.sciencegate.app/document/10.1139/x08-037)
- [Holappa Jonsson 2018, SLU, om hprImputation](https://stud.epsilon.slu.se/13767/)
- [Skogforsk, Arbetsrapport 981-2018](https://www.skogforsk.se/cd_20190114162446/contentassets/4a34a91c429f46b09a9f3abc5fcbc242/arbetsrapport-981-2018.pdf)
- [Skogforsk, Arbetsrapport 1093-2021](https://www.skogforsk.se/contentassets/7e7c5a97ae7b4e06b22eb755523e529c/arbetsrapport-1093-2021.pdf)
- [Dasymetrisk kartering, GIS&T Body of Knowledge](https://gistbok-ltb.ucgis.org/current/tag/show/30571)
- [Residence time distribution för spårning, PubMed](https://www.pubmed.gov/34822965/)
