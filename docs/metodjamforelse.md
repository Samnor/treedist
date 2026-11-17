# Jämförelse av metoder

Uppgiften: skatta en matris över diameter och längd per destination och handelssortiment för en månads leveranser. Vid
leverans finns bara inmätt brutto- och nettovolym per arbetsorder eller lastbil. Skördardatan ger stockar, diameter och
längd. Varje arbetsorder har en planerad destination, och skörd och leverans är var sin kampanj om 1–3 veckor. På sommaren
börjar leveranserna medan skördaren är kvar, se [antaganden](antaganden.md).

**Slutsats: metod A, lagerliggaren, är standard i `treedist`.** Den ger lägst fel i båda scenarierna. I basscenariot är
prisfelet 4,3 kr/m3fub mot 40,5 om man bara använder månadens skörd. Det förutsätter att varje lass har egen
skördardata, se [antaganden](antaganden.md).

## Metoderna

**A. Lagerliggare.** Massbalans per arbetsorder och sortiment: skördat virke läggs i lager, leverans dras ur lagret och
fördelas som lagret (S1). Levereras mer än lagret rymmer fördelas resten som arbetsorderns hela skördehistorik (S2), en
uppskattning som står kvar på bilagan. Ett lass utan egen skördardata stoppar månaden, se [antaganden](antaganden.md).

**B. Faltning på sortimentsnivå.** Ingen koppling till enskilda arbetsordrar. Skörden per planerad destination viktas med
hur stor andel som enligt en lagringstidsfördelning levererades just den månaden. Finns bara i jämförelseskriptet.

