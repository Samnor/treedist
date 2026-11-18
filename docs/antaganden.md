# Är antagandena rimliga?

Granskning av vad simulatorn och metoden antar om vägen från skördare till sågverk. Bedömningen bygger på
[exempelresorna](exempelresor.md), mätningar på det simulerade flödet och publicerade källor. Där en källa saknas står
det. **Härlett** betyder egen beräkning ur källor.

**Sammanfattning.** Granskningen hittade två antaganden som inte höll: lagringstiden var för lång, och sommaravverkat
timmer låg lika länge som vinteravverkat trots att köparna kräver leverans inom två veckor. Simulatorn är rättad och följer nu
säsongen. De övriga antagandena är rimliga eller går inte att pröva utan egna data. Känslighetsproven visar att metoden
har lägst fel i alla sju varianter, med prisfel 3,0–4,9 kr/m3fub mot 26–49 om man bara använder månadens skörd. Det
som mest påverkar resultatet i verkligheten är om varje lass har skördardata när månaden körs, och i vilken ordning
avläggen körs.

## Vad exempelresorna visar

Fyra avtalsobjekt ur samma simulering, en av varje slag:

| Resa | Felindex diameter | Vad den visar |
|---|---|---|
| En leveransmånad | 0,04 | Fälld 3–15 maj, levererad 9–26 maj från fyra avlägg, 6–11 dagar på avlägg. 99 % ur eget lager |
| Över ett månadsskifte | 0,05 och 0,07 | Ett avlägg, fällt 26 oktober–16 november och kört 20 november–9 december |
| Sen skördarrapport | 0,05 och 0,07 | Fälld i mars, senare halvan rapporterad i april, väntade till efter tjällossningen, 46 dagar på avlägg |
| Omdirigerad | 0,02 | Fel sågverk planerat, men mottagningsplatsen ger rätt destination |

Resan över månadsskiftet visar var felet uppstår. Metoden vet hur mycket som kördes varje månad men inte vilka stockar.
November skattades till 27,8 cm mot verkliga 27,5, och december till 27,8 mot 27,8. Över hela avtalsobjektet blir det
nära rätt (0,03), men den enskilda månaden blir något fel. Har avtalsobjektet flera avlägg skulle uppgift om vilket
avlägg ett lass kom från minska felet; se sista avsnittet.

I resan med sen skördarrapport fördelades 3 % av majs volym som avtalsobjektets hela skörd (S2), en uppskattning:
inmätningen gav något mer än lagret rymde efter kalibrering.

## Simulatorns antaganden

