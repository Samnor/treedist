# Underlag för simulerad data

Vad årsredovisningar från Sveaskog, SCA och Holmen (alla 2025) och Biometrias dokument säger om hur data borde se ut,
jämfört med vad `simulate.py` gör idag. Årsredovisningarna är lästa riktat, med fokus på volymer, flöden och logistik.

Märkning: **Källa** är en uppgift ur dokumenten. **Härlett** är min beräkning ur sådana uppgifter. Årsredovisningar
beskriver flöden per år och bolag. De säger ingenting om enskilda arbetsorder, stockar eller lagringstider.

## Skala

| Aktör | Uppgift | Månadsvolym sågtimmer | Typ |
|---|---|---|---|
| Sveaskog, snittkund | 2 895 tusen m3fub sågtimmer till cirka 50 sågverk | cirka 4 800 m3fub | Härlett |
| Holmen, snittsågverk | 1 294 tusen m3 sågade produkter, 5 sågverk, cirka hälften av stocken blir produkt | cirka 43 000 m3fub | Härlett |
| SCA, snittsågverk | 2 122 tusen m3 sågade produkter, 5 sågverk, samma utbyte som Holmen antaget | cirka 71 000 m3fub | Härlett |
| Simulatorn | 10 arbetsordrar per månad | cirka 9 400 m3fub | Mätt i backtest |

Simulatorn motsvarar en medelstor extern kund, inte ett stort integrerat sågverk. Ett sådant är 5–8 gånger större.

Biometria mätte 36,6 miljoner m3fub sågtimmer 2025, av knappt 95 miljoner totalt.

## Sortimentsmix

| Bolag | Sågtimmer | Massaved | Biobränsle |
|---|---|---|---|
| Sveaskog, levererad volym | 37 % | 59 % | Resten |
| Holmen, schablon för avverkningen | 50 % | 45 % | 5 % |

Sveaskog får mest sågtimmer ur föryngringsavverkning, och gallring ger massaved, timmer och biobränsle. Det talar för
två typer av arbetsordrar med olika fördelningar, inte en gemensam. SCA nämner dessutom att contorta växer och att
sågverk växlar mellan trädslag efter tillgång.

## Varifrån virket kommer

Det här är den viktigaste skillnaden mot simulatorn, där nästan allt levererat virke har skördardata.

- **Holmen** förädlar ungefär dubbelt så mycket virke som bolaget avverkar i egen skog.
- **Sveaskog** levererade 7 756 tusen m3fub: 60 % egen skog, 13 % köpt från privata skogsägare, 3 % import och övriga
  externa köp. Återstående 23 % framgår inte av det jag läst.
- **SCA** täcker ungefär halva råvarubehovet med egen skog och flis från egna sågverk, och byter virke med andra
  skogsbolag för att korta transporterna.

Andelen köpt och bytt virke är därför stor. Om skördardata saknas för det virket hamnar volymen i S3 och andelen blir
betydligt större än de 1–5 % som backtesten visar.

## Säsong och lagring

Sveaskogs sågtimmerleveranser 2025 per kvartal: 793, 804, 528 och 771 tusen m3fub. Tredje kvartalet ligger 27 % under
snittet, och 2026 upprepas mönstret med 550 tusen. Orsaken anges inte i de rapporter jag läst.

Lagringstiden är inte heller konstant:

- Mellanskogs leveransbestämmelser kräver att sågtimmer som fällts utanför vintern anmäls vid bilväg inom två veckor på
  grund av blånad, medan vinterfällt timmer får vänta till 15 april.
- Tjällossning sätter ned vägarnas bärighet och begränsar transporterna (Skogforsk 2023).
- Skogsbolagen flyttar avverkning mellan år för att möta marknaden (Holmen).

Simulatorn har samma fördröjning, median 25 dagar, hela året. Ingen källa ger själva fördelningen av lagringstider.

## Störningar

Stormen Johannes i slutet av december 2025 fällde drygt 300 000 m3fub på Holmens mark, cirka 10 % av årsavverkningen,
och upp till 300 000 m3 hos Sveaskog. SCA anger 8–10 miljoner m3fo nationellt. Sveaskog beskriver stormvirket som
spritt och dyrt att avverka. Sådana händelser ger en plötslig puls av virke med annan fördelning och annan lagring,
vilket simulatorn saknar.

## Geografi och transport