En tredje metod, C, lät virke utan skördardata låna fördelning från andra arbetsordrar. Den togs bort 2026-11-09, när
varje lass antogs ha egen skördardata. Den finns kvar i historiken under [Experiment](#experiment).

## Resultat

Medelvärden från 8 simuleringar om 12 månader, med 3 destinationer. Felindex är andelen volym i fel cell per månad,
destination och sortiment. Kumulativt är samma mått över hela perioden. Skriptet
[compare_methods.py](../scripts/compare_methods.py) återskapar [resultaten](metodjamforelse_resultat.csv).

| Scenario | Metod | Felindex | Prisfel, kr/m3fub | Kumulativt prisfel | Värdetäckning | Celltäckning |
|---|---|---|---|---|---|---|
| Bas | Naiv (månadens skörd) | 18,0 % | 40,5 | – | – | – |
| | B Faltning | 11,9 % | 24,2 | – | – | – |
| | **A Liggare** | **5,8 %** | **4,3** | **1,0** | 93 % | 98 % |
| Stora skillnader inom arbetsorder | Naiv | 22,5 % | 48,6 | – | – | – |
| | B Faltning | 15,6 % | 33,9 | – | – | – |
| | **A Liggare** | **7,5 %** | **6,8** | **2,1** | 86 % | 96 % |

Värdetäckning är hur ofta månadens värde låg inom 90 %-intervallet, och celltäckning motsvarande per cell. Fröna är
81–88, samma som i slutkontrollen av den tidigare metoden. Talen är mätta 2026-11-10, med S1 och S2 som enda källor och
en simulator där varje lass har egen skördardata. De går inte att jämföra med äldre tal i [Experiment](#experiment), där
en del av virket saknade skördardata.

Simulatorn ger sedan 2026-11-10 diameterklasser om 1 cm, förut 2 cm. Prisfelet är detsamma, eftersom prislistans
gränser ligger kvar. Felindexet är högre, 5,8 % mot 4,0 % för liggaren i basscenariot, eftersom cellerna är hälften så
breda och samma fel i diameter då flyttar mer volym över en gräns. Felindex mätta före den dagen, som i
[Experiment](#experiment), gäller klasser om 2 cm.

Bas-scenariot har sen rapport av skördens senare halva för 10 % av arbetsordrarna, 5 % omdirigerat virke, och cirka
44 % av arbetsordrarna levererar i mer än en månad. 98 % av volymen fördelas ur eget lager (S1), 97 % med stora
skillnader inom arbetsorder. Felindexet per arbetsorder är 0,05 med eget lager, och 0,06 med stora skillnader inom
arbetsorder.

**Felet är i hög grad ett månadsskiftesfel.** Över tolv månader är prisfelet bara 1,0 kr/m3fub mot 4,3 per månad, eftersom
en arbetsorder som delas över ett skifte blir nära rätt i summan.

De sparade modellerna i `modeller/` är utvärderade igen 2026-11-10 med [modell.py](../scripts/modell.py), på
klättringens fem scenarier. Standardmodellen har 15 delar. Prestanda är andelen av standardmodellens förbättring mot
den naiva skattningen, som har prisfelet 41,5 kr/m3fub på utvecklingsfröna. Värdetäckning är hur ofta det sanna värdet
faller inom 90 %-intervallet.

| Modell | Delar | Prisfel | Prestanda | Sämsta scenario | Värdetäckning | Kontrollfrön: prisfel, prestanda |
|---|---|---|---|---|---|---|
| `standard-2026-11-09` | 15 | 4,2 | 100 % | | 94 % | 4,0 |
| `halv` | 6 | 9,1 | 87 % | 31 %, delade arbetsordrar | 90 % | 8,9 och 87 % |
| `halv-volym` | 5 | 9,1 | 87 % | 31 %, delade arbetsordrar | 90 % | 8,9 och 87 % |
| `enkel` | 2 | 10,6 | 83 % | 29 %, delade arbetsordrar | inga intervall | 10,2 och 84 % |

De enkla modellerna behåller 93–100 % av förbättringen i fyra av scenarierna men bara omkring 30 % med delade
arbetsordrar. De drar inte först det virke som kapades för lassets sågverk, och en arbetsorder som levererar till
flera sågverk får då samma fördelning till alla. De äldre talen för samma modeller under [Experiment](#experiment),
92 % och 99 %, mättes innan det scenariot fanns.

## Experiment

**Läs det här avsnittet som historik.** S3 och S4 togs bort 2026-11-09: varje lass måste nu ha egen skördardata, se
[antaganden.md](antaganden.md), och simulatorn ger inte längre virke utan skördardata. Rader och stycken som nämner S3,
S4, givare, vikter för destination, grupp eller syskonsortiment eller scenariot "30 % utan skördardata" beskriver en
metod och en simulator som inte finns längre. Talen står kvar som de mättes då, också
antalet delar och prestandan för de sparade modellerna. Dagens tal står under [Resultat](#resultat) och i
[stresstestet](#stresstest-när-verkligheten-skiljer-sig-från-simulatorn).

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
| Klättring 2026-11-08: lager per mottagningsplats som virket kapades för (VIOL 3) | Poäng −6,55 ± 2,46. Prisfel −19,1 i det nya scenariot där hälften av arbetsordrarna delas efter toppdiameter mellan klen- och grovsåg, oförändrat i övriga | Behållen. Vinner bara där samma handelssortiment går till flera sågverk, vilket simulatorn själv skapar; hur vanligt det är i verkligheten är okänt |
| Klättring: virke utan skördardata lånar per mottagningsplats, givare delade efter mottagningsplatsen virket kapades för | Poäng −0,32 ± 0,15. Prisfel −2,4 med delade arbetsordrar, men +0,24 med 30 % utan skördardata | Behållen, men backad efter kontrollen: på kontrollfröna +0,14 ± 0,10, prisfel +0,77 med 30 % utan skördardata och −1,2 med delade arbetsordrar. Kostnaden kommer troligen av att vikten följer lassets faktiska mottagningsplats i stället för den planerade |
| Klättring: planerad destination i givarvikten när arbetsordern bara levererar till ett sågverk under månaden, ovanpå föregående steg | Poäng −0,05 ± 0,08. Prisfel −0,24 med 30 % utan skördardata, +0,08 i bas | Förkastad. Tar tillbaka föregående stegs kostnad, men inte mer än bruset |
| Klättring: lager per startplats (avlägg), när inmätningen anger startplatsen och skördarens stammar knutits till närmaste avlägg | Poäng −0,11 ± 0,05, prisfel −0,72 i det nya scenariot med kända avlägg, där 10 % av stockarna hamnar på fel avlägg; oförändrat i övriga | Behållen. Kopplingen mellan stamkoordinat och avlägg är ett antagande |
| Klättring: lån per mottagningsplats bara när arbetsordern levererar till flera under månaden, annars efter planerad destination (de två stegen ovan i ett) | Poäng −0,30 ± 0,13, prisfel −2,5 med delade arbetsordrar, oförändrat i övriga | Behållen, men backad efter kontrollen: −0,055 ± 0,041 på kontrollfröna, prisfel −1,1 med delade arbetsordrar och oförändrat i övriga. Kvar bakom `pool_per_destination` |
| Klättring: överleverans per mottagningsplats, var och en med det den saknar och historiken för virket som kapades för den | Poäng −0,055 ± 0,030, prisfel −0,21 med delade arbetsordrar | Förkastad, under två medelfel. Rätt i princip men liten |
| Klättring: givare väger lika i stället för efter volym | Poäng +0,54 ± 0,30, sämst när destinationen är oberoende av grovlek (+1,2) | Förkastad. Volymvikten följer att det levererade virket också vägs efter volym |
| Förenkling med sex scenarier: utan gruppvikt, utan syskonsortiment, utan AO-historik (S2) | +0,21 ± 0,15, +0,36 ± 0,14 och +0,15 ± 0,12. Gruppvikten kostar 0,7–0,9 med 30 % utan skördardata och oberoende destination, historiken 0,57 med kända avlägg | Inget borttaget. Gruppen och arbetsorderns historik väntas betyda mer i verklig data än i simulatorn |
| Klättring: osäkerheten för en del dragen per mottagningsplats vilar på virket som kapades för den | Poäng −0,04 ± 0,04, bara värdetäckningen ändras | Förkastad |
| Parameterklättring efter stegen med mottagningsplats och startplats, 30 kandidater | Inget steg slog bruset; närmast `donor_group_weight` 8 (−0,12 ± 0,11) och `design_effect` 163 (−0,11 ± 0,12) | Parametrarna ligger kvar i ett lokalt optimum |
| Klättring: överleverans får fördelningen hos månadens lass i stället för hela historiken | Poäng −0,06 ± 0,05, prisfel oförändrat | Förkastad |
| Klättring: en arbetsorder som levererat till flera sågverk tidigare räknas som delad även en månad med ett | Poäng −0,016 ± 0,014, prisfel −0,2 med delade arbetsordrar | Förkastad |
| Klättring: pro rata i stället för äldsta först inom ett känt avlägg | Poäng +0,01 ± 0,03, prisfel +0,12 med kända avlägg | Förkastad. Ordningen inom ett avlägg spelar liten roll |
| Klättring: vikten 64 i stället för 16 för givarvirke kapat för samma sågverk när en delad arbetsorder lånar | Poäng −0,015 ± 0,022 | Förkastad |
| 2026-11-09: ett lass som vänds en senare månad krediteras med sin månads fakturerade fördelning, hittad med leverans-id (VIOL 3:s leveransnummer) | Inte mätt: simulatorn vänder inga lass och poängen räknar inga krediteringar. Testat att krediteringen vänder exakt det lassets månad fakturerades | Infört (`credit_per_load`). Bokföring, inte en skattning: målet är att faktura och kreditering tar ut varandra |
| 2026-11-09: S3 och S4 borttagna. Källorna är eget lager (S1) och arbetsorderns hela skördehistorik (S2), och ett lass utan egen skördardata stoppar månaden. Simulatorn ger inte längre virke utan skördardata, och scenariot "30 % utan skördardata" är borttaget | Går inte att jämföra med raderna ovan, eftersom simulatorn nu uppfyller antagandena: prisfel 4,2 och värdetäckning 94 % på utvecklingsfröna, 4,0 och 93 % på kontrollfröna. Standardmodellen har 15 delar mot 23 | Infört. Parametrarna för givare finns inte kvar |
| 2026-11-09: uppskattningen (S2) står alltid kvar på bilagan, och inget ändras på en senare faktura | Inte mätt: ett avtalsval, inte en skattning. Hur uppskattningen skilde sig från skördardata som kom senare räknas fortfarande, för uppföljning | Infört |
| Klättring 2026-11-11: ett lass tar bara virke som är fällt senast dess leveransdag, och det som inte fanns då blir volym utöver lagret (S2) medan det senare virket ligger kvar i lagret | Poäng −0,07 ± 0,05, under två medelfel. Prisfelet är oförändrat i alla fem scenarier, och i demons fyra månader har varje sågverk samma S1 och S2 med och utan spärren | Förkastad. Simulatorn kör bara virke som redan är fällt, och med äldsta virket först tar månadens lass ändå det som fanns först, så simulatorn kan knappt pröva spärren. I verklig data slår den till när datum eller skördardata brister, och `check` varnar redan när mer än 5 % av volymen levererades före arbetsorderns första avverkningsdag |
| Dagmetoden 2026-11-11, som alternativ modell (`draw_per_day`, `--modell dag`): dag för dag tar lassen bara virke fällt senast sin leveransdag, och det som inte ryms blir S2. Dagar med samma fällda virke dras ihop, och underskott räknas av mot virke fällt senast sin månad | Första versionen: poäng −0,002 ± 0,04, prisfel 4,24. Förbättrad: poäng +0,009 ± 0,03, prisfel 4,22 mot 4,23 | Inte standard, men sparad som modellen `dag`. Lika bra i simulatorn, som inte kan pröva skillnaden: den kör bara virke som redan är fällt |
| VIOL 3, 2026-11-17: lasset tar ur lagret för den mottagningsplats det producerades för (`producerat_for_mottagningsplats` på leveransen), inte den det mättes in vid | Poäng +0,013 ± 0,022, prisfel oförändrat. Simulatorn mäter nästan alltid in virket där det producerades för | Infört som del av kontraktet: VIOL 3 har uppgiften på varje leverans |
| Förenkling 2026-11-17: ett lass tar aldrig ur en annan mottagningsplats lager; det som det egna inte räcker till blir S2. Avläggen inom ett lager delar fortfarande | Utveckling +0,009 ± 0,078, kontroll +0,016 ± 0,050; prisfelet −0,02 i båda, −0,09 med delade avtalsobjekt | Infört, koden och reglerna för det gemensamma lagret borttagna |
| Förenkling 2026-11-17: dessutom utan lager per avlägg | +0,119 ± 0,100, prisfel +1,0 med kända avlägg | Inte infört: avlägget ur stamkoordinaterna gör nytta när det finns |
| Klättring 2026-11-18: volym utöver lagret fördelas som skörden hittills för den mottagningsplats lasset producerades för, när avtalsobjektet har sådan skörd, i stället för som hela avtalsobjektets skörd. Prövad igen eftersom ett lass sedan 2026-11-17 aldrig tar ur en annan mottagningsplats lager, så att mer volym blir uppskattning i delade avtalsobjekt | Poäng −0,018 ± 0,028. Prisfel −0,34 med delade arbetsordrar, mot −0,21 förra gången, och oförändrat i de fyra övriga scenarierna; i snitt 4,21 → 4,14. Värdetäckningen går från 93,7 till 93,9 %, längre från 90 %, och tar ut det mesta av vinsten i poängen | Förkastad enligt regeln, under två medelfel. Fortfarande rätt i princip och utan kostnad i prisfel; vinsten finns bara där simulatorn själv delar ett sortiment mellan sågverk, och hur vanligt det är i verkligheten är inte mätt |

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
avräkning, omklassning, flera destinationer och avskrivning. Prestanda är hur stor del av avståndet till den naiva
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
  mycket som levereras utöver lagret, inte fördelningen.
- **Äldsta först** är den enda utelämnade del som är värd sitt pris om en femte del tillåts: prisfelet går från 13,5 till
  12,0 kr/m3fub. Den betyder mest på sommaren, när leveranserna börjar under skörden.

Allt är prövat mot simulatorn. Att destinationen säger så mycket om grovleken bygger på hur simulatorn kopplar
sågverk och dimension; i scenariot där destinationen är oberoende av grovlek ger `enkel` ändå 91 %.
Flödesrapporten för enkel visar demots månader med modellen. Skapa den med `uv run python scripts/flodesrapport.py --config modeller/enkel.toml --out out/flodesrapport_enkel.html`.

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

Flödesrapporten för halv visar demots månader med modellen. Skapa den med `uv run python scripts/flodesrapport.py --config modeller/halv.toml --out out/flodesrapport_halv.html`.

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

Flödesrapporten för halv-volym visar demots månader med modellen. Skapa den med `uv run python scripts/flodesrapport.py --config modeller/halv-volym.toml --out out/flodesrapport_halv-volym.html`.

### Stresstest: när verkligheten skiljer sig från simulatorn

Kontrollfröna är nya dragningar ur samma simulator. En del som förenklingen tog bort kan ha sett onyttig ut bara för
att simulatorn aldrig gav den något att göra. `scripts/stresstest.py` vrider upp en sak i taget som verkligheten kan ha
mer av, och kör de sparade modellerna på samma simuleringar, med frön 501–506 som inget beslut har använt.
Prestanda är andelen av standardmodellens förbättring mot den naiva skattningen i samma scenario.

| Scenario | Prisfel standard | `halv-volym` mot standard | Prestanda `halv-volym` | `enkel` | Täckning standard | Täckning `halv-volym` |
|---|---|---|---|---|---|---|
| bas | 4,47 | +0,05 ± 0,02 | 100 % | 98 % | 92 % | 99 % |
| skördaren mäter 5 % för mycket | 4,55 | +0,09 ± 0,01 | 100 % | 98 % | 95 % | 99 % |
| 5 % spill vid hantering | 4,61 | +0,09 ± 0,02 | 100 % | 98 % | 95 % | 99 % |
| 10 % skillnad brutto–netto | 4,50 | **+0,41 ± 0,08** | 99 % | 98 % | 92 % | 99 % |
| lång eftersläpning | 4,84 | +0,01 ± 0,02 | 100 % | 99 % | 91 % | 99 % |
| 40 % rapporteras sent | 5,59 | +0,02 ± 0,01 | 100 % | 99 % | 91 % | 99 % |
| 25 % omdirigeras | 4,41 | +0,07 ± 0,03 | 100 % | 98 % | 94 % | 99 % |
| mest travmätning | 4,47 | +0,06 ± 0,02 | 100 % | 98 % | 94 % | 99 % |
| klumpiga avlägg | 6,81 | **+0,40 ± 0,06** | 99 % | **87 %** | **87 %** | 99 % |
| små arbetsordrar | 2,77 | +0,03 ± 0,02 | 100 % | 98 % | 99 % | 100 % |
| stora diameterfel | 8,02 | +0,01 ± 0,04 | 100 % | 98 % | **77 %** | 99 % |

Talen är mätta 2026-11-10 med `standard-2026-11-09` som referens. `halv` ger samma prisfel som `halv-volym` i varje
scenario.

- **`halv-volym` behåller minst 99 % av förbättringen i varje scenario här.** Gapet mot standard syns bara när brutto
  och netto skiljer 10 % (+0,4), där bruttovolymen ur lagret får något att göra, och med klumpiga avlägg (+0,4).
- **Testet har inget scenario med delade arbetsordrar.** Det är där de enkla modellerna tappar mest, omkring 70 % av
  förbättringen, se tabellen över de sparade modellerna under [Resultat](#resultat).
- **Kalibreringen betyder nästan inget för prisfelet**, inte ens när skördaren mäter 5 % fel eller 5 % spills (+0,1).
  Liggaren skalar om till inmätt volym, så ett jämnt volymfel ändrar inte fördelningen. Att ta bort
  `harvester_bias` och `handling_loss` är alltså robust här.
- **Sen rapportering kostar lika mycket i alla modeller.** När 40 % rapporteras sent stiger standardmodellens prisfel
  från 4,5 till 5,6, och de enkla modellerna följer med (+0,02). Alla fördelar det som inte ryms i lagret som
  arbetsorderns hela skördehistorik.
- **Standardmodellens intervall är för smala när verkligheten avviker**: täckningen faller till 77 % med stora
  diameterfel och 87 % med klumpiga avlägg. Intervallen i `halv-volym` är i stället för breda, 99–100 % i varje
  scenario.
- **`enkel` faller till 87 %** med klumpiga avlägg (+4,1 ± 1,2). Den saknar äldsta först, som är det som följer
  avläggen när de körs ut ett i taget.
- **Testet kan inte vrida på** fler sortiment, säsongsskillnader i grovlek eller arbetsorder-id som inte stämmer
  mellan källorna. Simulatorn har inga parametrar för dem.

```bash
uv run python scripts/stresstest.py
```

## För- och nackdelar

| | Fördelar | Nackdelar |
|---|---|---|
| **A Liggare** | Volymen stämmer per arbetsorder. Fördelningen blir nära rätt i summan över arbetsorderns månader. Bara antaganden som går att förklara. Ger säkerhetsklass per volym. | Kräver liggare över månader och en körning i taget. Kräver att varje lass har egen skördardata, annars stoppar månaden. Kräver att arbetsordernumret stämmer mellan systemen. |
| **B Faltning** | Enkel, kräver ingen liggare och ingen koppling till arbetsorder. Bra rimlighetskontroll. Fungerar om kopplingen saknas helt. | Fem till sex gånger så stort prisfel som A. Bygger på en antagen lagringstid. Kan inte se omdirigerat virke på arbetsordernivå. Ger ingen säkerhetsklass. |

## Vad heter uppgiften?

Jag hittade inget etablerat namn på hela problemet, och ingen studie som gör exakt detta. Delarna har däremot namn:

| Del av uppgiften | Akademiskt begrepp | Fält |
|---|---|---|
| Sprida känd total över fina klasser med hjälp av en annan datakälla | **Disaggregering**, även nedskalning. Dasymetrisk kartering är geografins version av samma idé. | Statistik, geografi |
| Följa material genom lager och blandning | **Massbalans**, *residence time distribution*, *lot genealogy* | Processindustri |
| Förlorad koppling mellan stock och mätvärde | **Spårbarhet**, *forest-to-mill traceability* | Skoglig logistik |

Närmast är därför *disaggregering med skördardata som hjälpvariabel, med massbalans över lager*. Ekologisk inferens och
statistisk matchning är besläktade men passar sämre: den första skattar samband ur enbart aggregat, och den andra länkar
två datakällor utan att fördela en känd total.

Skogforsk är närmast i praktiken. Verktyget *hprImputation* använder kMSN på lagrade skördardata, men för att prognostisera
utfall i planerade bestånd före avverkning, inte för att fördela levererad volym.

## Liknar våra resultat andras?

Ja i riktning, men siffrorna går bara delvis att jämföra.

| Studie | Uppgift | Fel |
|---|---|---|
| Noordermeer m.fl. 2023 | k-NN med laserdata och skördardata som referens, 49 bestånd | 0,13 för diameter, 0,10 för sågad volym |
| Maltamo m.fl. 2019 | Samma ansats, 47 bestånd | Under 0,2 |
| Vårt virke med eget lager | Egna skördardata, simulerat | 0,05–0,06 med klasser om 1 cm, 0,03–0,05 med 2 cm |
| Vår månadsmatris | Per destination och sortiment | 0,06–0,08 med klasser om 1 cm, 0,04–0,06 med 2 cm |

**Det stämmer överens:**

- Vårt fel är lägre än forskningens, vilket är väntat. Studierna skattar fördelningen för bestånd utan egna
  mätningar, medan varje arbetsorder här har egen skördardata.
- Malinen och Maltamo fann skördardata lämpligare som referens än inventeringsdata, i linje med att skördardata räcker
  för att bära hela metoden.
- Skördaren mäter ungefär lika bra som mätramar (Skogforsk 2021), så mätfelet är inte det stora problemet.

**Skillnader som gör jämförelsen osäker:** studierna mäter stamfrekvenser per bestånd i en variant av Reynolds index,
och formeln i Noordermeer m.fl. kunde jag inte läsa. Vi mäter volym per arbetsorder. Felindexet beror också på hur
breda klasserna är, se [Resultat](#resultat). Alla våra tal är simulerade,
medan deras är verkliga. Jämförelsen visar storleksordning, inte att vi är bättre eller sämre.

## Kvarstående svagheter

- **Antagandena måste hålla.** Metoden har inget att falla tillbaka på: ett lass utan egen skördardata stoppar månaden,
  se [antaganden](antaganden.md). Hur ofta det händer i verklig data är inte mätt.
- **Värdeintervallet är för smalt när avläggen skiljer sig mycket.** Månadens värde låg inom 90 %-intervallet i 93 % av
  fallen i basscenariot, men i 86 % med stora skillnader inom arbetsorder. Per cell är intervallen i stället något
  breda, 96–98 %.
- **Inget verkligt facit.** Eftersom dimensioner saknas vid leverans går metoden inte att validera direkt i drift.
- **Simulatorn är antaganden.** Andel sent rapporterad skörd, andel omdirigerat virke, hur starkt destination styr
  dimensionerna och skillnader inom arbetsordrar är påhittade. Den ordning metoderna hamnar i är mer pålitlig än de
  exakta talen.
- **Det mesta av kvarvarande fel går inte att ta bort.** Utan stockantal eller dimensioner vid leverans finns inget som
  säger vilka stockar som åkte, och vid månadsskiften finns inget som säger vilket avlägg som kördes först.

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