| Antagande | Simulatorn | Verkligheten | Bedömning |
|---|---|---|---|
| Tid från fällning till leverans | Median 18 dagar, medel 18–21 | Sågtimmerlagret i landet är 2,6–3,5 miljoner m3fub, mot knappt 34 miljoner m3fub avverkat per år: 28–37 dagar från fällning till förbrukning (härlett). 4–6 % av årsavverkningen ligger vid industrin, alltså 15–22 dagar där. Kvar blir cirka 6–22 dagar i skog, vid väg och på terminal | Rimligt efter rättningen. Var 31 dagar. Statistiken täcker bara de största aktörerna, så den verkliga tiden är troligen något längre än beräkningen |
| Sommaravverkat timmer | Median 12 dagar, 72 % inom 14 dagar. På sommaren börjar 90 % av avtalsobjekten leverera medan skörden pågår | Holmen: timmer fällt 1/6–31/8 ska vara vid sågverket inom två veckor. Mellanskog och Sveaskog: anmält vid väg inom två veckor. Blånad ger avdrag och kan stoppa partier | Rimligt efter rättningen. Var 30 dagar och inget inom 14 |
| Vinteravverkat timmer | Median 24 dagar | Vinterfällt får ligga till 15 april (Mellanskog) eller 15 juni (Holmen) | Rimligt. Väntan genom tjällossningen syns i exemplet ovan |
| Skörd sedan leverans, 1–3 veckor var | Skördetid median 15 dagar, kampanj 15 dagar. Vintertid separata perioder, sommartid överlappande | Projektets egen beskrivning, och köparnas regler för sommaravverkat timmer | Rimligt |
| Storlek per avtalsobjekt | Median 721 m3fub sågtimmer per sortiment vid slutavverkning, 188 vid gallring | Medelanmälan för föryngringsavverkning var 3,8 ha 2021, knappt 5 ha för andra ägare än enskilda. Med antagna 250 m3sk/ha och knappt hälften sågtimmer blir det 350–500 m3fub sågtimmer per trakt (härlett, volym per hektar antagen) | **Troligen för stora**, kanske upp till dubbelt. Ett bolags avtalsobjekt kan dock omfatta flera anmälningar. Prövat nedan |
| Lass | Median 44,5 m3fub | 64 ton totalvikt ger cirka 45 m3fub (härlett), 74-tonsbilar mer | Rimligt |
| Andel stockmätt | 90 % | En stor majoritet av sågtimret stockmäts (Skogforsk) | Rimligt, exakt andel okänd |
| Vrak | 0–2 %, i snitt 1 % | Ingen läsbar källa hittad; ett Biometriadokument som ska ange cirka en procent gav 404 | Antagande |
| Svinn mellan skördare och mätning | 1 % ± 1,5 % | Ett exempel i Biometrias material räknar med 1 % | Rimligt som nivå, spridningen antagen |
| Skördarens mätfel | 0,9 % över i volym, 3 mm brus och 2 mm systematiskt per maskin i diameter | Biometria 2025: 0,9 % under bark. Spridning 2,4–9,6 mm i toppdiameter mellan mätramar | Rimligt för volymen. Det systematiska felet i diameter är troligen för litet, se nedan |
| Utan skördardata | Finns inte: varje lass har skördardata, som metoden antar. Var 10 % före 2026-11-09 | Sveaskog: 13 % köpt från privata ägare och 3 % import. Om köpt virke har skördardata framgår inte | Okänt, **viktigast att ta reda på**: ett lass utan skördardata stoppar månaden |
| Sen rapport | För 10 % av avtalsobjekten kommer skördarfilerna för den senare halvan av skörden en månad sent. Den första halvan kommer alltid i tid, så lassen har skördardata och den sena halvan levereras utöver lagret | hpr-filer kan skickas delavslutade under avverkningen (Biometria) | Troligen försiktigt antaget |
| Destination | Planeras efter grovlek, 5 % omdirigeras | Sågverk är inriktade på dimensioner, men styrkan är okänd | Antagande, prövat nedan |
| Skillnader inom bestånd | Varje avlägg har egen grovlek, standardavvikelse 10 % | Ingen källa | Antagande, prövat med 20 % i metodjämförelsen |
| Ordning mellan avlägg | I fällningsordning när leveransen överlappar skörden, annars slumpad | Ingen källa | Antagande. Avgör hur stort månadsskiftesfelet blir |

Ej med i simulatorn: massaved, kvalitetsklasser, samlast, terminaler, stormvirke och omklassning vid inmätning.

## Metodens antaganden

| Antagande | Bedömning |
|---|---|
| Skördarens fördelning beskriver det som levereras, efter 0,9 % kalibrering och 1 % svinn | Rimligt för volymen. Klasserna är skördarens, inte mätramens, se nedan |
| Inmätningens volym är exakt på fakturan | Rimligt, den är avtalsmässigt det som betalas |
| Ett lass drar pro rata ur avtalsobjektets lager, eller äldsta virket först när leveransen börjar innan skörden är klar | Rimligt utan uppgift om avlägg. Ger felet vid månadsskiftet ovan |
| Vrak, avdrag och nedklassning har samma fördelning som resten av lasset | Troligen fel i riktning, liten i volym, se nedan |
| Varje lass har skördardata för sitt avtalsobjekt och sitt sortiment när månaden körs | Sex antaganden, se nedan. Brister ett stoppar månaden |
| Volym utöver lagret fördelar sig som avtalsobjektets hela skörd | Rimligt när resten av skörden liknar det som rapporterats. Står i bilagan som en uppskattning |
| När ett avtalsobjekt levererar utöver lagret syns halva skörden ännu inte i skördardatan | Antagande. Påverkar bara utvärderingens intervall |
| Ett lass faktureras den månad det mäts in enligt matdatum, eller med leveransdatum när källan saknar matdatum. Ordningen ur lagret följer leveransdatum | Rimligt. Mätningen sker samma dag som transporten eller senare |