| | Norra | Mellan | Södra | Källa |
|---|---|---|---|---|
| Medelstam under bark, m3fub | 0,21 | 0,32 | 0,37 | Biometria 2025, tabell 7 |

Timmer kördes i snitt 92,7 km år 2020, från 83 km i Götaland till 107 km i Norrland. SCA kör virke till järnvägsterminal
när avståndet överstiger cirka 100 km, vilket ger ett lagersteg till. Lastbilarna har normalt 64 tons bruttovikt, och
70–74 ton ökar.

Skogforsks siffror ger 0,90 ton per m3fub. Med antagen nyttolast 40 ton blir ett lass cirka 45 m3fub (härlett),
mot 35 i simulatorn.

## Mätning vid leverans

**Stockmätning dominerar sågtimmer.** Skogforsk skriver att en stor majoritet av sågtimret stockmäts i mätramar. Andelen
anges inte, men simulatorns 30 % är för lågt.

**Dimensioner vid leverans finns inte i vårt fall.** Biometrias stocklista innehåller diameter och längd per stock, men
de uppgifterna ingår inte i projektets indata. Fördelningen måste därför skattas ur skördarmätningarna. Metoden kan inte
heller kalibreras mot stocknotor, utan bara mot sådant som går att räkna ut ur skördardata och leveransvolymer.

**Säkerheten har redan en officiell skala.** Varje mätt kvantitet får en måttslagskvalitet:

| Kvalitet | Användning | Får värdeberäknas |
|---|---|---|
| 1 | Råvaruredovisning enligt virkesmätningslagen | Ja |
| 2 | Råvaruredovisning mellan företag | Ja |
| 3 | Transportredovisning | Nej |
| 4 | Statistik | Nej |

Det ligger nära projektets formulering "mätningar av varierande säkerhet". `treedist` använder idag bara mätmetod och
kan alltså fakturera en volym som inte får värdeberäknas.

**Volym i två led.** Chauffören anger en uppskattad bruttovolym vid lastning. Den är inte ersättningsgrundande och
används för lager och statistik. Mätningen på mätplatsen ger brutto och netto. Ersättningsgrundande resultat skickas som
`MeasuringTicket`, övrigt som `ArrivalTicket`. Delar av en leverans kan mätningsvägras, och vrak dras från volymen.
Simulatorn har en enda volym per leverans.

**En leverans är inte en lastbil.** Ett leveranstillfälle är allt som kommer på samma lastbil, och kan vara flera
leveranser (samlast). Leveransinnehåll skapas per avtalsobjekt, handelssortiment och startplats. Lass och travar kan
delas med viktfördelning. Simulatorn antar ett lass per leverans.

**Biometrias begrepp är avtalsobjekt.** Det är nyckeln i både hpr-filer och leveransavisering. Hur det förhåller sig
till *arbetsorder* behöver stämmas av.

**Skördaren mäter lika bra som mätramen.** Spridningen i toppdiameter var 2,4–9,6 mm och i längd 0,8–1,8 cm mellan 23
mätramar. De flesta av 31 undersökta skördare mätte lika bra eller bättre. Skördarens klassning är alltså ett gott
underlag: felet i månadens matris kommer främst av att vi inte vet vilket virke som åkte, inte av mätningen.

**Klassning.** Klasserna i simulatorn stämmer med prislistorna: längder 340–550 cm i steg om 30, och prisklasser
14/18/24/28 cm. Däremot betalas också 10–13,9 cm, som simulatorn saknar, och SCA arbetar för att sänka minsta
sågbara diameter. Kvalitetsklasser saknas helt, trots att de styr priset på tall.

## Så används underlaget i simulatorn

| Inbyggt | Grund |
|---|---|
| 90 % stockmätt | Stor majoritet enligt Skogforsk, exakt andel antagen |
| 10 % virke utan skördardata, 30 % som scenario | Stor andel köpt och bytt virke, andel antagen |
| Säsong i lagring och leveranstakt | Sveaskogs kvartal, Mellanskogs regler, styrka antagen |
| Slutavverkning och gallring | Sveaskog, Holmen |
| Regioner | Medelstam 0,21–0,37 |
| 45 m3fub per lass | Härlett |
| Brutto och netto | Biometria, kassationsandel antagen |
| 10–13 cm | Prislistor |
| Skörd och leverans som kampanjer om 1–3 veckor, avlägg för avlägg | Projektets egna data |
| 3 destinationer, klent virke till klensågverk, 5 % omdirigerat | Planerad destination i projektets data, styrka antagen |
| Skördarens volym räknas ur dess egen diameter, svinn varierar | Biometria, spridning antagen |

