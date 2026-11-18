# Metod

## Problemet

Under en månad finns två datakällor i VIOL 3 om virket till sågverket. Produktionen är skördarens
produktionsrapportering i hpr, inte ersättningsgrundande skördarmätning. Mätningen vid mottagningsplatsen är den som
senare affärsled betalar efter.

| | Produktion (hpr) | Mätning vid mottagningsplatsen |
|---|---|---|
| Nyckel | avtalsobjekt, producerat handelssortiment, diameterklass, längdklass | leveransnummer, avtalsobjekt, handelssortiment |
| Styrka | Fördelningen över dimensioner och antal stockar | Volymen som kom fram, brutto och netto, som fakturan bygger på |
| Svaghet | Mäter virket när det avverkas, inte när det levereras | Säger inget om dimensioner eller antal stockar |

Det svåra är tiden. Varje avtalsobjekt skördas under 1–3 veckor och levereras sedan under 1–3 veckor, så månadens
skörd beskriver inte månadens leveranser. Avtalsobjekt som töms inom månaden får sin fördelning känd. Felet uppstår
för dem som korsar ett månadsskifte.

Metoden låter därför de två källorna svara på var sin fråga. Mätningen avgör **hur mycket**. Skördardatan avgör
**hur det fördelar sig**, via en liggare som bär med sig oleverat virke mellan månaderna.

treedist körs första dagen i en ny månad, för månaden innan, och ger en bilaga per sågverk till månadens faktura. En
bilaga som skickats ändras inte av senare månader. Metoden antar att varje lass har skördardata för sitt avtalsobjekt
och sitt sortiment när månaden körs.

## Månadsstängning

För varje kombination av avtalsobjekt och handelssortiment (AO × sortiment):

1. **Kalibrering.** Skördad volym multipliceras med `(1 - harvester_bias)(1 - handling_loss)` och läggs i lagret
   per diameter, längd och avverkningsmånad.
2. **Avräkning.** Har avtalsobjektet en tidigare månad levererat mer än lagret rymde står den volymen som underskott i
   liggaren. Kommer skördardata sedan in tas underskottet ur lagret först, så att samma virke inte levereras två
   gånger. Underskottet minns bruttovolymen som lämnade avlägget, och det är den som tas. Bilagan som skickades
   ändras inte: volymen står kvar som den uppskattades, och inget läggs på en senare faktura.
3. **Dragning.** Bruttovolymen tas ur lagret, eftersom den lämnat avlägget. Började månadens leveranser innan det
   sista i lagret var avverkat följer lastbilarna skördaren, och då går det äldsta virket först. Det är vanligt på
   sommaren, när köparna vill ha sågtimret fram inom ett par veckor. Annars är lagret blandat på avlägget och
   varje klass ger samma andel. Vilken månad ett lass faktureras avgör källan: månadens rader är de som
   redovisades i månaden. Ett lass som kördes i slutet av en månad och redovisades i nästa dras med sitt
   leveransdatum.

   **Dagmetoden** (`draw_per_day`, `--modell dag`) drar i stället dag för dag, i den ordning lassen kördes. Varje
   dags lass tar bara virke som är fällt senast den dagen. Det som det virket inte räcker till är volym utöver lagret
   och fördelas som avtalsobjektets hela skörd (S2), medan virke som fälldes senare ligger kvar i lagret till senare
   dagar och månader. Dagar som har samma virke fällt senast sig dras tillsammans, så ordningen mellan lass som
   ingen avverkning skiljer spelar ingen roll. Var allt virke fällt före månadens första lass blir det samma
   dragning som med månadsmetoden. Om lastbilarna följer skördaren, och tar det äldsta virket först, avgörs en gång
   för månaden som ovan. Destination, avlägg och krediteringar är desamma. Två saker skiljer i avräkning och avslut:
   - Ett underskott från en tidigare månad räknas av mot virke som fälldes senast den månaden först, i lika andelar,
     och först därefter mot senare virke, äldst först. Månadens nyfällda virke ligger då kvar åt månadens lass.

   Dagmetoden är känslig för datum: både leveransdatum och avverkningsdatum ska gälla dagen. Blir volym en
   uppskattning fast virke som fälldes senare i månaden låg kvar i lagret, säger körningen och `check` det; över 5 %
   av leveransen är det en varning, eftersom ett datum då oftare är fel än att virket saknades. I simulatorn ger
   dagmetoden samma prisfel som standardmodellen inom bruset, eftersom simulatorn bara kör virke som redan är fällt.