### Antaganden som gör S1 och S2 tillräckliga

Beslutat 2026-11-09: följande sex antaganden antas sanna. Då har varje lass som faktureras skördardata för samma
avtalsobjekt och samma inmätta sortiment när månaden körs, och all volym får sin fördelning ur avtalsobjektets eget lager
(S1) eller dess skördehistorik (S2).

1. **Skördaren rapporterar före lastbilen.** Skördardatan finns i källan senast när månaden körs, också för virke som
   fälls och körs sista veckan.
2. **Allt virke som fördelas kommer från skördare med skördardata.** Inget leveransvirke, ingen manuell fällning,
   inget köpt virke utan skördardata och ingen terminal som blandar avtalsobjekt. Sedan 2026-11-17 kan källan märka
   sådant virke `utan_avverkning`: det hålls då utanför matriserna, och bilagan anger hur stor del av sågverkets
   inmätta volym matrisen gäller. I den verkliga datan är det 28 % av den levererade volymen, alla sortiment.
3. **Skördardatan är fullständig.** Ingen maskin utan rapportering och inga tappade filer.
4. **Arbetsordernas id stämmer** mellan skörd och inmätning, utan prefix eller nollor som skiljer.
5. **Sortimenten stämmer.** Det inmätta sortimentet har skördats på avtalsobjektet, eller så anger
   `producerat_handelssortiment` vad skördaren kapade.
6. **Liggaren har hela historiken**, också virke skördat före liggarens första månad.

Antagandena är metodens: fördelningen är bara S1 eller S2. Saknar ett lass egen skördardata stoppar månaden och säger
vilka avtalsobjekt och sortiment det gäller, och `check --state` visar samma stopp som `FEL`. Ingen inställning kommer
förbi det; rätta källan efter antagandet som brast. Nya avtalsobjekt i slutet av månaden pekar på antagande 1.
Avtalsobjekt som saknas helt i skörden pekar på 2, 4 eller 5. Stoppar den första månaden i en ny liggare pekar det på 6:
den behöver all skördardata som rapporterats till och med månaden, också för virke som fälldes tidigare.

Ett vänt lass antas finnas i liggaren. En negativ rad har leveransnumret, avtalsobjektet, sortimentet och
mottagningsplatsen för lasset den vänder, och lasset antas ha levererats en månad liggaren har. Finns numret inte i
liggaren, eller vänds mer än lassets månad fakturerade, stoppar månaden. Beslutat 2026-11-17, efter att den verkliga
datan visade att varje negativ rad vänder en rad med samma nummer (se stickproven nedan). En korrigering kom där som
längst 178 dagar efter lasset, så liggaren ska börja minst sex månader före den första månad som faktureras. Ett lass
som redovisades före liggarens första månad har aldrig tagits ur liggarens lager: källan tar inte med raden som vänder
det.

Volym utöver lagret (S2) bryter inget antagande. Den uppstår när lastbilen kör virke som skördaren rapporterat en del
av men inte allt, och fördelas som avtalsobjektets hela skörd. Bilagan visar den som en uppskattning, och den står kvar:
treedist körs första dagen i en ny månad för månaden innan, och ingen senare månad ändrar en bilaga som skickats.

## Känslighet

Varje variant ändrar ett antagande, med fyra nya simuleringar om 12 månader per variant. Siffrorna går att återskapa med
[sensitivity.py](../scripts/sensitivity.py) och finns i [kanslighet_resultat.csv](kanslighet_resultat.csv).

