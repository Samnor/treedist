# Går treedists krav att motivera med VIOL 3?

treedist stoppar månaden när en uppgift saknas, i stället för att gissa. Det här dokumentet prövar varje sådant krav
mot två slags källor: Biometrias dokument om VIOL 3, och svaren ur den verkliga datan från 2026-11-17. Varje påstående
har en hänvisning inom hakparentes. B-källorna är Biometrias dokument och D-källorna är svaren ur datan; båda listas
sist. Skrivet 2026-11-17, mot treedist med kontraktsversion 3.

## Slutsats

De flesta kraven håller. Två gör det inte, och två vilar bara på ett års data.

- **Kraven på mätningen håller alla**, i både dokumenten och datan: leveransnummer, de två sortimenten, de två
  mottagningsplatserna, datumen, brutto och netto, och att en korrigering bär numret på lasset den vänder.
- **Två krav på produktionen håller inte som stopp.** VIOL 3 gör *producerat för mottagningsplats* frivillig i hpr
  [B1 §6.4], och den saknas på ungefär var sjätte stock i datan [D1]. VIOL 3 tillåter också produktion som
  rapporteras utan skördarens fil [B2], men metoden stoppar ett lass som saknar skördardata. I datan har avverkat
  virke skördardata till 99,7 %, men 28 % av den levererade volymen är köpt, importerad eller från terminal och har
  ingen avverkning alls [D11].
- **Avverkningsdatum håller i datan men inte i dokumenten.** Ingen rad saknar det [D2], men VIOL 3 lagrar det bara om
  skördaren skickar det [B1 §8].
- **Två regler är våra egna och vilar på ett års data:** att månadens rader väljs på redovisningsdatum, och att
  liggaren börjar sex månader före första fakturan [D5].

## Hur ett krav bedöms

Ett krav som stoppar månaden är motiverat när tre saker gäller:

1. Uppgiften finns alltid: VIOL 3 garanterar den, eller datan visar att den aldrig saknas.
2. En gissning i dess ställe skulle ge fel siffror utan att det märks.
3. Den som får stoppet kan rätta källan.

Bedömningarna nedan är:

- **Håller**: stöd i både dokumenten och datan.
- **Håller i datan**: datan visar det, men VIOL 3 garanterar det inte. Kravet kan stå kvar, med vetskap om att det
  vilar på ett stickprov.
- **Håller inte**: VIOL 3 garanterar det inte och datan motsäger det, eller har inte prövat det.

## Kraven på produktionen

| Krav | Vad VIOL 3 säger | Vad datan visar | Bedömning |
|---|---|---|---|
| `avtalsobjekt`, samma id som i mätningen | Obligatoriskt för redovisningen. Biometria lagrar de åtta första siffrorna, och avtalsobjekt och produktionsunderlag har samma identitet [B1 §7.1] | Inte prövat: formen på id i de två källorna är inte jämförd | Håller i dokumenten |
| `producerat_handelssortiment` | Måste anges för att volymen ska godkännas mot produktionsunderlaget [B2] | Inte frågat | Håller i dokumenten |
| `producerat_for_mottagningsplats` | Frivillig i hpr: den kan utelämnas [B1 §6.4]. Frivillig också på produktionsunderlaget [B2] | Saknas på ungefär 17 % av stockarna mars–oktober 2026, 23 % i januari och 54 % i februari [D1] | **Håller inte** |
| `avverkningsdatum` | Tidpunkten per stam är ny i VIOL 3 [B2] och lagras om den förekommer i filen [B1 §8, §8.12] | Ingen rad saknar det. Ett avtalsobjekt har i snitt 8–13 olika avverkningsdagar [D2] | Håller i datan |
| Diameter- och längdklass, volym per rad | hpr ger toppdiameter, längd och volym per stock [B1]. Rapp hanterar bara handelssortiment, inte produkter [B2] | Datan har en rad per stock [D1] | Håller för hpr |

### Producerat för mottagningsplats håller inte som stopp

Kravet finns för att varje mottagningsplats ska ha sitt eget lager: ett lass tar bara virke som kapades för sitt
sågverk. Det är rätt tänkt när uppgiften finns, eftersom virke som kapats för en viss industri ska hållas isär
[B3 §3.2]. Men VIOL 3 gör uppgiften frivillig på tre ställen:

- **I hpr.** Den är inte obligatorisk och får utelämnas [B1 §6.4].
- **På produktionsunderlaget.** Där är det möjligt, inte nödvändigt, att lägga till den per sortiment [B2].
- **I sortimentsstrukturen.** Att ange *producerat för mottagningsplats* är ett av flera sätt att hålla isär virke
  till olika industrier. Ett annat är ett industrispecifikt handelssortiment, och då behövs uppgiften inte [B3 §3.2].

Datan säger samma sak: uppgiften saknas på omkring var sjätte stock [D1]. Till 2026-11-18 stoppade kravet varje
månad som har sådana rader.

**Sedan 2026-11-18 stoppar det inte.** Skördarraden har alltid sitt avtalsobjekt, och det räcker för att veta vems
virket är. Källan lämnar värdet tomt, och virket blir avtalsobjektets lager utan känd mottagningsplats: ett lass tar
det när lagret för dess egen mottagningsplats är slut, som eget lager (S1). Går sortimentet till en mottagningsplats
är det samma sak som om uppgiften hade funnits. Kapas det för flera delar deras lass på virket, och det som
uppgiften skulle ha sagt är förlorat; `check` varnar för den volymen. Mätt i simulatorn med 17 % av skörden utan
uppgift står det i [metodjamforelse.md](metodjamforelse.md).

Hur mycket luckan kostar beror på tre saker, och ingen av dem är besvarad [D1]:

- Om luckan finns i sågtimret eller i massaved och energived.
- Om den gäller hela avtalsobjekt eller spridda stockar.
- Vad leveransen har som *producerat för mottagningsplats* när skörden saknar den. Leveransen saknar den aldrig
  [D3], så värdet kommer någon annanstans ifrån, troligen destineringen: ett destinerat sortiment bär paret
  producerat handelssortiment och producerat för mottagningsplats [B2].

Den tredje frågan avgjorde varför det inte räckte att bara släppa kravet: har leveransen ett värde som skörden
saknar, hittar lasset inget lager för sin mottagningsplats. Lagret utan känd mottagningsplats är svaret på det.

Ett svar pekar på en väg framåt. Datalagret har också en destinerad mottagningsplats per stock, och de två
kolumnerna har samma värde på bara 0,3 % av stockarna [D9]. Saknas markeras med ett eget värde i båda, så högst
0,3 % av stockarna saknar båda. Där *producerat för* saknas finns alltså nästan alltid en destinering. Två saker
är obelagda: om de två kolumnerna har samma id-lista, och varför de skiljer sig där båda är satta.

Hur mycket lagret per mottagningsplats betyder är inte heller mätt. 39 % av arbetsordrarna levererar till mer än en
mottagningsplats [D8], men talet gäller alla sortiment tillsammans, och olika sortiment går till olika industrier.
Det som avgör är hur ofta samma sortiment från ett avtalsobjekt går till flera mottagningsplatser. Den typiska
arbetsordern är inte delad: den största mottagningsplatsen får i median 100 % av leveransen och 99,9 % av det
skördade. Volymvägt är andelarna 64 % och 80 %, så det är de stora arbetsordrarna som delas [D10].

### Avverkningsdatum håller i datan

VIOL 3 lovar inte datumet. Uppgifterna per stam lagras om de förekommer i filen [B1 §8], och de skapas inte alls vid
rapportering i Rapp [B2]. Datan har det ändå på varje rad, och spridningen över 8–13 dagar per avtalsobjekt visar att
det är fällningsdagen och inte rapportdagen [D2].

Kravet kan stå kvar. Metoden använder dagen för att veta vilket virke som fanns när lasset kördes, och drar det
äldsta först när lastbilarna följer skördaren ([metod.md](metod.md)). En gissad dag skulle flytta virke mellan lass
och månader utan att det syns. Risken är en maskin eller ett avtalsobjekt som datan från 2026 inte innehåller.

### Varje lass har skördardata: metodens krav, inte VIOL 3:s

Ett lass utan skördardata för sitt avtalsobjekt och sortiment stoppar månaden. VIOL 3 kräver inte att sådan data
finns:

- Produktion kan rapporteras i Rapp i stället för med skördarens fil. Rapp hanterar bara handelssortiment, inte
  produkter, och resultatet per stam skapas inte [B2].
- Dokumenten säger vad som krävs *för att* produktionsrapportera, ett produktionsunderlag [B2], inte att varje
  avtalsobjekt rapporteras från en skördare.

Det enda stickprovet är litet: vid ett sågverk en månad hade alla 297 par av avtalsobjekt och sortiment skördardata
[D6]. Provet frågade bara om någon rad fanns, inte om den hade kommit när månaden kördes.