4. **Destination.** Levererad volym bokas hos mottagningsplatsen leveransen mättes in vid. Lagret är uppdelat på den
   mottagningsplats skördaren kapade för (VIOL 3: *Producerat för mottagningsplats*), och varje leverans säger vilken
   det var. Lasset tar bara ur det lagret, också när det mättes in någon annanstans; det som lagret inte räcker till
   är volym utöver lagret (S2), aldrig virke som kapades för en annan mottagningsplats. Uppgiften är frivillig i hpr.
   Skörd som rapporterats utan den är avtalsobjektets virke utan känd mottagningsplats: ett lass tar det när lagret
   för dess egen mottagningsplats är slut, som eget lager (S1), och först det som inte heller ryms där är volym utöver
   lagret. Där ett sortiment från avtalsobjektet kapas för flera mottagningsplatser delar deras lass på det virket,
   eftersom arbetsordern inte säger vems det var. Anger både produktionen och
   mätningen startplatsen, avlägget, tar varje lass först virket vid sitt eget avlägg, och det som inte räcker ur
   resten av samma lager, eftersom avlägget räknas fram ur stamkoordinaterna och kan bli fel.
5. **Omklassning.** Lagret förs på det sortiment skördaren producerade. Virke som mätts in som ett annat sortiment dras
   ur det producerade sortimentets lager men bokas och faktureras som inmätt, med samma fördelning.
6. **Säkerhetsklass.** Volymen får en klass efter var fördelningen kommer ifrån, se nedan.
7. **Vända lass.** En negativ rad vänder ett lass och har lassets leveransnummer, avtalsobjekt, sortiment och
   mottagningsplats (VIOL 3: en korrigering pekar på leveransen den ändrar). Månadens rader för ett lass räknas
   samman, netto och brutto var för sig. Finns lasset bara i månaden levereras det som blir kvar. Fakturerades
   lasset en tidigare månad gäller skillnaden mot det: en lägre nettovolym krediteras på raden `KREDITERING` med
   den fördelning lassets månad fakturerades med, och en högre levereras i månaden. Liggaren sparar det fakturerade
   per månad och vilken månad varje leveransnummer först levererades. Lagret ändras med skillnaden i bruttovolym:
   virke som kom tillbaka går tillbaka till lagret, och ett lass som bara mätts om till en annan nettovolym flyttar
   inget virke. Högre nettovolym utan mer bruttovolym fördelas som månadens övriga lass från avtalsobjektet och
   sortimentet, eller som avtalsobjektets hela skörd (S2) när det inte finns några. Den del av en kreditering som
   levererades utöver lagret tas ur underskottet. Finns leveransnumret inte i liggaren, eller har mer vänts än
   lassets månad fakturerade vid mottagningsplatsen, stoppar månaden. Ett lass som redovisades före liggarens
   första månad har aldrig tagits ur liggarens lager; källan tar då inte med raden som vänder det.