| Variant | Prisfel | Prisfel faltning | Prisfel naiv | Värdetäckning | Andel eget lager |
|---|---|---|---|---|---|
| Bas, med säsong | 4,4 | 24,0 | 40,4 | 95 % | 98 % |
| Leverans efter skörd året runt, lång lagring (förra basen) | 4,9 | 18,7 | 46,5 | 91 % | 99 % |
| Leverans under pågående skörd året runt | 3,0 | 27,6 | 32,9 | 95 % | 97 % |
| Tre gånger så lång paus före leverans | 4,4 | 25,8 | 48,3 | 93 % | 98 % |
| Destination oberoende av grovlek | 4,2 | 32,8 | 46,6 | 95 % | 98 % |
| Mindre avtalsobjekt, dubbelt så många | 4,0 | 19,1 | 26,5 | 97 % | 97 % |
| 20 % omdirigerat | 4,2 | 39,3 | 48,9 | 95 % | 97 % |

Prisfel i kr/m3fub per månad, destination och sortiment. Prisfel är metodens, lagerliggaren. Faltning och naiv är
jämförelsemetoderna i [metodjämförelsen](metodjamforelse.md): faltning på sortimentsnivå, och bara månadens skörd.

- **Rättningen av säsongen ändrade inte slutsatserna.** Den naiva metoden blev bättre med kortare lagring, 40,4 mot
  46,5, men metoden har fortfarande omkring en tiondel av dess fel. Med säsong ligger något mindre ur eget lager,
  98 mot 99 %, eftersom mer virke levereras medan skördaren är kvar.
- **Utan koppling mellan destination och grovlek ändras metodens fel knappt**, 4,2 mot 4,4, eftersom fördelningen bara
  kommer från avtalsobjektets egen skörd. Faltningen och den naiva metoden blir sämre.
- **Felet är lägst när lastbilarna följer skördaren.** Med leverans under pågående skörd året runt är prisfelet 3,0.
  Metoden drar då det äldsta virket först, i samma ordning som det körs.
- **Mindre avtalsobjekt ändrar metodens fel lite**, 4,0 mot 4,4, men den naiva metoden blir klart bättre, 26,5 mot
  40,4. Om verkliga avtalsobjekt är mindre än i simulatorn är försprånget mot den naiva metoden alltså mindre.

## Stickprov ur verklig data

Från 2026-11-03 jämförs antagandena med stickprov ur en verklig datamiljö. Stickproven är små och gäller enstaka
sågverk och månader, så de ändrar inga standardvärden än.

