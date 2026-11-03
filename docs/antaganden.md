# Är antagandena rimliga?

Granskning av vad simulatorn och metoden antar om vägen från skördare till sågverk. Bedömningen bygger på
[exempelresorna](exempelresor.md), mätningar på det simulerade flödet och publicerade källor. Där en källa saknas står
det. **Härlett** betyder egen beräkning ur källor.

**Sammanfattning.** De flesta antaganden är rimliga eller går inte att pröva utan egna data. Två avviker tydligt:
lagringstiden är för lång, och sommartimmer ligger i simulatorn lika länge som vintertimmer trots att köparna kräver
leverans inom två veckor. Känslighetsproven visar att metodens slutsatser håller ändå: metod C har lägst fel i alla sju
varianter och prisfelet ligger mellan 7,0 och 10,4 kr/m3fub. Det som mest påverkar resultatet i verkligheten är i
stället hur stor andel som saknar skördardata, och i vilken ordning avläggen körs.

## Vad exempelresorna visar

Sex arbetsordrar ur samma simulering, en av varje slag:

| Resa | Felindex diameter | Vad den visar |
|---|---|---|
| Slutavverkning, en leveransmånad | 0,02 | Allt ur eget lager. Felet är bara skördarens mätning |
| Slutavverkning över ett månadsskifte | 0,03 och 0,05 | Delad mellan två månader, båda nära rätt eftersom beståndet är jämnt |
| Gallring | 0,12 och 0,07 | Fyra avlägg med olika grovlek, en enda lass första månaden |
| Utan skördardata | 0,11 | Lånad fördelning, medeldiametern rätt men formen sämre |
| Sen skördarrapport | 0,04 | 15 % preliminärt (S2), rättat månaden efter |
| Omdirigerad | 0,04 och 0,20 | Tre avlägg; det klenaste kördes sist och hamnade i december |

Den sista resan visar metodens svagaste punkt. Avlägg 2 hade medeldiameter 24,2 cm mot 25,6 och 28,6 för de andra, och
kördes sist. Metoden drar pro rata ur hela lagret och skattade december till 25,8 cm mot verkliga 23,2. Över hela
arbetsordern blir det rätt (0,03), men den enskilda månaden blir fel. Uppgift om vilket avlägg ett lass kom från skulle
ta bort det felet; se sista avsnittet.

## Simulatorns antaganden