8. **Avslut.** När tabellen `avtalsobjekt` säger att transporten är avslutad (`transport_avslutad` = true) skrivs
   kvarvarande lager och underskott av efter första månaden, den månaden eller en senare, där ingen leverans från
   avtalsobjektet mätts in. Ett lass som kördes före avslutet och mäts in månaden efter tar alltså fortfarande lagret.
   treedist minns avtalsobjektet tills dess, också om senare månaders tabell inte längre har det med. Lager och
   underskott som skrivs av syns i `utveckling/avstamning_ao.csv`, som skrivs med `--utvecklare`, som `avskrivet` och
   `avskrivet_underskott`. Skördehistoriken sparas: levererar avtalsobjektet igen efter avskrivningen fördelas volymen
   som dess hela skörd (S2), och körningen ber en person se efter om `transport_avslutad` stämmer. Ett lass som vänds
   efter avskrivningen går tillbaka till lagret och ligger kvar där.

### Säkerhetsklasser

| Klass | Fördelningens källa | När | I bilagan |
|---|---|---|---|
| S1 | Avtalsobjektets eget olevererade skördarlager | Så mycket som ryms i lagret | Eget lager, mätt av skördaren |
| S2 | Avtalsobjektets hela skördehistorik | Det som levererats utöver lagret | Egen skörd i snitt, uppskattad |

S2 är en uppskattning och står i bilagan som en sådan, med ett exempel i tre steg som visar hur den räknas. Den står
kvar: kommer skördardatan senare räknar liggaren av volymen (steg 2), men ingen bilaga ändras och inget läggs på en
senare faktura. Med `--utvecklare` skrivs skillnaden mellan uppskattningen och den skördardata som sedan kom till
`utveckling/uppskattning_mot_skordardata.csv`, för uppföljning av hur bra uppskattningen var.