| Antagande | Stickprov | Bedömning |
|---|---|---|
| Ett fullt lass är cirka 45 m3fub | Fulla lass 41–49 m3fub, 1 000 inmätningsrader från oktober | Stämmer |
| Fakturamånaden kan ligga efter transporten | Transporter 14–26 oktober redovisades 2 november | Stämmer, och stöds redan |
| Inmätningen saknar dimensioner | Bekräftat. Raderna har produktnycklar till en produktdimension, vars innehåll ännu inte är känt | Stämmer |
| Producerat och inmätt sortiment skiljer sig ibland | Id:na skiljer sig på nästan varje rad, som en fast koppling mellan två kodnivåer. Enligt uppgift 2026-11-17 är det två kodlistor för samma sortiment, som i praktiken matchar. Hur ofta virket verkligen mäts in som ett annat sortiment är inte mätt | Inte prövat. Källbeskrivningen skriver om den ena listans id till den andras med `koder`, annars ser allt virke omklassat ut |
| Inmätta volymer är positiva | 26 % av raderna med nettovolym i m3fub är negativa, 27–29 % för 2017–2022 men 18 % för 2025 och 2 % för 2026. Valideringen stoppar i dag på dem | Avviker. Mönstret tyder på lass som vänds i efterhand. Stöds sedan 2026-11-03: vändningar inom månaden nettas, senare krediteras med den fakturerade fördelningen. Sedan 2026-11-09 med lassets egen månads fördelning när raden har samma leverans-id som ursprungsraden. Att källan ger samma id bekräftades 2026-11-17, se nedan |
| En korrigering har lassets leveransnummer | 2026-11-17, data från 2026: alla 7 501 negativa rader vänder hela volymen på en rad med samma leveransnummer, avtalsobjekt, sortiment och mottagningsplats. Raden har lassets transport- och mätdatum; bara redovisningsdatum skiljer, på 47 % av paren, i snitt 5 dagar och som längst 178. 96,5 % av de ommätta lassen bokas igen under samma nummer | Stämmer. Reservvägarna för okänt nummer, annan mottagningsplats och eget nummer togs bort 2026-11-17, och ett vänt lass som inte finns i liggaren stoppar. Månadens rader ska väljas på redovisningsdatum |
| Leveransen har producerat sortiment och producerat för mottagningsplats | 2026-11-17: ingen leveransrad saknar någon av dem | Stämmer |
| Ett avtalsobjekt levererar till flera mottagningsplatser | 2026-11-17, leveranser från 2026-01-01: av 19 968 arbetsordrar med volym har 39 % volym till mer än en mottagningsplats: 61 % till en, 11 % till två, 9 % till tre och 19 % till fyra eller fler. Räknat över alla sortiment och med korrigeringsrader. Den största mottagningsplatsen får i median 100 % av arbetsorderns volym och i snitt 84 %, men volymvägt 64 %: de stora arbetsordrarna delas mer. I produktionen får det största värdet på producerat för i median 99,9 % och volymvägt 80 % | Säger inte hur ofta samma sortiment delas mellan mottagningsplatser, eftersom massaved, timmer och energived går till olika industrier. Det är den frågan som avgör hur mycket lagret per mottagningsplats betyder. Öppet |
| Produktionen har producerat för mottagningsplats | 2026-11-17: saknas på ungefär 17 % av stockarna mars–oktober 2026, 23 % i januari och 54 % i februari. Räknat i antal stockar för alla sortiment; inte känt om det gäller sågtimret, eller hela avtalsobjekt. Datalagret har också en destinerad mottagningsplats per stock. Av 73,9 miljoner stockar fällda från 2026-01-01 har 0,3 % samma värde i de två kolumnerna, och ingen av dem är tom utan har ett eget värde för saknas. Högst 0,3 % av stockarna kan alltså sakna båda | Avviker. Sedan 2026-11-18 stoppar det inte: skörd utan uppgiften lämnas tom i källan och tas av avtalsobjektets lass när deras egna lager är slut. Det är rätt där avtalsobjektets sortiment har en mottagningsplats, och en blandning där det kapas för flera. Hur luckan fördelar sig per avtalsobjekt och sortiment är inte mätt. Nästan varje stock har minst en av de två uppgifterna, men om de går att använda i varandras ställe är inte prövat. Öppet |
| Avverkningsdatum per stock | 2026-11-17: ingen rad saknar det, och ett avtalsobjekt har i snitt 8–13 olika avverkningsdagar | Stämmer. Datumet är fällningsdagen, inte rapportdagen |
| Varje lass har skördardata | Ett sågverk en månad: alla 297 par av avtalsobjekt och sortiment, 43 600 m3fub, hade skördardata. 2026-11-17, hela datan, alla sortiment: av 20 002 arbetsordrar med leveranser körda från 2026-01-01, 7,1 miljoner m3fub, saknar 13 252 stockdata, 2,1 miljoner m3fub eller 29 % av volymen. 94 % av den volymen ligger på arbetsordrar som enligt sin typ inte har någon produktion: centrala köp (73 %), egen terminal (11 %), virkesköp utan produktion (5 %) och import (5 %). Grotskotning är 5 %. Avverkning som borde ha skördardata men saknar den är 67 arbetsordrar och 15 900 m3fub: 1 % av avverkningsordrarna och 0,3 % av deras volym | **Stämmer för avverkat virke, inte för allt virke.** Där arbetsordern är en avverkning saknas skördardata på 0,3 % av volymen. Men 28 % av den levererade volymen kommer inte från någon avverkning i systemet, och går att känna igen på arbetsorderns typ. Sedan 2026-11-17 märker källan det virket `utan_avverkning`: det fördelas inte, och bilagan anger dess volym utanför matrisen. Hur stor del av sågtimret till ett sågverk det gäller är inte mätt |
| Skördardata finns per klass | Skördardatan finns per stock med topp-, mitt- och rotdiameter, längd, volym och fällningsdag | Bättre än antaget. Klasserna kan räknas fram från prislistans klassindelning |
| Skörd och lager bokas på avtalsobjektets planerade destination | Varje stock har en destination den kapades för | Bättre än antaget. Lagret delas per destination, och sedan 2026-11-17 tar varje lass ur lagret för den mottagningsplats det producerades för |

