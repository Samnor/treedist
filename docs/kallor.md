# Källor

Det här är källorna bakom projektets antaganden, ordnade efter ämne. Varje rad säger vad källan visar och var den används,
så att samma uppgift kan hämtas härifrån i stället för att letas fram igen. Siffrorna är de som lästs ur källan. Står
**härlett**, är talet en egen beräkning ur källan. Lägg till nya källor här när de används i en text.

Senast genomgången 2026-11-08, VIOL 3-termerna 2026-11-17.

## VIOL 3: kontraktets termer och vad de vilar på

Kontraktets tabeller och kolumner (`treedist kontrakt`) har VIOL 3:s termer. Här är var varje definition kommer
ifrån, med dokumentets version och avsnitt. Allt lästes 2026-11-17. Dokumenten är Biometrias och får inte spridas, så
repot sparar länken, versionen och vad som står där, inte filerna.

| I treedist | Källa | Vad källan säger |
|---|---|---|
| Bara VIOL 3 | [Komprimerad info VIOL 3 transport](https://biometria.se/media/jjkc0pat/komprimerad-info-viol-3-transport.pdf), 2024-10-07 | Transport och inmätning kunde börja i VIOL 3 vid Go Live 2025-05-02. VIOL 2 tog emot leveranser till 2025-10-17 och stängdes för inmätning 2025-10-31. Data mellan maj och oktober 2025 kan alltså vara från båda |
| `avtalsobjekt` | [Handbok Avtalsobjekt](https://www.biometria.se/media/j5rjurag/handbok-avtalsobjekt.pdf) 3.0, 2021-11-17, avsnitt 2 | Den sammanhållande identiteten för råvaru- och tjänsteaffärerna, bärare för transport, produktion och mätning. Motsvarar ett geografiskt avgränsat område, till exempel en avverkningstrakt |
| `avtalsobjekt` i produktionen | [Tolkning av hpr i VIOL 3](https://www.biometria.se/media/g4zbgb1j/biometria-regler-vid-tolkning-av-hpr-viol3-20251020.pdf) 2.0, 2025-10-20, avsnitt 7.1 | `ObjectDefinition ContractNumber`. Biometria lagrar de 8 första siffrorna, och Sender XC kontrollerar att avtalsobjektet finns i VIOL. Avtalsobjekt och produktionsunderlag har samma identitet |
| Flera avtalsobjekt per kontrakt | [Helhetslösning produktion](https://www.biometria.se/media/ffmfrvts/helhetsloesning-produktion-jan-2023.pdf), 2023-01-24, avsnittet om produktionens del i helheten | Det kan finnas flera avtalsobjekt på varje förstaledskontrakt |
| Kolumnnamnen i `matning` | [Beskrivning av värde- och urvalstermer råvara](https://biometria.se/media/5m2fc5as/beskrivning-av-vaerde-och-urvalstermer-raavara-60.pdf) 6.0, 2024-10-03, avsnitt 3.2 | Termer på leveransnivå: Avtalsobjekt, Avverkningsform, Handelssortiment, Producerat handelssortiment, Producerat för mottagningsplats, Mottagningsplats, Leveransdatum, Mätdatum, Mätmetod och Sitetyp. Listan gäller pris- och urvalsvillkor; den säger inte att varje leverans har alla |
| `anskaffningsform` | Beskrivning av värde- och urvalstermer råvara, avsnitt 3.2 | Anskaffningsform är en term på leveransnivå. treedist visar den som källan ger den och läser den inte i metoden |
| `leveransnummer`, `matdatum` | [Så här läser du ditt mätbesked i VIOL 3](https://biometria.se/media/3cajdnjf/saa-haer-laeser-du-ditt-maetbesked-version-10.pdf) 1.0, 2024-08-23, avsnitt 3–4 | Mätbeskedet gäller en period av mätdatum och listar de ingående leveranserna, med leveransnummer, per mätdatum. En korrigering visar förändringen mot det tidigare mätbeskedet och dess leveransnummer |
| `producerat_for_mottagningsplats` i produktionen | Tolkning av hpr i VIOL 3, avsnitt 6.4 | Den tänkta mottagningsplatsen för det producerade handelssortimentet, `ProductDestination.BusinessID`, och ett brytbegrepp för produktionsresultatet. **Inte obligatorisk** i hpr: den kan utelämnas. treedist kräver den ändå |
| Producerat sortiment och producerat för hör ihop | Helhetslösning produktion, avsnitten om produktionsunderlag och destinering | Kombinationen producerat handelssortiment och producerat för mottagningsplats ska matcha produktionsunderlaget. Destineringen görs per handelssortiment, och ett destinerat sortiment bär paret producerat sortiment och producerat för mottagningsplats, också när det går till en annan mottagare |
| `avverkningsdatum` | Tolkning av hpr i VIOL 3, avsnitt 8 och 8.12; Helhetslösning produktion, "Nytt data i VIOL 3" | Avverkningstidpunkt per stam, `Stem.HarvestDate`, nytt i VIOL 3. Uppgifterna per stam lagras **om de förekommer**, så den är inte garanterad. treedist kräver den ändå |
| StanForD 2010 | Tolkning av hpr i VIOL 3, avsnitt 3 | Biometria hanterar version 3.0–3.6 och 4.1 |
| Slutsignaler | Tolkning av hpr i VIOL 3, avsnitt 7.7; [Tolkning av fpr i VIOL 3](https://www.biometria.se/media/pilenrq3/biometria-regler-vid-tolkning-av-fpr-viol3-20251020.pdf) 2.0, 2025-10-20, avsnitt 6.7 och 8.5; Helhetslösning produktion | Skördaren: `EndDate` ger Slutskördat på avtalsobjektet. Skotaren: Slutskotat på avtalsobjektet och per handelssortiment och avlägg. Ingen av dem säger att transporten är klar |
| `transport_avslutad` | Handbok Avtalsobjekt, steg 12 | Avtalsobjektet avslutas när samtliga leveranser kommit fram och mätts in korrekt; då skapas mätbesked och en slutgiltig värdeberäkning. treedist frågar bara om transporten är klar, men ett avslutat avtalsobjekt är det också |
| `brutto_m3fub` och `volym_m3fub` | Instruktion mätplatsstöd och Tjänstespecifikation mätning, under Mätning vid industrin | Mätplatsen ger brutto och netto |
| En brutto- och en nettovolym per leverans | [White paper Principer för mätningsflöden VIOL 3](https://www.biometria.se/media/ewvnofoa/white-paper-principer-foer-maetningsfloeden-viol-3-20230303.pdf) 1.0, 2023-03-03, avsnitt 3.3 | Det redovisas bara en brutto- och en nettovolym i m3f per leverans och dokumenttyp |
| Produktion utan skördarfil | Helhetslösning produktion, avsnitten om Rapp och produktionsresultat | Produktion kan rapporteras i Rapp, som bara hanterar handelssortiment. Resultatet per stam skapas då inte. *Producerat för mottagningsplats* är möjlig, inte nödvändig, på produktionsunderlaget |
| Sena rättelser | Komprimerad info VIOL 3 transport; [Handbok Mätbeskedsklienten](https://biometria.se/media/jcmh2bq5/handbok_maetbeskedsklienten_viol-3_21.pdf) 2.1, 2025-03-24 | VIOL 2-transaktioner gick att rätta till 2026-01-31, tre månader efter att inmätningen stängdes. Händelsestyrda mätbesked kan vänta 1–365 dagar efter en ny eller korrigerad händelse |

Vilka av treedists krav som håller mot dessa källor och mot datan står i [krav.md](krav.md). Prövat mot riktig data
2026-11-17, se [stickproven](antaganden.md#stickprov-ur-verklig-data): varje leverans har
producerat handelssortiment och producerat för mottagningsplats, en korrigering har leveransnumret för lasset den
vänder, och avverkningsdatum finns på varje stock. Producerat för mottagningsplats saknas däremot på ungefär var
sjätte stock i produktionen. Sedan 2026-11-18 läses den som tom där: virket är avtalsobjektets, och dess lass tar
det när deras egna lager är slut ([metod.md](metod.md)).

Redovisningsdatum, dagen en rad redovisades, står inte i något av dokumenten ovan: varken mätbeskedets beskrivning
eller Principer för mätning och redovisning av kvantiteter nämner ordet. I den verkliga datan är det ändå det enda
datum som skiljer en korrigering från lasset den vänder, så källan väljer månadens rader på det.

## Lag och mätningsregler

- [Lag (2014:1005) om virkesmätning](https://data.riksdagen.se/dokument/sfs-2014-1005.html). Grunden för den
  ersättningsgrundande mätningen. Används i [metod.md](metod.md).
- [Skogsstyrelsens föreskrifter om virkesmätning, SKSFS 2014:11](https://wwwprod.skogsstyrelsen.se/globalassets/lag-och-tillsyn/foreskrifter-efter-amne/virkesmatning/sksfs-2014-11--skogsstyrelsens-foreskrifter-om-virkesmatning.pdf).
  Föreskrifterna till lagen. Används i [metod.md](metod.md).
- [Biometria, Nationella mätningsbestämmelser](https://www.biometria.se/publikationer/maetningsinstruktioner/maetningsbestaemmelser/nationella-maetningsbestaemmelser/).
  Sidan med de gällande dokumenten om stockmätning, travmätning och kvalitetsbestämning. Inte läst i sin helhet.

## Mätning vid industrin

- [Biometria, Kvalitetsrapport 2025](https://www.biometria.se/media/zqzgry3k/kvalitetsrapport-biometria-2025-low.pdf).
  - Tabell 1, mätfel per lass:
    - stockmätning `unit_cv` 0,043, med konfidensintervall ±0,1 %
    - travmätt sågbart 0,051, med konfidensintervall ±0,3 %
    - travmätt massaved ungefär 0,069
  - Tabell 6–7: skördaren överskattar volymen 0,9 % under bark och 1,2 % på bark.
  - Tabell 7: medelstam 0,21, 0,32 och 0,37 m3fub i norra, mellersta och södra Sverige.
  - Används i [metod.md](metod.md) (`harvester_bias` och volymfelen) och i [simuleringsunderlag.md](simuleringsunderlag.md).
- [Biometria, Krav och åtgärdsnivåer, mätningskvalitet industri (2025)](https://www.biometria.se/media/r4wf21el/biometrias-krav-och-aatgaerdsnivaaer-antagna-_251211.pdf).
  Krav på noggrannhet vid stock- och travmätning, och när kontrollmätning kräver avverkningsform. Används i [metod.md](metod.md).
- [Biometria, Simulera stockdatainsändning (2021)](https://www.biometria.se/media/tsclkavv/instruktion-simulera-stockdatainsaendning_2021-01-29.pdf).
  - Stockmätningen ger en stocklista per stock.
  - Diametern korrigeras för bark och mätramens systematiska fel. Korrektionen sätts per mätplats, utrustning,
    trädslag och barktyp.
  - I VIOL 3 är sågtimrets produkter kvalitetsklasser, tall 0110–0114 och gran 0120–0122, plus vrak.
  - Vrak ingår i bruttot.
  - Omräkningen från m3to till m3f följer avtalsobjektets regelverk.
  - Används i [antaganden.md](antaganden.md).
- [Biometria, Lathund stockmätning i mätplatsstödet](https://www.biometria.se/media/fl5fbjvf/lathund-stockmaetning-maetplatsstoedet-10.pdf).
  Stocklistan har barktyp, produkt, trädslag, kvalitet, längd, diameter och avdrag per stock. Används i
  [simuleringsunderlag.md](simuleringsunderlag.md).
- [Biometria, Mätning av stockars fastvolym (2015)](https://www.biometria.se/media/ekub3gwo/maetning-av-stockars-fastvolym-dec-2015.pdf).
  - Jämför sätt att räkna fastvolym: toppcylindervolym gånger ett omräkningstal ur en matris efter toppdiameter och
    längd, topp-rot-mätning, mittmätning och sektionsmätning.
  - Rotstockarnas rotmått flyttades från 10 till 50 cm från rotänden.
  - Avsmalningen är i snitt 8,8 % av mittdiametern för tall och 9,3 % för gran.
  - Används i [antaganden.md](antaganden.md).
- [Biometria, Principer för mätning och redovisning av kvantiteter i VIOL 3](https://biometria.se/media/ke0dk42k/principer-foer-maetning-och-redovisning-av-kvantiteter-i-viol-3-40.pdf).
  - Måttslagskvalitet 1–4. Bara kvalitet 1 och 2 får värdeberäknas.
  - En mätning kan ge flera måttslag, till exempel m3f från stockmätningen och en beräknad m3to.
  - Används i [simuleringsunderlag.md](simuleringsunderlag.md).
- Biometrias dokument om flödet från lastning till mätplats. De visar tillsammans:
  - Chauffören anger en uppskattad bruttovolym, som inte är ersättningsgrundande.
  - Mätplatsen ger brutto och netto, som `MeasuringTicket` eller `ArrivalTicket`.
  - Delar av en leverans kan mätningsvägras.
  - Samlast förekommer, och leveransinnehållet skapas per avtalsobjekt, handelssortiment och startplats.

  Dokumenten:
  - [Instruktion mätplatsstöd](https://www.biometria.se/media/4szpr50l/instruktion_maetplatsstoed_-2021-11-19.pdf)
  - [Best practice leveransavisering](https://www.biometria.se/media/taejwt5a/best-practice-leveransavisering.pdf)
  - [Best practice digitala kedjan](https://biometria.se/media/cbkdivzj/best-practice-digitala-kedjan-20.pdf)
  - [Tjänstespecifikation mätning](https://www.biometria.se/media/3m1pftkx/tjaenstespecifikation-maetning-viol3_11.pdf)

  Används i [simuleringsunderlag.md](simuleringsunderlag.md).
- [Biometria, Måttstocken 2024](https://biometria.se/media/twbpepkx/maattstocken-2024.pdf). Biometrias årliga
  statistik över mätta volymer. Används i [simuleringsunderlag.md](simuleringsunderlag.md).
- [Skogforsk, Arbetsrapport 1093-2021, mätramar i sågverk](https://www.skogforsk.se/contentassets/7e7c5a97ae7b4e06b22eb755523e529c/arbetsrapport-1093-2021.pdf).
  - Studien omfattar 23 mätramar på 19 sågverk.
  - Spridningen i toppdiameter under bark var 2,4–9,6 mm, och i längd 0,8–1,8 cm.
  - Nyare mätramar hade mindre spridning.
  - En jämförelse med 31 kvalitetssäkrade skördare i södra Sverige finns med.
  - Används i [simuleringsunderlag.md](simuleringsunderlag.md), [antaganden.md](antaganden.md) och
    [metodjamforelse.md](metodjamforelse.md).
- [Skogforsk, Arbetsrapport 1195-2024, kontrollmetoder vid stockmätning](https://www.skogforsk.se/cd_20240319163017/contentassets/abf9147873c84885a4fd625cd75740ee/1195-2024-kontrollmetoder-for-diameter-langd-och-volym-vid-stockmatning-1.pdf).
  Hur diameter, längd och volym i mätram kontrolleras. Inte använd i någon text än.

## Skördare och skotare

- [Biometria, Tolkning av hpr i VIOL 3 (2025)](https://www.biometria.se/media/g4zbgb1j/biometria-regler-vid-tolkning-av-hpr-viol3-20251020.pdf).
  - Per stock finns toppdiameter under bark i mm, längd i cm och volym m3sub ur filen. Toppmätt volym räknas ur
    toppdiameter och längd.
  - Klassen är närmast underliggande klassbotten i skördarens produktdefinition.
  - Stamkoordinaten räknas om till SWEREF 99 TM.
  - Biometria rekommenderar delavslutade filer. Dubblettstammar sorteras bort.
  - Avsnitt 6.4: *Producerat för mottagningsplats* tas ur produktdefinitionen och delar produktionsresultatet. Den är
    frivillig. Se tabellen under VIOL 3 ovan.
  - Används i [metod.md](metod.md) och [antaganden.md](antaganden.md).
- [Biometria, Regler vid tolkning av hpr (äldre version)](https://www.biometria.se/media/vezp5bej/biometria-regler-vid-tolkning-av-hpr.pdf).
  hpr-filer kan skickas delavslutade under avverkningen. Används i [antaganden.md](antaganden.md).
- [Biometria, Fältdata för ersättningsgrundande virkesmätning (2026)](https://www.biometria.se/media/4ulozgo3/faeltdata-foer-ersaettningsgrundande-virkesmaetning.pdf).
  - Skotaren rapporterar uppskattad volym per lass.
  - Skotarföraren flyttar stockar som inte klarar kvalitetskraven från timmer till massaved, så kallad sortimentsvandring.
  - Lastbilen börjar ibland hämta innan allt är framkört.
  - Krök är den vanligaste orsaken till nedklassning eller vrak av sågtimmer.
  - Vid bedömning i fält hittas i snitt cirka 20 % av vraket.
  - Används i [antaganden.md](antaganden.md).
- [Biometria, Sortimentsstrukturen i VIOL 3 (2021)](https://www.biometria.se/media/yqgohtdj/beskrivning-av-sortimentstruktur-i-viol-3.pdf).
  - Handelssortimentet är det som destineras och mäts in. Produkterna är den lägsta nivån.
  - Virke kapat för en viss industri hålls isär på tre sätt: ett industrispecifikt handelssortiment, branschgemensamma
    sortiment efter grovlek (klenare och grövre), eller samma sortiment med *Producerat för mottagningsplats*.
  - Används i [antaganden.md](antaganden.md).
- [Staland 2001, SLU, styrning av kundanpassade timmerflöden](https://stud.epsilon.slu.se/4388/1/staland_j_120403.pdf).
  Skördarens och sågverkets stockfördelning stämde överens till 81 % för tall och 82 % för gran. Ett mått på hur
  mycket mätramens klasser skiljer från skördarens. Inte använt än.
- [Skogforsk, StanForD 2010](https://www.skogforsk.se/contentassets/f6ab99f3707a4670baeb987798c6e0b6/stanford-2010-svensk.pdf).
  Standarden för skogsmaskinernas filer: hpr från skördaren, fpr från skotaren och ett eget styrmeddelande till
  skotaren. En location är ett avlägg.
- [Skogforsk, Skotning](https://www.skogforsk.se/contentassets/e7f5fe3dd2204c8f906f17a9350b4d79/skotning.pdf).
  - fpr säger vilken produkt som ligger vid vilket avlägg och hur mycket.
  - Skördare och skotare kan rapportera olika sortiment för samma virke.
  - Skotarrapporteringen beskrivs som ofta manuell. Källan är från 2006.
  - Används i [antaganden.md](antaganden.md).
- [Karlsson 2011, SLU, skördarmätt medeldiameter mot stockmätning](https://stud.epsilon.slu.se/2912/1/Karlsson_A_20110623.pdf).
  - Skördarna mätte i snitt 1,6 mm större medeldiameter än stockmätningen.
  - Standardavvikelsen mellan partier var 8,5 mm, och enskilda partier skilde avsevärt.
  - Sortimentsvandringen var i vissa fall omfattande och gick normalt från timmer till massaved.
  - Används i [antaganden.md](antaganden.md).

## Prislistor och leveransbestämmelser

- [Mellanskog, Virkesprislista Mälardalen november 2025](https://www.mellanskog.se/wp-content/uploads/2025/11/virkesprislista-malar-251119.pdf)
  och [Mitt november 2025](https://www.mellanskog.se/wp-content/uploads/2025/11/virkesprislista-mitt-251119.pdf).
  - Sågtimmer betalas i kr/m3fub efter toppdiameter under bark, med klasserna 14, 18, 24 och 28 cm.
  - Tall har kvalitet 1, 2–3 och 4.
  - Stockar på 10–13,9 cm betalas lägre, och vrak betalas med 350 kr/m3fub.
  - Travmätt timmer har grövre klasser.
  - Används i [metod.md](metod.md) och [simuleringsunderlag.md](simuleringsunderlag.md), och i utvärderingens
    exempelprislista.
- [Mellanskog, Allmänna leveransbestämmelser 2025](https://www.mellanskog.se/wp-content/uploads/2025/08/allmanna-leveransbestammelser.pdf).
  Sågtimmer fällt utanför vintern ska anmälas vid bilväg inom två veckor, på grund av blånad. Vinterfällt timmer får
  vänta till 15 april. Används i [antaganden.md](antaganden.md) och [simuleringsunderlag.md](simuleringsunderlag.md).
- [Sveaskog, Prislista Svealand och södra Norrland 2025](https://www.sveaskog.se/globalassets/skogsagare/2025/7995-s2-svealand-och-sodra-norrland-251215.pdf).
  Sommarfällt timmer ska anmälas vid väg inom två veckor. Biometria utfärdar mätbestämmelserna. Används i
  [antaganden.md](antaganden.md).
- [Stora Enso, Prislista H821](https://storaensoskog.se/wordpress/wp-content/uploads/prislistor/H821-0C.pdf).
  - m3to är toppcylindervolym under bark, och m3fub är hela stockens volym under bark.
  - Minsta toppdiameter är 13 cm för normaltimmer och 11 cm för klentimmer, och största 50 cm.
  - Länken leder numera vidare till Stora Ensos startsida.
- Holmens marknadsprislista 2026. Sommarfällt timmer ska vara vid sågverket inom två veckor, och vinterfällt får ligga
  till 15 juni. Vrak ersätts i m3to. Länken finns i [antaganden.md](antaganden.md).

## Statistik

- [Skogsstyrelsen, Lager av sågtimmer, massaved och massaflis](https://www.skogsstyrelsen.se/statistik/avverkning/lager-av-sagtimmer-massaved-och-massaflis/).
  Sågtimmerlagret är 2,6–3,5 miljoner m3fub. Det ger 28–37 dagar från fällning till förbrukning (härlett). Används i
  [antaganden.md](antaganden.md).
- [Skogsstyrelsen, Avverkningen 2025](https://www.skogsstyrelsen.se/nyhetslista/avverkningen-fortsatte-att-minska-2025/).
  Knappt 34 miljoner m3fub avverkat per år, som antaganden.md jämför med sågtimmerlagret. Används i
  [antaganden.md](antaganden.md).
- [Skogsstyrelsen, Avverkningsanmälningar 2021](https://www.skogsstyrelsen.se/globalassets/statistik/statistikfaktablad/JO0314-statistikfaktablad-avverkningsanmalningar-2021.pdf).
  Medelanmälan för föryngringsavverkning var 3,8 ha. Används i [antaganden.md](antaganden.md).
- [Skogforsk, Arbetsrapport 1142-2023, skogsbrukets vägtransporter 2020](https://www.skogforsk.se/contentassets/2b9ecb7389bd495dbbe4724fd9793d55/arbetsrapport-1142-2023-skogsbrukets-vagtransporter-2020.pdf).
  - Timmer kördes i snitt 92,7 km, från 83 km i Götaland till 107 km i Norrland.
  - Bilarna har normalt 64 ton bruttovikt.
  - Skogforsks tal ger 0,90 ton per m3fub. Med 40 ton last blir ett lass cirka 45 m3fub (härlett).
  - Tjällossningen begränsar transporterna.
  - Används i [simuleringsunderlag.md](simuleringsunderlag.md).
- [Skogforsk, Arbetsrapport 1231-2025, kostnader, lönsamhet och lager](https://www.skogforsk.se/cd_20250211113825/contentassets/b3d3919b3ac744fe82937338733fc85a/arbetsrapport-1231-2025-kostnader-intakter-lonsamhet-produktivitet-och-kvalitet-pa-utforda-atgarder-i-svenskt-skogsbruk.pdf).
  Lager och lagringstid i skogsbruket. Används i [antaganden.md](antaganden.md) vid beräkningen av tiden från fällning
  till förbrukning.

## Bolagens rapporter

De visar volymer, varifrån virket kommer, säsong och stormar. Används i [simuleringsunderlag.md](simuleringsunderlag.md).

- [Sveaskog, Annual and Sustainability Report 2025](https://www.sveaskog.se/globalassets/trycksaker/finansiella-rapporter/annual-and-sustainability-report-2025.pdf)
  - 7 756 tusen m3fub levererades.
  - 60 % kom från egen skog, 13 % var köpt från privata ägare och 3 % import.
- [Sveaskog, Bokslutskommuniké 2025](https://mb.cision.com/Main/1495/4302592/3916398.pdf) och delårsrapporterna för
  [januari–mars 2025](https://www.sveaskog.se/globalassets/trycksaker/finansiella-rapporter/delarsrapport-januari-mars-2025.pdf),
  [januari–juni 2025](https://www.sveaskog.se/globalassets/trycksaker/finansiella-rapporter/delarsrapport-januari-juni-2025.pdf)
  och [januari–september 2026](https://www.sveaskog.se/globalassets/trycksaker/finansiella-rapporter/delarsrapport-januari-september-2026.pdf).
  Sågtimmerleveranser per kvartal. Tredje kvartalet ligger 27 % under snittet.
- [SCA, Annual Report 2025](https://www.sca.com/siteassets/investors/reports-and-presentations/annual-reports/2025/sca-annual-report-2025.pdf)
  - Egen skog täcker ungefär halva råvarubehovet.
  - Virket går via järnvägsterminal över cirka 100 km.
  - Stormen Johannes fällde 8–10 miljoner m3fo nationellt.
- [Holmen, Annual Report 2025](https://mb.cision.com/Main/308/4318038/3970154.pdf)
  - Holmen förädlar ungefär dubbelt så mycket virke som bolaget avverkar i egen skog.
  - Stormen Johannes fällde drygt 300 000 m3fub på Holmens mark.

## Forskning om metoden

Används i [metodjamforelse.md](metodjamforelse.md).

- [Noordermeer, Ørka och Gobakken 2023, Silva Fennica](https://silvafennica.fi/article/23023). k-NN med laserdata och
  skördardata som referens, 49 bestånd. Felindex 0,13 för diameter och 0,10 för sågad volym.
- [Maltamo m.fl. 2019, Silva Fennica](https://www.silvafennica.fi/article/10075). Samma ansats, 47 bestånd, felindex
  under 0,2.
- [Malinen och Maltamo, International Journal of Forest Engineering](https://journals.lib.unb.ca/index.php/IJFE/article/download/30024/1882525273?inline=1).
  Skördardata passar bättre som referens än inventeringsdata.
- [Packalén och Maltamo 2008, Canadian Journal of Forest Research](https://next.sciencegate.app/document/10.1139/x08-037).
  Uppmätta fördelningar från närmaste grannar slår parametriska Weibullfördelningar.
- [Holappa Jonsson 2018, SLU, om hprImputation](https://stud.epsilon.slu.se/13767/). Skogforsks verktyg använder kMSN
  på lagrade skördardata för att förutsäga utfallet före avverkning.
- [Skogforsk, Arbetsrapport 981-2018](https://www.skogforsk.se/cd_20190114162446/contentassets/4a34a91c429f46b09a9f3abc5fcbc242/arbetsrapport-981-2018.pdf).
  Listad bland metodjämförelsens källor. Innehållet är inte sammanfattat här.
- [Dasymetrisk kartering, GIS&T Body of Knowledge](https://gistbok-ltb.ucgis.org/current/tag/show/30571). Geografins
  sätt att sprida en känd total med en hjälpvariabel.
- [Residence time distribution för spårning, PubMed](https://www.pubmed.gov/34822965/). Processindustrins sätt att
  följa material genom lager och blandning.

## Att hämta källorna

- Biometrias och Skogforsks PDF:er går att hämta med `curl -sSL -A "Mozilla/5.0"` och läsa med `pdftotext -layout`.
  Ett verktyg som bara tar emot text ser dem ofta som binärdata.
- Holmens prislistor svarar med en HTML-sida i stället för PDF:en när de hämtas utan webbläsare.
- Biometrias *Mätbesked i VIOL 3* (white paper, `wp-maetbesked-viol3.pdf`) och *Handbok Kollektiv* gav 404 vid sökning 2026-11. *Sortimentsstrukturen i
  VIOL 3* gav också 404 under det namnet, men finns under *Beskrivning av sortimentstruktur i VIOL 3*. *Handbok Kollektiv* är relevant för vägning, där stickprov kan ändra volymen i efterhand.
- Biometrias regler och prislistorna ändras. Kontrollera datumet på dokumentet innan en siffra återanvänds.