Hela datan ger ett tydligare svar, i två delar [D11]:

- **Avverkat virke har skördardata.** Bland arbetsordrar som är avverkningar saknar 67 av 6 817 stockdata, 0,3 % av
  deras levererade volym.
- **Mycket virke är inte avverkat i systemet.** 28 % av den levererade volymen ligger på arbetsordrar som enligt sin
  typ inte har någon produktion: centrala köp, egen terminal, virkesköp utan produktion och import. Ytterligare
  1,5 % är grotskotning.

Antagandet att allt virke kommer från skördare med skördardata håller alltså inte för hela flödet. Det håller för
det avverkade virket, och det övriga går att känna igen på arbetsorderns typ. Talen gäller alla sortiment; hur stor
del av sågtimret till ett sågverk som saknar avverkning är inte mätt.

Beslutat 2026-11-17: bilagan täcker bara avverkat virke och säger det. Källan tar med det övriga virket och märker
det `utan_avverkning` ur arbetsorderns typ. treedist håller det utanför matriserna, och bilagan anger hur stor del
av sågverkets inmätta volym matrisen gäller. Stoppet står kvar för avverkat virke utan skördardata, och ett märkt
avtalsobjekt som har skördardata eller har fördelats tidigare stoppar, så att märkningen inte blir en väg förbi.
Har källan anskaffningsform, som är en term på leveransnivå i VIOL 3 [B5 §3.2], visar bilagan volymen per
anskaffningsform i ett eget diagram.

Kravet är alltså ett val i metoden. Sex antaganden beslutades 2026-11-09, bland dem att allt virke kommer från
skördare med skördardata och att skördaren rapporterar före lastbilen ([antaganden.md](antaganden.md)). Bryts de
finns ingen egen fördelning att ge lasset. Valet kan stå kvar, men det ska inte motiveras med VIOL 3.

## Kraven på mätningen

| Krav | Vad VIOL 3 säger | Vad datan visar | Bedömning |
|---|---|---|---|
| `leveransnummer` | Mätbeskedet listar de ingående leveranserna med leveransnummer per mätdatum [B4 §3.4] | Varje korrigering hittar sitt lass på numret [D4] | Håller |
| `avtalsobjekt`, `handelssortiment`, `mottagningsplats`, `leveransdatum`, `matdatum` | Alla är termer på leveransnivå [B5 §3.2]. Listan gäller pris- och urvalsvillkor och lovar inte att varje leverans har alla | Inte frågat särskilt. Korrigeringarna hittar sitt lass på avtalsobjekt, sortiment och mottagningsplats, och har lassets transportdatum [D4, D5] | Håller |
| `producerat_handelssortiment`, `producerat_for_mottagningsplats` | Båda är termer på leveransnivå [B5 §3.2], och ett destinerat sortiment bär paret [B2] | Ingen leveransrad saknar någon av dem, med `-1` räknat som saknat [D3] | Håller |
| `volym_m3fub` och `brutto_m3fub` | En brutto- och en nettovolym i m3f redovisas per leverans och dokumenttyp [B6 §3.3] | Inte frågat särskilt | Håller i dokumenten |
| En vändning har lassets nummer, avtalsobjekt, sortiment och mottagningsplats | En korrigering relaterar alltid till det tidigare mätbeskedet och dess leveransnummer. Inget eget kreditbesked sänds ut [B4 §4] | Alla 7 501 negativa rader vänder hela volymen på en rad med samma fyra uppgifter [D4] | Håller |
| Bara data från VIOL 3 | VIOL 3 tog emot leveranser från 2025-05-02, VIOL 2 till 2025-10-17 [B7] | Datan kommer bara att vara från VIOL 3 [D7] | Håller |

### Vända lass håller, med en reservation

Dokumentet säger att korrigeringen pekar på det tidigare beskedets leveransnummer [B4 §4]. Att den är en hel negativ
rad med samma avtalsobjekt, sortiment och mottagningsplats står inte där; det kommer bara ur datan [D4]. Det är ändå
väl belagt: 7 501 av 7 501 rader.

Två följder av svaren är värda att känna till:

- **3,5 % av de ommätta lassen bokas om under ett annat nummer** [D4]. Det klarar metoden: vändningen har det gamla
  numret och lägger tillbaka virket, och den nya raden är ett nytt lass.
- **En korrigering kan ändra identitetsuppgifter**, inte bara kvantitet [B4 §4]. Den negativa raden har då lassets
  gamla uppgifter, vilket är vad datan visar [D4].