## Från skördare via skotare till mätram

Genomgång 2026-11-08 av hur virket skördas, skotas och mäts in, mot det metoden antar. Inget av detta är prövat på
verkliga data.

**Kedjan.** Skördaren kapar efter mottagande industris aptering och rapporterar per stock toppdiameter under bark,
längd, klass enligt sin produktdefinition, stamkoordinat och destination. Skotaren kör virket till avlägg och
rapporterar i fpr vilken produkt som ligger vid vilket avlägg, med uppskattad volym per lass. Föraren flyttar stockar
med krök eller röta från timmer till massaved, så kallad sortimentsvandring, och lastbilarna börjar ibland hämta innan
allt är framkört. Vid industrin stockmäts det mesta sågtimret i mätram: toppdiameter, längd, kvalitet och avdrag per
stock, med bark- och diameterkorrektion per mätplats. Volymen räknas från toppcylindervolym (m3to) till m3fub med
omräkningstal, och vrak ingår i bruttot. Resultatet är en stocklista. Travmätt timmer får en kvalitetsklass och en
bedömd medeldiameter.

| Det metoden inte tar hänsyn till | Varför det spelar roll | Bedömning |
|---|---|---|
| Mätramens klasser är inte skördarens | Metoden kalibrerar volymen, inte klassgränserna. Skördarna mätte i snitt 1,6 mm grövre medeldiameter än stockmätningen, med standardavvikelse 8,5 mm mellan partier (Karlsson 2011). Med 1 cm-klasser flyttar 1,6 mm ungefär en sjättedel av volymen en klass. En stock som mätramen mäter under längdklassens botten faller en hel längdklass | **Troligen störst.** Bilagan visar skördarens klassning. Simulatorn antar 2 mm systematiskt per maskin, troligen för lite. Kan bara skattas mot stocklistor |
| Vrak, avdrag och nedklassning är inte slumpmässiga | Krök är vanligaste orsaken (Biometria 2026), röta sitter i rotstockar av gran, blånad i sommarvirke som legat länge, och skotarens sortimentsvandring tar samma stockar. Metoden drar bruttot pro rata | Liten volym men riktad. Samma begränsning som för omklassning |
| Destinationen per stock | Skördaren kapar varje stock för en industri. Före 2026-11-08 delade metoden ett avtalsobjekts lager mellan destinationerna efter nettovolym, så ett klent och ett grovt sågverk fick samma blandning | Stor där samma handelssortiment går till flera sågverk, annars ingen. Metoden använder nu uppgiften när skördardatan har den, se nedan |
| Skotning och avlägg | Lastbilen tar bara det som skotats fram, och avlägg skiljer sig i grovlek. fpr och stamkoordinater i hpr finns i standarden | Se förbättring 2 nedan |
| Kvalitet | I VIOL 3 är sågtimrets produkter kvalitetsklasser, tall 0110–0114 och gran 0120–0122, plus vrak. Mäts virket in per kvalitet får varje kvalitet avtalsobjektets hela fördelning, fast kvalitet 1 i tall mest är grova rotstockar | Summan stämmer, varje kvalitet för sig blir för lik de andra. Kontrollera vad produktnycklarna betyder |
| Volymen räknas olika | Mätramen räknar m3fub ur m3to med omräkningstal efter toppdiameter och längd, skördaren summerar sektioner. En enda faktor på 0,9 % flyttar lite volym mellan klasser | Liten |

Ej granskat: terminaler, järnväg och om torkning krymper diametern före mätning.

### Destinationen per stock

Granskat 2026-11-08 ur Biometrias regler för hpr i VIOL 3 och för sortimentsstrukturen. Inte prövat på verkliga data.

