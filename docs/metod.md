# Metod

## Problemet

Under en månad finns två datakällor om virket till sågverket. Skördardata är skördarens produktionsrapportering, inte
ersättningsgrundande skördarmätning. Inmätningen vid industri är den mätning som senare affärsled betalar efter.

| | Skördardata | Inmätning vid industri |
|---|---|---|
| Nyckel | arbetsorder, handelssortiment, diametergrupp, längdgrupp | arbetsorder, handelssortiment, ibland lastbil |
| Styrka | Fördelningen över dimensioner och antal stockar | Volymen som kom fram, brutto och netto, som fakturan bygger på |
| Svaghet | Mäter virket när det avverkas, inte när det levereras | Säger inget om dimensioner eller antal stockar |

Det svåra är tiden. Varje arbetsorder skördas under 1–3 veckor och levereras sedan under 1–3 veckor, så månadens
skörd beskriver inte månadens leveranser. Arbetsordrar som töms inom månaden får sin fördelning känd. Felet uppstår
för dem som korsar ett månadsskifte och för virke utan skördardata.

Metoden låter därför de två källorna svara på var sin fråga. Inmätningen avgör **hur mycket**. Skördardatan avgör
**hur det fördelar sig**, via en liggare som bär med sig oleverat virke mellan månaderna.

## Månadsstängning

För varje kombination av arbetsorder och handelssortiment (AO × sortiment):

1. **Kalibrering.** Skördad volym multipliceras med `(1 - harvester_bias)(1 - handling_loss)` och läggs i lagret
   per diameter, längd och avverkningsmånad.
2. **Korrigering.** Finns ett underskott från tidigare månad och har skördardata kommit in, tas den volymen ur
   lagret. Skillnaden mot den preliminära fördelningen bokas som korrigering.
3. **Dragning.** Bruttovolymen tas ur lagret, eftersom den lämnat avlägget. Varje leverans drar pro rata ur virke som
   var avverkat och skotat på leveransdatumet (`dated`). Utan datum räknas leveransen till månadens slut. Började
   leveranserna innan det sista i lagret var avverkat följer lastbilarna skördaren, och då går det äldsta virket först
   (`overlap_fifo`). Det är vanligt på sommaren, när köparna vill ha sågtimret fram inom ett par veckor.
4. **Destination.** Alla destinationer delar liggare, eftersom en arbetsorders lager är samma virke vart det än går.
   Levererad volym hamnar hos mottagningsplatsen om den finns, annars hos den planerade destinationen. Går en arbetsorder
   till flera destinationer delas fördelningen efter nettovolym.
5. **Omklassning.** Lagret förs på det sortiment skördaren producerade. Virke som mätts in som ett annat sortiment dras
   ur det producerade sortimentets lager men bokas och faktureras som inmätt, med samma fördelning. Ett underskott
   minns vilket sortiment det fakturerades som, så att korrigeringen hamnar där.
6. **Säkerhetsklass.** Volymen får en klass efter var fördelningen kommer ifrån, se nedan.
7. **Avslut.** För avslutade arbetsordrar skrivs kvarvarande lager av och underskott blir slutgiltiga.

### Säkerhetsklasser

| Klass | Fördelningens källa | När |
|---|---|---|
| S1 | AO:ns eget olevererade skördarlager | `V` ryms i lagret, med toleransen `coverage_tolerance` |
| S2 | AO:ns hela skördehistorik | Mer levererat än lagret räcker till |
| S3 | Andra arbetsordrar i samma sortiment, viktade efter likhet | Skördardata saknas för AO:n |
| S4 | Inget, bokas på klassen `OKÄND` | Skördardata saknas för hela sortimentet |

S2, S3 och S4 är preliminära. De ligger kvar som underskott i liggaren och korrigeras när skördardata kommer.
S4 får bara ett pris om prislistan har en uttrycklig regel för det, annars flaggas volymen och debiteras inte.

### Varför volymen på fakturan alltid stämmer

Nettovolymen fördelas, den ändras aldrig. Summan av alla rader per sortiment är exakt inmätningen, och
körningen avbryts om den inte är det. Volymer räknas i hela liter och belopp i hela ören, så att raderna går jämnt
upp. Osäkerheten flyttar alltså värde mellan produkter men aldrig volym in eller ut ur fakturan.