## Två regler som är våra egna

### Månadens rader väljs på redovisningsdatum

Ordet redovisningsdatum finns inte i något av Biometrias dokument som lästs [B4, B8]. Regeln kommer ur datan: den
negativa raden kopierar lassets transportdatum i 100 % av fallen och mätdatum i 99,65 %, så bara redovisningsdatum
säger när korrigeringen gjordes. Det skiljer på 47 % av paren, i snitt 5 dagar [D5].

Regeln håller i datan. Två saker är obelagda: vad datumet heter och betyder i VIOL 3, och om datalagret sätter det
på samma sätt för alla rader.

### Liggaren börjar minst sex månader före första fakturan

En vändning av ett lass som liggaren inte känner stoppar månaden. Källan ska därför utelämna vändningar av lass som
redovisades före liggarens första månad, och liggaren ska börja så tidigt att de blir få.

Sex månader kommer av att det längsta avståndet mellan ett lass och dess korrigering var 178 dagar [D5]. Det är det
största värdet under ett år, inte en gräns. Två av Biometrias dokument tyder på att sena rättelser är väntade:

- VIOL 2-transaktioner gick att rätta i tre månader efter att inmätningen stängdes [B7].
- Händelsestyrda mätbesked kan vänta 1–365 dagar efter en ny eller korrigerad händelse [B9].

Regeln håller som arbetssätt. Gränsen är tunt belagd, och stoppet är rätt skydd när den brister: en vändning som
inte hittar sitt lass kan inte krediteras rätt.

## Vad som bör göras

Tre saker, i ordning efter hur mycket de avgör. Den andra är gjord.

1. **Ta reda på vad luckan i producerat för mottagningsplats är**, med de tre frågorna ovan. Sedan 2026-11-18 går
   en verklig månad att köra med luckan, men där ett sortiment kapas för flera mottagningsplatser kostar den.
2. **Gjort 2026-11-17: bilagan anger virke utan avverkning utanför matrisen**, med kolumnen `utan_avverkning`.
   Kvar är att mäta hur stor del av sågtimret till ett sågverk det gäller.
3. **Skriv om motiveringen i AGENTS.md och kontraktet** för de två kraven som inte vilar på VIOL 3, så att ingen tror
   att VIOL 3 garanterar dem.

## Källor

### Biometrias dokument

Lästa 2026-11-17. Dokumenten är Biometrias och får inte spridas, så här står länk, version och vad som lästes, inte
texten.