**Hur destinationen följer stocken.** Varje produktdefinition i skördarens hpr-fil kan ange den mottagningsplats den
kapas för, *Producerat för mottagningsplats*. Biometria delar produktionsresultatet på den. Uppgiften är frivillig. Samma handelssortiment kan
alltså kapas för flera sågverk på samma trakt, med olika produktdefinitioner och olika aptering.

**När lagret redan är delat.** Metoden delar lagret på avtalsobjekt och handelssortiment. VIOL 3 har tre sätt att hålla
isär virke som kapats för en viss industri:

1. Ett industrispecifikt handelssortiment, vars identitet innehåller industrin.
2. Olika branschgemensamma handelssortiment efter grovlek, till exempel tallsågtimmer, klenare och grövre. De har
   samma produkter men hålls isär i produktion, mätning och redovisning.
3. Samma branschgemensamma handelssortiment, med industrin angiven som *Producerat för mottagningsplats* vid
   destineringen.

I de två första fallen delar handelssortimentet redan lagret per industri, och ett lager per destination ändrar
ingenting. I det tredje fallet hamnar virke till olika sågverk i samma lager. Det verkliga stickprovet har uppgiften
producerat för mottagningsplats per stock, så den finns. Om den skiljer sig inom ett avtalsobjekt och ett
handelssortiment är inte undersökt.

**Hur stort felet blir.** Anta att ett avtalsobjekts sågtimmer delas efter toppdiameter mellan ett klent och ett grovt
sågverk, i samma handelssortiment. Med simulatorns stockar, åtta frön, hamnar då följande andel av volymen i klasser
som sågverket aldrig fick:

| Gräns, toppdiameter | Andel volym över gränsen | Andel volym i fel klass |
|---|---|---|
| 18 cm | 90 % | 13 % |
| 20 cm | 81 % | 21 % |
| 22 cm | 71 % | 28 % |
| 24 cm | 59 % | 34 % |

Felet är systematiskt: det klena sågverket får för grova klasser och det grova för klena. Det är flera gånger större
än metodens fel i övrigt, men bara på de avtalsobjekt där samma handelssortiment delas. Hur vanligt det är visar
skördardatan: andelen volym per avtalsobjekt och handelssortiment som har en annan tänkt mottagningsplats än den
största.

**Prövat i simulatorn 2026-11-08.** Simulatorn kan nu dela hälften av avtalsobjekten efter toppdiameter mellan klen-
och grovsåg. Ett lager per mottagningsplats sänkte prisfelet där med 19 kr/m3fub, se
[metodjamforelse.md](metodjamforelse.md).

**Omdestinerat virke.** Ett lass kan gå till ett annat sågverk än det virket kapades för. I VIOL 3 säger leveransen
vilken mottagningsplats virket producerades för, så lasset tar ur det lagret och bokas där det mättes in. Sedan
2026-11-17 tar ett lass aldrig ur en annan mottagningsplats lager: det som det egna lagret inte räcker till är en
uppskattning (S2). I simulatorn kostade det 0,02 i poäng på kontrollfröna, inom bruset, och prisfelet sjönk något.

## Det som skulle förbättra mest

1. **Ta reda på om allt levererat virke har skördardata när månaden körs.** Metoden antar det, och ett lass utan
   stoppar månaden. Gäller särskilt köpt virke och import, och virke som fälls och körs sista veckan i månaden.
2. **Avlägg eller startplats per leverans.** Biometria skapar leveransinnehåll per avtalsobjekt, handelssortiment och
   startplats, och hpr-filer innehåller koordinater per stam. Metoden drar sedan 2026-11-08 ur lagret per startplats när
   både skördardatan och inmätningen har kolumnen `startplats`; i simulatorn, med 10 % av stockarna på fel avlägg,
   sänkte det prisfelet med 0,7 kr/m3fub. Det som återstår är att knyta stammarnas koordinater till startplatserna.
   Kopplingen måste vara rätt för de flesta stockar: med 30 % på fel avlägg sjönk vinsten till 0,25, och med 50 % blev
   prisfelet 0,25 sämre än utan avlägg. Hamnar mer än en tredjedel fel, lämna kolumnen tom.