## Osäkerhet

Varje dragning i Monte Carlo-simuleringen slumpar om det som inte är känt:

- **Fördelning, S1.** Vilka delar av skörden som åkte: fördelningar för 5-dagarsblock av skörden blandas med Dirichletvikter.
  Skillnaderna inom arbetsordern hämtas alltså ur skördardata. Ovanpå det kommer urvalsbrus, styrt av `design_effect`.
  Ändlighetskorrektionen tar bort urvalsosäkerheten bara om hela skörden levereras samma månad. En rest i en senare månad
  är lika osäker som första delen. Skördarens klassningsfel finns alltid kvar, ett per stock.
- **Fördelning, S2.** Mer levererat än lagret räcker till är oftast en del av beståndet som skördardatan ännu inte
  visar. En dragning är därför en slumpad del av arbetsorderns skörd, med skördeblock som för S1. Hur stor del som
  antas stå kvar anger `pool_remaining_share`.
- **Fördelning, S3.** En slumpad annan arbetsorder, och sedan en slumpad del av dess skörd, som om den levererat.
  Bestånd skiljer sig genom att hela fördelningen förskjuts, så närliggande klasser samvarierar, vilket en Dirichlet
  inte kan uttrycka. Givarens vikt är volymen, gånger 16 vid samma destination, gånger 4 vid samma grupp, och en
  normalfördelad vikt runt den medeldiameter som arbetsorderns andra sortiment förutsäger. Bandbredden är
  förutsägelsens skattade fel, minst `donor_sibling_cm`. En fast, smalare bandbredd gav nästan samma skattning men för
  snäva intervall, eftersom givarna då liknade förutsägelsen mer än det saknade beståndet gör. Med färre än
  `pool_min_donors` arbetsordrar används Dirichlet.
- **Diameterbias.** Skördaren på en arbetsorder mäter systematiskt högt eller lågt, vilket flyttar volym till
  grannklasser.
- **Volym.** Per leverans `unit_cv / sqrt(antal_matenheter)`, plus ett fel per metod som delas av alla månadens
  leveranser.

Två spridningar redovisas. `std_fordelning` håller volymen fast och är osäkerheten i fakturans värde.
`std`, `p05` och `p95` lägger till volymfelet och beskriver vad som fysiskt levererades.

## Parametrar och källor

| Parameter | Standard | Grund |
|---|---|---|
| `harvester_bias` | 0,009 | Biometria 2025: skördaren överskattar 0,9 % under bark (1,2 % på bark), tabell 6–7 |
| `handling_loss` | 0,01 | Antagande. Biometria 2026 räknar i ett exempel med 1 % färre stockar framme |
| `coverage_tolerance` | 0,03 | Antagande, av samma storleksordning som stamvisa mätfel |
| `design_effect` | 40 | Inställd mot simulatorn. Var 20 innan simulatorn fick säsongens lagringstider |
| `cluster_volume` | 2400 | Inställd mot simulatorn: hur mycket volym som rör sig tillsammans |
| `mixture_min_concentration` | 0,25 | Inställd mot simulatorn |
| `donor_destination_weight` | 16 | Inställd mot simulatorn |
| `donor_group_weight` | 4 | Inställd mot simulatorn |
| `donor_sibling_cm` | 1,5 | Inställd mot simulatorn. Minsta bandbredd, annars skattas den ur data |
| `pool_remaining_share` | 0,5 | Antagande: en arbetsorder utan skördardata levererar halva skörden samma månad |
| `stock_block_days` | 5 | Antagande |
| `min_forwarding_days` | 2 | Antagande |
| `intervals` | på | Av ger profilen enkel: samma faktura och matriser, utan Monte Carlo-intervall |
| `overlap_fifo` | på | Klättring: prisfel 11,9 → 10,9 kr/m3fub i snitt över klättringens scenarier. Bygger på antagandet att lastbilar som börjar under skörden tar avläggen i skördeordning |
| `pool_concentration_default` | 20 | Antagande |
| `pool_min_donors` | 5 | Antagande |
| `diameter_bias_sd_mm` | 2 | Antagande |
| `stockmatning` | `unit_cv` 0,043 | Biometria 2025, tabell 1. Systematiskt fel härlett ur KI ±0,1 % |
| `travmatning` | `unit_cv` 0,051 | Biometria 2025, tabell 1, sågbara. Systematiskt fel härlett ur KI ±0,3 % |
| `vagning` | `unit_cv` 0,069 | Antagande: nivån för travmätt massaved i tabell 1, inte en vägningssiffra |
| `skordarmatning` | `unit_cv` 0,050 | Biometria 2025, tabell 7, stamvis under bark. Systematiskt fel antaget |
| `okand` | `unit_cv` 0,080 | Antagande, medvetet försiktigt |