| Antagande | Simulatorn | Verkligheten | Bedömning |
|---|---|---|---|
| Tid från fällning till leverans | Median 31 dagar, medel 34 | Sågtimmerlagret i landet är 2,6–3,5 miljoner m3fub, mot knappt 34 miljoner m3fub avverkat per år: 28–37 dagar från fällning till förbrukning (härlett). 4–6 % av årsavverkningen ligger vid industrin, alltså 15–22 dagar där. Kvar blir cirka 6–22 dagar i skog, vid väg och på terminal | **För lång**, troligen 1,5–3 gånger. Statistiken täcker bara de största aktörerna och underskattar därför lagret något |
| Sommartimmer | Median 30 dagar, inget inom 14 | Holmen: timmer fällt 1/6–31/8 ska vara vid sågverket inom två veckor. Mellanskog och Sveaskog: anmält vid väg inom två veckor. Blånad ger avdrag och kan stoppa partier | **Orimligt.** På sommaren pågår leverans medan skördaren är kvar |
| Vintertimmer | Median 33 dagar | Vinterfällt får ligga till 15 april (Mellanskog) eller 15 juni (Holmen) | Kan vara längre i verkligheten. Simulatorns säsongsfaktor slår för svagt |
| Skörd sedan leverans, 1–3 veckor var | Skördetid median 15 dagar, kampanj 15 dagar | Projektets egen beskrivning | Rimligt, men inte på sommaren enligt raden ovan |
| Storlek per arbetsorder | Median 851 m3fub sågtimmer per sortiment vid slutavverkning, 115 vid gallring | Medelanmälan för föryngringsavverkning var 3,8 ha 2021, knappt 5 ha för andra ägare än enskilda. Med antagna 250 m3sk/ha och knappt hälften sågtimmer blir det 350–500 m3fub sågtimmer per trakt (härlett, volym per hektar antagen) | **Troligen för stora**, kanske dubbelt. Ett bolags arbetsorder kan dock omfatta flera anmälningar |
| Lass | Median 44,5 m3fub | 64 ton totalvikt ger cirka 45 m3fub (härlett), 74-tonsbilar mer | Rimligt |
| Andel stockmätt | 90 % | En stor majoritet av sågtimret stockmäts (Skogforsk) | Rimligt, exakt andel okänd |
| Vrak | 0–2 %, i snitt 1 % | Ingen läsbar källa hittad; ett Biometriadokument som ska ange cirka en procent gav 404 | Antagande |
| Svinn mellan skördare och mätning | 1 % ± 1,5 % | Ett exempel i Biometrias material räknar med 1 % | Rimligt som nivå, spridningen antagen |
| Skördarens mätfel | 0,9 % över i volym, 3 mm brus och 2 mm systematiskt per maskin i diameter | Biometria 2025: 0,9 % under bark. Spridning 2,4–9,6 mm i toppdiameter mellan mätramar | Rimligt |
| Utan skördardata | 10 %, prövat med 30 % | Sveaskog: 13 % köpt från privata ägare och 3 % import. Om köpt virke har skördardata framgår inte | Okänt, **viktigast att ta reda på** |
| Sen rapport | 10 % kommer månaden efter | hpr-filer kan skickas delavslutade under avverkningen (Biometria) | Troligen försiktigt antaget |
| Destination | Planeras efter grovlek, 5 % omdirigeras | Sågverk är inriktade på dimensioner, men styrkan är okänd | Antagande, prövat nedan |
| Skillnader inom bestånd | Varje avlägg har egen grovlek, standardavvikelse 10 % | Ingen källa | Antagande, prövat med 20 % tidigare |
| Ordning mellan avlägg | Slumpad | Ingen källa | Antagande. Avgör hur stort månadsskiftesfelet blir |

Ej med i simulatorn: massaved, kvalitetsklasser, samlast, terminaler, stormvirke och omklassning vid inmätning.

## Metodens antaganden

| Antagande | Bedömning |
|---|---|
| Skördarens fördelning beskriver det som levereras, efter 0,9 % kalibrering och 1 % svinn | Rimligt. Skördaren mäter ungefär lika bra som mätramen |
| Leveransmätningens volym är exakt på fakturan | Rimligt, den är avtalsmässigt det som betalas |
| Ett lass drar pro rata ur arbetsorderns lager, bland virke fällt minst 2 dagar innan | Rimligt utan uppgift om avlägg. Ger felet i den omdirigerade resan |
| Virke utan skördardata liknar arbetsordrar med samma destination och grupp | Rimligt om sågverk tar emot en viss grovlek. Prövat nedan |
| En arbetsorder utan skördardata levererar halva skörden samma månad | Antagande. Påverkar bara intervallets bredd |
| Månaden följer leveransdatum | Rimligt. Fakturamånad kan avvika, se README |

## Känslighet

Varje variant ändrar ett antagande, med fyra simuleringar om 12 månader per variant. Siffrorna går att återskapa med
[sensitivity.py](../scripts/sensitivity.py) och finns i [kanslighet_resultat.csv](kanslighet_resultat.csv).

| Variant | Prisfel C | Prisfel A | Prisfel naiv | Värdetäckning C | Andel eget lager |
|---|---|---|---|---|---|
| Bas | 8,7 | 11,6 | 49,9 | 89 % | 89 % |
| Kort lagring, hälften levererar under skörd | 10,4 | 13,7 | 35,2 | 88 % | 85 % |
| All leverans under pågående skörd | 9,4 | 15,1 | 31,9 | 87 % | 84 % |
| Lång lagring, dubbelt så lång paus | 8,0 | 12,0 | 51,5 | 89 % | 89 % |
| Destination oberoende av grovlek | 9,3 | 10,9 | 76,0 | 87 % | 89 % |
| Mindre arbetsordrar, dubbelt så många | 7,0 | 10,4 | 36,1 | 92 % | 88 % |
| 20 % omdirigerat | 8,3 | 11,3 | 62,8 | 88 % | 91 % |