3. **Löpande skördarrapportering.** Med kort sommarlagring ökar annars andelen uppskattad volym (S2), och risken att
   ett lass saknar skördardata när månaden körs.
4. **Stocklistor från stockmätningen, som facit.** Redan en månad från ett sågverk visar hur stor skillnaden mellan
   skördarens och mätramens klasser är, hur vrak fördelar sig och vad kvalitetsprodukterna betyder. Ta också reda på
   mätmetoden per sågverk. Där sågverket stockmäter har det redan sin egen fördelning att jämföra bilagan med; där
   virket travmäts eller vägs ger bilagan ny information.
5. **Lager per destination.** Byggt 2026-11-08. Det som återstår är att mappa källans uppgift till
   `producerat_for_mottagningsplats`, med samma id som i mätningen, och mäta hur ofta samma sortiment delas.

## Källor

Alla projektets källor, med vad var och en visar, finns i [kallor.md](kallor.md).

- [Skogsstyrelsen, lager av sågtimmer, massaved och massaflis](https://www.skogsstyrelsen.se/statistik/avverkning/lager-av-sagtimmer-massaved-och-massaflis/)
- [Skogsstyrelsen, avverkningen 2025](https://www.skogsstyrelsen.se/nyhetslista/avverkningen-fortsatte-att-minska-2025/)
- [Skogforsk, Arbetsrapport 1231-2025, kostnader, lönsamhet och lager](https://www.skogforsk.se/cd_20250211113825/contentassets/b3d3919b3ac744fe82937338733fc85a/arbetsrapport-1231-2025-kostnader-intakter-lonsamhet-produktivitet-och-kvalitet-pa-utforda-atgarder-i-svenskt-skogsbruk.pdf)
- [Skogsstyrelsen, avverkningsanmälningar 2021](https://www.skogsstyrelsen.se/globalassets/statistik/statistikfaktablad/JO0314-statistikfaktablad-avverkningsanmalningar-2021.pdf)
- [Holmen, marknadsprislista 2026](https://www.holmen.com/globalassets/skog/prislistor/ny-20260416-marknadsprislista-hnd6l4-arvidsjaur-mala-norsjo-lucksele-sorselle-storuma-vilhelmina-stromsund-dorotea.pdf)
- [Mellanskog, allmänna leveransbestämmelser 2025](https://www.mellanskog.se/wp-content/uploads/2025/08/allmanna-leveransbestammelser.pdf)
- [Sveaskog, prislista Svealand och södra Norrland 2025](https://www.sveaskog.se/globalassets/skogsagare/2025/7995-s2-svealand-och-sodra-norrland-251215.pdf)
- [Biometria, regler vid tolkning av hpr](https://www.biometria.se/media/vezp5bej/biometria-regler-vid-tolkning-av-hpr.pdf)
- [Biometria, tolkning av hpr i VIOL 3 (2025)](https://www.biometria.se/media/g4zbgb1j/biometria-regler-vid-tolkning-av-hpr-viol3-20251020.pdf)
- [Biometria, Fältdata för ersättningsgrundande virkesmätning (2026)](https://www.biometria.se/media/4ulozgo3/faeltdata-foer-ersaettningsgrundande-virkesmaetning.pdf)
- [Biometria, Simulera stockdatainsändning (2021)](https://www.biometria.se/media/tsclkavv/instruktion-simulera-stockdatainsaendning_2021-01-29.pdf)
- [Biometria, Mätning av stockars fastvolym (2015)](https://www.biometria.se/media/ekub3gwo/maetning-av-stockars-fastvolym-dec-2015.pdf)
- [Karlsson 2011, skördarmätt medeldiameter mot stockmätning, SLU](https://stud.epsilon.slu.se/2912/1/Karlsson_A_20110623.pdf)
- [Skogforsk, skotning](https://www.skogforsk.se/contentassets/e7f5fe3dd2204c8f906f17a9350b4d79/skotning.pdf)
- Övriga källor om mätning och volymer: [underlaget för simuleringen](simuleringsunderlag.md)