## Utvärdering

`treedist backtest` bygger ett virkesflöde med känt facit: bestånd, stockar, avlägg, leveranskampanjer och lastbilar.
Metoden får bara det verkliga system skulle se. [Underlaget](simuleringsunderlag.md) beskriver vad simulatorn bygger på.
Resultat, tre metoder och jämförelse med forskningen finns i [metodjämförelsen](metodjamforelse.md).

I korthet, i basscenariot: 5,5 % av volymen hamnar i fel cell mot 17,1 % om man bara använder månadens skörd, och
medelpriset fel med 8,6 mot 41,7 kr/m3fub. Över tolv månader är prisfelet 4,8 kr/m3fub. Värdeintervallet täcker 87–93 %
mot nominellt 90 %. Simulatorns lagringstider följer säsongen, se [antaganden](antaganden.md).

Eftersom leveranser saknar diameter och längd finns inget direkt facit i verklig drift. Det som går att följa upp är
volymbalansen när arbetsordrar avslutas. Inget av detta är prövat på verkliga data.

## Medvetna begränsningar

- **Varje skördarrad hör till en månad.** Tabellerna i dataplattformen antas sakna dubbletter, och månadens uttag ska
  bara innehålla rader som inte varit med tidigare. Ett uttag av hela tabellen varje månad skulle dubbelräknas.
- **Kallstart.** Virke skördat före första körda månaden finns inte i liggaren och blir S3 eller S4. Kör in historiska
  månader först.
- **Omklassat virke antas vara ett slumpmässigt urval av lagret.** I verkligheten är det troligen de klenaste eller
  sämsta stockarna som klassas ned, så timmerfakturan blir något för klen och den nedklassade volymen för grov. Utan
  `producerat_handelssortiment` syns omklassning bara som över- och underskott per sortiment i `avstamning_ao.csv`.
- **Kvalitetsklasser ingår inte.** En produkt är sortiment, diameter och längd. Kvalitet måste ligga i sortimentet.
- **Bara m3fub och inga krediterade leveranser.** Negativa leveransrader avvisas. Moms ingår inte i beloppen.
- **Korrigeringar räknas i bruttoskala.** Skillnaden mot netto är liten och volymen på korrigeringsrader går jämnt ut.

## Källor

- [Biometria, Kvalitetsrapport 2025](https://www.biometria.se/media/zqzgry3k/kvalitetsrapport-biometria-2025-low.pdf)
- [Biometria, Tolkning av hpr i VIOL 3 (2025)](https://www.biometria.se/media/g4zbgb1j/biometria-regler-vid-tolkning-av-hpr-viol3-20251020.pdf)
- [Biometria, Fältdata för ersättningsgrundande virkesmätning (2026)](https://www.biometria.se/media/4ulozgo3/faeltdata-foer-ersaettningsgrundande-virkesmaetning.pdf)
- [Biometria, Krav och åtgärdsnivåer (2025)](https://www.biometria.se/media/r4wf21el/biometrias-krav-och-aatgaerdsnivaaer-antagna-_251211.pdf)
- [Mellanskog, Virkesprislista november 2025](https://www.mellanskog.se/wp-content/uploads/2025/11/virkesprislista-malar-251119.pdf)
- [Lag (2014:1005) om virkesmätning](https://data.riksdagen.se/dokument/sfs-2014-1005.html)
- [Skogsstyrelsens föreskrifter om virkesmätning, SKSFS 2014:11](https://wwwprod.skogsstyrelsen.se/globalassets/lag-och-tillsyn/foreskrifter-efter-amne/virkesmatning/sksfs-2014-11--skogsstyrelsens-foreskrifter-om-virkesmatning.pdf)