Ej inbyggt: samlast, stormpuls, terminaler och kvalitetsklasser.

## Saknas fortfarande

- Fördelningen av lagringstid per arbetsorder. Finns troligen i egna system eller i Biometrias statistik.
- Faktiska diameter- och längdfördelningar per region. Prislistor ger klasser, inte volymer.
- Storlek på arbetsordrar.
- Biometrias *Sortimentsstrukturen i VIOL 3*, *Mätbesked i VIOL 3* och *Handbok Kollektiv* gav 404, och *Nationella
  mätningsbestämmelser* är inte lästa. Kollektiv är relevant vid vägning, där stickprov kan ändra volymen i efterhand.

## Källor

Årsredovisningar och rapporter:

- [Sveaskog, Annual and Sustainability Report 2025](https://www.sveaskog.se/globalassets/trycksaker/finansiella-rapporter/annual-and-sustainability-report-2025.pdf)
- [Sveaskog, Bokslutskommuniké 2025](https://mb.cision.com/Main/1495/4302592/3916398.pdf)
- [Sveaskog, Delårsrapport januari–mars 2025](https://www.sveaskog.se/globalassets/trycksaker/finansiella-rapporter/delarsrapport-januari-mars-2025.pdf)
- [Sveaskog, Delårsrapport januari–juni 2025](https://www.sveaskog.se/globalassets/trycksaker/finansiella-rapporter/delarsrapport-januari-juni-2025.pdf)
- [Sveaskog, Delårsrapport januari–september 2026](https://www.sveaskog.se/globalassets/trycksaker/finansiella-rapporter/delarsrapport-januari-september-2026.pdf)
- [SCA, Annual Report 2025](https://www.sca.com/siteassets/investors/reports-and-presentations/annual-reports/2025/sca-annual-report-2025.pdf)
- [Holmen, Annual Report 2025](https://mb.cision.com/Main/308/4318038/3970154.pdf)

Biometria:

- [Kvalitetsrapport 2025](https://www.biometria.se/media/zqzgry3k/kvalitetsrapport-biometria-2025-low.pdf)
- [Principer för mätning och redovisning av kvantiteter i VIOL 3](https://biometria.se/media/ke0dk42k/principer-foer-maetning-och-redovisning-av-kvantiteter-i-viol-3-40.pdf)
- [Lathund stockmätning i mätplatsstödet](https://www.biometria.se/media/fl5fbjvf/lathund-stockmaetning-maetplatsstoedet-10.pdf)
- [Instruktion mätplatsstöd](https://www.biometria.se/media/4szpr50l/instruktion_maetplatsstoed_-2021-11-19.pdf)
- [Best practice leveransavisering](https://www.biometria.se/media/taejwt5a/best-practice-leveransavisering.pdf)
- [Best practice digitala kedjan](https://biometria.se/media/cbkdivzj/best-practice-digitala-kedjan-20.pdf)
- [Tjänstespecifikation mätning](https://www.biometria.se/media/3m1pftkx/tjaenstespecifikation-maetning-viol3_11.pdf)
- [Måttstocken](https://biometria.se/media/twbpepkx/maattstocken-2024.pdf)

Övrigt:

- [Skogforsk, Arbetsrapport 1093-2021, mätramar i sågverk](https://www.skogforsk.se/contentassets/7e7c5a97ae7b4e06b22eb755523e529c/arbetsrapport-1093-2021.pdf)
- [Skogforsk, Arbetsrapport 1142-2023, skogsbrukets vägtransporter 2020](https://www.skogforsk.se/contentassets/2b9ecb7389bd495dbbe4724fd9793d55/arbetsrapport-1142-2023-skogsbrukets-vagtransporter-2020.pdf)
- [Mellanskog, Allmänna leveransbestämmelser 2025](https://www.mellanskog.se/wp-content/uploads/2025/08/allmanna-leveransbestammelser.pdf)
- [Mellanskog, Virkesprislista november 2025](https://www.mellanskog.se/wp-content/uploads/2025/11/virkesprislista-malar-251119.pdf)
