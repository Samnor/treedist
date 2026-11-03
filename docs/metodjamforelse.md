# Jämförelse av metoder

Uppgiften: skatta en matris över diameter och längd per destination och handelssortiment för en månads leveranser. Vid
leverans finns bara inmätt brutto- och nettovolym per arbetsorder eller lastbil. Skördarmätningen ger stockar, diameter
och längd. Varje arbetsorder har en planerad destination, och skörd och leverans är var sin kampanj om 1–3 veckor.

**Slutsats: metod C, lagerliggare med mjuk matchning, är standard i `treedist`.** Den ger lägst fel i alla scenarier. I
basscenariot är prisfelet 10,0 kr/m3fub mot 52,3 om man bara använder månadens skörd.

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
| Bas | Naiv (månadens skörd) | 21,9 % | 52,3 | – | – | – |
| | B Faltning | 11,7 % | 27,3 | – | – | – |
| | A Liggare | 7,6 % | 14,7 | 8,5 | 87 % | 94 % |
| | **C Mjuk matchning** | **6,3 %** | **10,0** | **3,8** | 88 % | 94 % |
| 30 % utan skördardata | Naiv | 23,7 % | 57,2 | – | – | – |
| | B Faltning | 13,3 % | 31,6 | – | – | – |
| | A Liggare | 11,9 % | 28,2 | 21,7 | 81 % | 89 % |
| | **C Mjuk matchning** | **8,5 %** | **16,2** | **7,4** | 84 % | 90 % |
| Stora skillnader inom arbetsorder | Naiv | 28,0 % | 68,3 | – | – | – |
| | B Faltning | 13,9 % | 30,2 | – | – | – |
| | A Liggare | 8,3 % | 13,0 | 5,8 | 87 % | 93 % |
| | **C Mjuk matchning** | **8,1 %** | **12,1** | **5,1** | 83 % | 91 % |

Värdetäckning är hur ofta månadens värde låg inom 90 %-intervallet, och celltäckning motsvarande per cell.

Bas-scenariot har 10 % virke helt utan skördardata, 10 % sen rapport, 5 % omdirigerat virke, och cirka 39 % av
arbetsordrarna korsar ett månadsskifte. Med eget lager är felindexet per arbetsorder 0,04, utan skördardata 0,21.

**Felet är i hög grad ett månadsskiftesfel.** Över tolv månader är prisfelet bara 3,8 kr/m3fub mot 10,0 per månad, eftersom
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
| Stockantal per leverans | 7,7 → 2,1 i tidigare simulering | Uppgiften finns inte |

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
| Vårt virke med eget lager | Egna skördardata, simulerat | 0,04–0,06 |
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

- **Värdeintervallet är något smalt.** Månadens värde låg inom 90 %-intervallet i 83–88 % av fallen.
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