Prisfel i kr/m3fub per månad, destination och sortiment.

- **Kortare lagring gör den naiva metoden bättre men inte bra.** Med leverans under skörd sjunker dess fel från 50 till
  32 kr/m3fub, men C ligger kvar runt 9–10. Andelen ur eget lager sjunker från 89 till 84 %, eftersom mer virke hinner
  levereras innan skördardatan kommit in. Med kort lagring blir det alltså viktigare att skördardata rapporteras löpande.
- **Utan koppling mellan destination och grovlek försvinner det mesta av C:s försprång** mot A (9,3 mot 10,9), som
  väntat. C blir inte sämre än A.
- **Mindre arbetsordrar ger lägre fel**, eftersom fler och mindre leveranser jämnar ut månadsskiftena.
- **Intervallet håller 87–92 %** i alla varianter.

## Det som skulle förbättra mest

1. **Ta reda på hur stor andel av det levererade virket som saknar skördardata.** Det är den största enskilda
   felkällan: 30 % utan data nästan fördubblar prisfelet. Gäller särskilt köpt virke och import.
2. **Avlägg eller startplats per leverans.** Biometria skapar leveransinnehåll per avtalsobjekt, handelssortiment och
   startplats, och hpr-filer innehåller koordinater per stam. Kan ett lass kopplas till ett avlägg, och skördardatan
   delas per avlägg, försvinner det mesta av månadsskiftesfelet.
3. **Löpande skördarrapportering.** Med kort sommarlagring ökar annars andelen preliminärt fördelad volym.
4. **Låt simulatorn följa säsongen bättre:** leverans under skörd på sommaren och längre väntan på vintern. Proven ovan
   tyder inte på att metodens slutsatser ändras, men parametrarna som ställts in mot simulatorn bör kontrolleras igen
   då.

## Källor

- [Skogsstyrelsen, lager av sågtimmer, massaved och massaflis](https://www.skogsstyrelsen.se/statistik/avverkning/lager-av-sagtimmer-massaved-och-massaflis/)
- [Skogsstyrelsen, avverkningen 2025](https://www.skogsstyrelsen.se/nyhetslista/avverkningen-fortsatte-att-minska-2025/)
- [Skogforsk, Arbetsrapport 1231-2025, kostnader, lönsamhet och lager](https://www.skogforsk.se/cd_20250211113825/contentassets/b3d3919b3ac744fe82937338733fc85a/arbetsrapport-1231-2025-kostnader-intakter-lonsamhet-produktivitet-och-kvalitet-pa-utforda-atgarder-i-svenskt-skogsbruk.pdf)
- [Skogsstyrelsen, avverkningsanmälningar 2021](https://www.skogsstyrelsen.se/globalassets/statistik/statistikfaktablad/JO0314-statistikfaktablad-avverkningsanmalningar-2021.pdf)
- [Holmen, marknadsprislista 2026](https://www.holmen.com/globalassets/skog/prislistor/ny-20260416-marknadsprislista-hnd6l4-arvidsjaur-mala-norsjo-lucksele-sorselle-storuma-vilhelmina-stromsund-dorotea.pdf)
- [Mellanskog, allmänna leveransbestämmelser 2025](https://www.mellanskog.se/wp-content/uploads/2025/08/allmanna-leveransbestammelser.pdf)
- [Sveaskog, prislista Svealand och södra Norrland 2025](https://www.sveaskog.se/globalassets/skogsagare/2025/7995-s2-svealand-och-sodra-norrland-251215.pdf)
- [Biometria, regler vid tolkning av hpr](https://www.biometria.se/media/vezp5bej/biometria-regler-vid-tolkning-av-hpr.pdf)
- Övriga källor om mätning och volymer: [underlaget för simuleringen](simuleringsunderlag.md)