Finns ingen skördardata för lassets avtalsobjekt och sortiment finns inget att fördela efter. Då har något av
[antagandena](antaganden.md#antaganden-som-gör-s1-och-s2-tillräckliga) brustit, och månaden stoppar med besked om vilka
avtalsobjekt och sortiment det gäller. Ingen inställning kommer förbi stoppet.

### Varför volymen i bilagan alltid stämmer

Nettovolymen fördelas, den ändras aldrig. Summan av alla rader per sortiment är exakt inmätningen, och
körningen avbryts om den inte är det. Volymer räknas i hela liter, så att raderna går jämnt upp. Fördelningen flyttar
alltså volym mellan klasser men aldrig in eller ut ur månaden.

Samma rader blir bilagan till varje sågverks faktura, `bilagor/<destination>.html` och `.xlsx`: en matris för alla
handelssortiment tillsammans, längd i dm som rader och diameter i cm som kolumner, med summor som går jämnt upp mot
inmätningen. treedist sätter inga priser; utvärderingen i `dev/` väger felen med en exempelprislista, så att ett fel i
en dyr klass väger tyngre.

## Osäkerhet

`treedist run` drar inga intervall: bilagan visar inga, och säkerhetsklasserna säger hur säker fördelningen är.
Monte Carlo används när metoden utvärderas mot simulatorn, för att pröva om osäkerheten är rätt skattad. Varje
dragning slumpar om två saker.

- **Fördelning.** Dirichletbrus kring den fördelning som bokades. Bruset är så stort som urvalet motiverar:
  - **S1.** Antalet stockar delat med `design_effect`, eftersom stockar åker i vältor från samma del av beståndet,
    är det effektiva antalet oberoende stockar. Ändlighetskorrektionen gör bruset mindre ju större del av skörden som
    levererats, och tar bort det bara om hela skörden levereras samma månad. En rest i en senare månad är lika osäker
    som första delen. Skördarens klassning finns alltid kvar, ett fel per stock.
  - **S2.** Samma sak, med antagandet att `pool_remaining_share` av skörden ännu inte syns i skördardata.
- **Volym.** Per leverans `unit_cv / sqrt(antal_matenheter)`, plus ett fel per metod som delas av alla månadens
  leveranser.

Utvärderingen redovisar två spridningar. `std_fordelning` håller volymen fast och är osäkerheten i fördelningen.
`std`, `p05` och `p95` lägger till volymfelet och beskriver vad som fysiskt levererades.

## Parametrar och källor

Metodens parametrar, som `treedist run` läser (`src/treedist/config.py`):

| Parameter | Standard | Grund |
|---|---|---|
| `harvester_bias` | 0,009 | Biometria 2025: skördaren överskattar 0,9 % under bark (1,2 % på bark), tabell 6–7 |
| `handling_loss` | 0,01 | Antagande. Biometria 2026 räknar i ett exempel med 1 % färre stockar framme |
| `oldest_first` | på | Av: varje klass ger alltid samma andel. Används av den sparade modellen `enkel` |
| `draw_gross` | på | Av: nettovolymen lämnar lagret, bruttovolymen används inte |
| `stock_per_landing` | på | Av: lasset drar ur hela lagret för den mottagningsplats det producerades för, inte först vid sitt avlägg. Gör ingen skillnad när produktionen eller mätningen saknar `startplats` |
| `stock_per_destination` | på | Av: alla mottagningsplatser delar avtalsobjektets lager, som före 2026-11-08 |
| `stock_without_destination` | på | Av: inget lass tar skörd som rapporterats utan producerat för mottagningsplats, och det som lassets eget lager inte räcker till blir volym utöver lagret (S2), som före 2026-11-18. Gör ingen skillnad när varje skördarrad har uppgiften |

Ett lass som vänds en senare månad krediteras alltid med den fördelning dess månad fakturerades med, hittad med
leveransnumret. Tills 2026-11-17 gick det att stänga av (`credit_per_load`); en konfiguration med `credit_per_load =
true` läses som förut, och `false` stoppar.

Monte Carlo-parametrarna, som bara utvärderingen läser (`src/treedist/dev/uncertainty.py`). En sparad modell har båda; körningen läser förbi dessa.

| Parameter | Standard | Grund |
|---|---|---|
| `design_effect` | 200 | Inställd mot simulatorn, den enda parametern som styr bredden på intervallen för S1 och S2 |
| `pool_remaining_share` | 0,5 | Antagande: när ett avtalsobjekt levererar utöver lagret syns halva skörden ännu inte i skördardatan |
| `default_log_volume` | 0,25 | Antagande: medelstockvolym när skördardata saknar antal stockar |
| `finite_population` | på | Av: ingen ändlighetskorrektion, bruset följer bara effektivt antal stockar. Lätta intervall i modellen `halv` |
| `volume_error` | på | Av: inget volymfel i Monte Carlo, så `std` blir lika med `std_fordelning` |
| `log_counts` | på | Av: antal stockar läses inte; bruset följer volymen genom `default_log_volume` × `design_effect`. Modellen `halv-volym` |
| `intervals` | på | Av: inga dragningar. Modellen `enkel` |
| `stockmatning` | `unit_cv` 0,043 | Biometria 2025, tabell 1. Systematiskt fel härlett ur KI ±0,1 % |
| `travmatning` | `unit_cv` 0,051 | Biometria 2025, tabell 1, sågbara. Systematiskt fel härlett ur KI ±0,3 % |
| `vagning` | `unit_cv` 0,069 | Antagande: nivån för travmätt massaved i tabell 1, inte en vägningssiffra |
| `skordarmatning` | `unit_cv` 0,050 | Biometria 2025, tabell 7, stamvis under bark. Systematiskt fel antaget |
| `okand` | `unit_cv` 0,080 | Antagande, medvetet försiktigt |

## Utvärdering

`treedist backtest` bygger ett virkesflöde med känt facit: bestånd, stockar, avlägg, leveranskampanjer och lastbilar.
Metoden får bara det verkliga system skulle se. [Underlaget](simuleringsunderlag.md) beskriver vad simulatorn bygger på.
Resultat, jämförelsemetoder och jämförelse med forskningen finns i [metodjämförelsen](metodjamforelse.md).

I korthet, i basscenariot: 5,8 % av volymen hamnar i fel cell mot 18,0 % om man bara använder månadens skörd, och
medelpriset fel med 4,3 mot 40,5 kr/m3fub. Över tolv månader är prisfelet 1,0 kr/m3fub. Värdeintervallet täcker 86–93 %
mot nominellt 90 %. Simulatorns lagringstider följer säsongen, se [antaganden](antaganden.md). I simulatorn har varje
lass skördardata, som metoden antar.

Eftersom leveranser saknar diameter och längd finns inget direkt facit i verklig drift. Det som går att följa upp är
volymbalansen när avtalsobjekt avslutas. Inget av detta är prövat på verkliga data.

## Medvetna begränsningar

- **Varje skördarrad hör till en månad.** Tabellerna i dataplattformen antas sakna dubbletter, och månadens uttag ska
  bara innehålla rader som inte varit med tidigare. Ett uttag av hela tabellen varje månad skulle dubbelräknas.
- **Första månaden.** Virke skördat före liggarens första månad finns inte i liggaren. Den första månaden behöver därför
  all skördardata som rapporterats till och med månaden, också för virke som fälldes tidigare; annars saknar månadens
  lass skördardata och körningen stoppar. Börja minst sex månader före den första som ska faktureras, så att liggaren
  vet vad som redan levererats och har de lass som senare vänds.
- **Virke utan avverkning fördelas inte.** Köpt virke, import och virke från terminal har ingen skördardata. Källan
  märker det `utan_avverkning`, treedist håller det utanför matriserna, och bilagan anger hur stor del av sågverkets
  inmätta volym matrisen gäller. Ett sågverk som bara fick sådant virke får ingen bilaga. Har källan
  `anskaffningsform` visar bilagan också den inmätta volymen per anskaffningsform, och vad av den som fördelades ur
  eget lager, som egen skörd i snitt eller står utanför matrisen.
- **Omklassat virke antas vara ett slumpmässigt urval av lagret.** I verkligheten är det troligen de klenaste eller
  sämsta stockarna som klassas ned, så timmerfakturan blir något för klen och den nedklassade volymen för grov. Utan
  `producerat_handelssortiment` syns omklassning bara som över- och underskott per sortiment i
  `utveckling/avstamning_ao.csv`.
- **Kvalitetsklasser ingår inte.** En produkt är sortiment, diameter och längd. Kvalitet måste ligga i sortimentet.
- **Bara m3fub.** Bilagan visar volym, inga priser eller belopp.

## Källor

- [Biometria, Kvalitetsrapport 2025](https://www.biometria.se/media/zqzgry3k/kvalitetsrapport-biometria-2025-low.pdf)
- [Biometria, Tolkning av hpr i VIOL 3 (2025)](https://www.biometria.se/media/g4zbgb1j/biometria-regler-vid-tolkning-av-hpr-viol3-20251020.pdf)
- [Biometria, Fältdata för ersättningsgrundande virkesmätning (2026)](https://www.biometria.se/media/4ulozgo3/faeltdata-foer-ersaettningsgrundande-virkesmaetning.pdf)
- [Biometria, Krav och åtgärdsnivåer (2025)](https://www.biometria.se/media/r4wf21el/biometrias-krav-och-aatgaerdsnivaaer-antagna-_251211.pdf)
- [Mellanskog, Virkesprislista november 2025](https://www.mellanskog.se/wp-content/uploads/2025/11/virkesprislista-malar-251119.pdf)
- [Lag (2014:1005) om virkesmätning](https://data.riksdagen.se/dokument/sfs-2014-1005.html)
- [Skogsstyrelsens föreskrifter om virkesmätning, SKSFS 2014:11](https://wwwprod.skogsstyrelsen.se/globalassets/lag-och-tillsyn/foreskrifter-efter-amne/virkesmatning/sksfs-2014-11--skogsstyrelsens-foreskrifter-om-virkesmatning.pdf)