| | Dokument | Version | Avsnitt som används |
|---|---|---|---|
| B1 | [Tolkning och redovisning av skördarens produktion i VIOL 3, hpr](https://www.biometria.se/media/g4zbgb1j/biometria-regler-vid-tolkning-av-hpr-viol3-20251020.pdf) | 2.0, 2025-10-20 | 6.1, 6.4, 7.1, 8, 8.12 |
| B2 | [Produktion i VIOL 3, helhetslösning och förberedelser](https://www.biometria.se/media/ffmfrvts/helhetsloesning-produktion-jan-2023.pdf) | 2023-01-24 | Produktionsunderlag, Produktionsdata, Nytt data i VIOL 3, destinering, Rapp |
| B3 | [Sortimentsstrukturen i VIOL 3](https://www.biometria.se/media/yqgohtdj/beskrivning-av-sortimentstruktur-i-viol-3.pdf) | 1.0, 2021-09-10 | 3.2 |
| B4 | [Så här läser du ditt mätbesked i VIOL 3](https://biometria.se/media/3cajdnjf/saa-haer-laeser-du-ditt-maetbesked-version-10.pdf) | 1.0, 2024-08-23 | 3.4–3.6, 4 |
| B5 | [Beskrivning av värde- och urvalstermer råvara](https://biometria.se/media/5m2fc5as/beskrivning-av-vaerde-och-urvalstermer-raavara-60.pdf) | 6.0, 2024-10-03 | 3.2 |
| B6 | [White paper Principer för mätningsflöden VIOL 3](https://www.biometria.se/media/ewvnofoa/white-paper-principer-foer-maetningsfloeden-viol-3-20230303.pdf) | 1.0, 2023-03-03 | 3.3 |
| B7 | [Komprimerad info VIOL 3 transport](https://biometria.se/media/jjkc0pat/komprimerad-info-viol-3-transport.pdf) | 2024-10-07 | Översikt viktiga datum |
| B8 | [Principer för mätning och redovisning av kvantiteter i VIOL 3](https://biometria.se/media/ke0dk42k/principer-foer-maetning-och-redovisning-av-kvantiteter-i-viol-3-40.pdf) | 4.0 | Hela, sökt efter redovisningsdatum |
| B9 | [Handbok Mätbeskedsklienten](https://biometria.se/media/jcmh2bq5/handbok_maetbeskedsklienten_viol-3_21.pdf) | 2.1, 2025-03-24 | Händelsestyrda mätbesked |

### Svar ur den verkliga datan

Svar på SQL-frågor mot en verklig datamiljö, lämnade 2026-11-17 och gällande data från 2026. De står också i
[stickproven](antaganden.md#stickprov-ur-verklig-data). Inga namn, koder eller frågor sparas här, bara andelar och
antal.

| | Fråga | Svar |
|---|---|---|
| D1 | Hur ofta saknar en stock i produktionen producerat för mottagningsplats? | Ungefär 17 % mars–oktober, 23 % i januari, 54 % i februari, 10 % i november. Räknat i antal stockar, alla sortiment. Inte känt om det gäller sågtimret eller hela avtalsobjekt |
| D2 | Hur ofta saknas avverkningsdatum, och hur många avverkningsdagar har ett avtalsobjekt? | Ingen rad saknar det. I snitt 8–13 olika dagar per avtalsobjekt |
| D3 | Hur ofta saknar en leveransrad producerat handelssortiment eller producerat för mottagningsplats? | Aldrig, med `-1` räknat som saknat |
| D4 | Hur ser en korrigering ut? | 7 501 negativa rader. Var och en vänder hela volymen på en rad med samma leveransnummer, avtalsobjekt, sortiment och mottagningsplats. 96,5 % av de ommätta lassen bokas igen under samma nummer |
| D5 | Vilka datum skiljer en korrigering från sitt lass? | Transportdatum samma på 100 %, mätdatum på 99,65 % och som mest 22 dagar isär. Redovisningsdatum samma på 53 %, i snitt 5 dagar isär och som mest 178 |
| D6 | Har varje lass skördardata? (tidigare stickprov) | Ett sågverk en månad: alla 297 par av avtalsobjekt och sortiment, 43 600 m3fub, hade skördardata |
| D7 | Från vilket system kommer datan? | Första fakturamånaden är inte bestämd, men datan blir bara från VIOL 3 |
| D8 | Hur ofta har en arbetsorder volym till mer än en mottagningsplats? | 7 814 av 19 968 arbetsordrar med volym från 2026-01-01, 39 %. 61 % har en mottagningsplats, 11 % två, 9 % tre och 19 % fyra eller fler. Alla sortiment, med korrigeringsrader. Ingen saknar mottagningsplats |
| D9 | Hur förhåller sig producerat för och destinerad mottagningsplats i produktionen? | 73,9 miljoner stockar fällda från 2026-01-01, i 5 976 arbetsordrar. De två kolumnerna har samma värde på 0,3 % av stockarna. Ingen är tom; saknas har ett eget värde. Räknat per arbetsorder har 57 % mer än ett värde på producerat för och 88 % mer än ett på destinerad, men värdet för saknas är troligen medräknat som en plats, och talen gäller alla sortiment |
| D10 | Hur stor del av en arbetsorders volym går till dess största mottagningsplats? | Leveranser körda från 2026-01-01, 20 002 arbetsordrar och 7,1 miljoner m3fub: medel 84 %, median 100 %, kvartiler 64 % och 100 %, volymvägt 64 %. Produktion fälld från 2026-01-01, 5 976 arbetsordrar och 5,0 miljoner m3fub: för producerat för medel 84 %, median 99,9 %, kvartiler 66 % och 100 %, volymvägt 80 %; för destinerad medel 70 %, median 70 %, volymvägt 68 %. Alla sortiment, och värdet för saknas är troligen räknat som en plats |
| D11 | Vilka arbetsordrar med leveranser saknar stockdata? | Leveranser körda från 2026-01-01, alla sortiment: 20 002 arbetsordrar och 7,1 miljoner m3fub. 13 252 arbetsordrar saknar stockdata, 2,09 miljoner m3fub, 29 %. Av den volymen: centrala köp utan produktion 73 % (11 904 arbetsordrar), egen terminal 11 % (48), virkesköp utan produktion 5 % (527), import 5 % (22), grotskotning 5 % (684), avverkning utan skördardata 0,8 % (67 arbetsordrar, 15 900 m3fub). 6 750 arbetsordrar har stockdata. 1 694 av de 20 002 levererade första gången före 2026 |
