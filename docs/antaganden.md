# Är antagandena rimliga?

Granskning av vad simulatorn och metoden antar om vägen från skördare till sågverk. Bedömningen bygger på
[exempelresorna](exempelresor.md), mätningar på det simulerade flödet och publicerade källor. Där en källa saknas står
det. **Härlett** betyder egen beräkning ur källor.

**Sammanfattning.** Granskningen hittade två antaganden som inte höll: lagringstiden var för lång, och sommaravverkat
timmer låg lika länge som vinteravverkat trots att köparna kräver leverans inom två veckor. Simulatorn är rättad och följer nu
säsongen. De övriga antagandena är rimliga eller går inte att pröva utan egna data. Känslighetsproven visar att metod C
har lägst fel i alla sju varianter, med prisfel 6,0–9,9 kr/m3fub. Det som mest påverkar resultatet i verkligheten är
hur stor andel som saknar skördardata, och i vilken ordning avläggen körs.

## Vad exempelresorna visar

Sex arbetsordrar ur samma simulering, en av varje slag:

| Resa | Felindex diameter | Vad den visar |
|---|---|---|
| Slutavverkning, en leveransmånad | 0,03 | Fälld 8–18 juni, levererad 18–27 juni, 9 dagar på avlägg. Allt ur eget lager |
| Slutavverkning över ett månadsskifte | 0,02 och 0,07 | Det klenaste avlägget fälldes sist och kördes i juli |
| Gallring | 0,02 | Fyra små avlägg, sex lass |
| Utan skördardata | 0,13 | Lånad fördelning, 26,5 cm mot verkliga 28,2. Ett av avläggen var ovanligt grovt |
| Sen skördarrapport | 0,03 och 0,05 | Fälld i mars, väntade till efter tjällossningen, 46 dagar på avlägg |
| Omdirigerad | 0,01 | Fel sågverk planerat, men mottagningsplatsen ger rätt destination |

Resan över månadsskiftet visar metodens svagaste punkt. Avlägg 3 var klenare än avlägg 2 och kördes sist. Metoden
utesluter virke som inte hunnit fällas, men inom det som fanns drar den pro rata. Juli skattades till 19,1 cm mot verkliga
18,3. Över hela arbetsordern blir det rätt (0,01), men den enskilda månaden blir något fel. Uppgift om vilket avlägg ett
lass kom från skulle ta bort det felet; se sista avsnittet.

## Simulatorns antaganden

| Antagande | Simulatorn | Verkligheten | Bedömning |
|---|---|---|---|
| Tid från fällning till leverans | Median 18 dagar, medel 18–21 | Sågtimmerlagret i landet är 2,6–3,5 miljoner m3fub, mot knappt 34 miljoner m3fub avverkat per år: 28–37 dagar från fällning till förbrukning (härlett). 4–6 % av årsavverkningen ligger vid industrin, alltså 15–22 dagar där. Kvar blir cirka 6–22 dagar i skog, vid väg och på terminal | Rimligt efter rättningen. Var 31 dagar. Statistiken täcker bara de största aktörerna, så den verkliga tiden är troligen något längre än beräkningen |
| Sommaravverkat timmer | Median 12 dagar, 72 % inom 14 dagar. På sommaren börjar 90 % av arbetsordrarna leverera medan skörden pågår | Holmen: timmer fällt 1/6–31/8 ska vara vid sågverket inom två veckor. Mellanskog och Sveaskog: anmält vid väg inom två veckor. Blånad ger avdrag och kan stoppa partier | Rimligt efter rättningen. Var 30 dagar och inget inom 14 |
| Vinteravverkat timmer | Median 24 dagar | Vinterfällt får ligga till 15 april (Mellanskog) eller 15 juni (Holmen) | Rimligt. Väntan genom tjällossningen syns i exemplet ovan |
| Skörd sedan leverans, 1–3 veckor var | Skördetid median 15 dagar, kampanj 15 dagar. Vintertid separata perioder, sommartid överlappande | Projektets egen beskrivning, och köparnas regler för sommaravverkat timmer | Rimligt |
| Storlek per arbetsorder | Median 721 m3fub sågtimmer per sortiment vid slutavverkning, 188 vid gallring | Medelanmälan för föryngringsavverkning var 3,8 ha 2021, knappt 5 ha för andra ägare än enskilda. Med antagna 250 m3sk/ha och knappt hälften sågtimmer blir det 350–500 m3fub sågtimmer per trakt (härlett, volym per hektar antagen) | **Troligen för stora**, kanske upp till dubbelt. Ett bolags arbetsorder kan dock omfatta flera anmälningar. Prövat nedan |
| Lass | Median 44,5 m3fub | 64 ton totalvikt ger cirka 45 m3fub (härlett), 74-tonsbilar mer | Rimligt |
| Andel stockmätt | 90 % | En stor majoritet av sågtimret stockmäts (Skogforsk) | Rimligt, exakt andel okänd |
| Vrak | 0–2 %, i snitt 1 % | Ingen läsbar källa hittad; ett Biometriadokument som ska ange cirka en procent gav 404 | Antagande |
| Svinn mellan skördare och mätning | 1 % ± 1,5 % | Ett exempel i Biometrias material räknar med 1 % | Rimligt som nivå, spridningen antagen |
| Skördarens mätfel | 0,9 % över i volym, 3 mm brus och 2 mm systematiskt per maskin i diameter | Biometria 2025: 0,9 % under bark. Spridning 2,4–9,6 mm i toppdiameter mellan mätramar | Rimligt |
| Utan skördardata | 10 %, prövat med 30 % | Sveaskog: 13 % köpt från privata ägare och 3 % import. Om köpt virke har skördardata framgår inte | Okänt, **viktigast att ta reda på** |
| Sen rapport | 10 % kommer månaden efter | hpr-filer kan skickas delavslutade under avverkningen (Biometria) | Troligen försiktigt antaget |
| Destination | Planeras efter grovlek, 5 % omdirigeras | Sågverk är inriktade på dimensioner, men styrkan är okänd | Antagande, prövat nedan |
| Skillnader inom bestånd | Varje avlägg har egen grovlek, standardavvikelse 10 % | Ingen källa | Antagande, prövat med 20 % i metodjämförelsen |
| Ordning mellan avlägg | I fällningsordning när leveransen överlappar skörden, annars slumpad | Ingen källa | Antagande. Avgör hur stort månadsskiftesfelet blir |

Ej med i simulatorn: massaved, kvalitetsklasser, samlast, terminaler, stormvirke och omklassning vid inmätning.

## Metodens antaganden

| Antagande | Bedömning |
|---|---|
| Skördarens fördelning beskriver det som levereras, efter 0,9 % kalibrering och 1 % svinn | Rimligt. Skördaren mäter ungefär lika bra som mätramen |
| Inmätningens volym är exakt på fakturan | Rimligt, den är avtalsmässigt det som betalas |
| Ett lass drar pro rata ur arbetsorderns lager, bland virke fällt minst 2 dagar innan | Rimligt utan uppgift om avlägg. Ger felet vid månadsskiftet ovan |
| Virke utan skördardata liknar arbetsordrar med samma destination och grupp | Rimligt om sågverk tar emot en viss grovlek. Prövat nedan |
| En arbetsorder utan skördardata levererar halva skörden samma månad | Antagande. Påverkar bara intervallets bredd |
| Månaden följer leveransdatum | Rimligt. Fakturamånad kan avvika, se README |

## Känslighet

Varje variant ändrar ett antagande, med fyra nya simuleringar om 12 månader per variant. Siffrorna går att återskapa med
[sensitivity.py](../scripts/sensitivity.py) och finns i [kanslighet_resultat.csv](kanslighet_resultat.csv).

| Variant | Prisfel C | Prisfel A | Prisfel naiv | Värdetäckning C | Andel eget lager |
|---|---|---|---|---|---|
| Bas, med säsong | 9,2 | 12,5 | 43,6 | 93 % | 86 % |
| Leverans efter skörd året runt, lång lagring (förra basen) | 9,3 | 12,0 | 48,1 | 93 % | 89 % |
| Leverans under pågående skörd året runt | 6,7 | 9,6 | 34,9 | 94 % | 89 % |
| Tre gånger så lång paus före leverans | 9,8 | 12,7 | 52,2 | 92 % | 87 % |
| Destination oberoende av grovlek | 9,9 | 12,8 | 55,4 | 88 % | 86 % |
| Mindre arbetsordrar, dubbelt så många | 6,0 | 11,6 | 29,1 | 94 % | 86 % |
| 20 % omdirigerat | 7,5 | 10,6 | 50,5 | 94 % | 89 % |

Prisfel i kr/m3fub per månad, destination och sortiment.

- **Rättningen av säsongen ändrade inte slutsatserna.** Den naiva metoden blev bättre med kortare lagring, 43,6 mot
  48,1, men C har fortfarande under en fjärdedel av dess fel. Med säsong ligger något mindre ur eget lager, 86 mot
  89 %, eftersom mer virke hinner levereras innan skördardatan kommit in.
- **Utan koppling mellan destination och grovlek krymper C:s försprång** mot A, och intervallet blir för smalt (88 %).
  Vikten för samma destination är inställd mot simulatorn och bör prövas på verkliga data.
- **Äldsta virket först vinner mest när lastbilarna följer skördaren.** Med leverans under pågående skörd året
  runt sjönk C:s prisfel från 8,1 till 6,7 när klättringen införde det, och med leverans efter skörd är det oförändrat.
- **Mindre arbetsordrar ger lägre fel**, eftersom fler och mindre leveranser jämnar ut månadsskiftena. Om verkliga
  arbetsordrar är mindre än i simulatorn är basens fel alltså snarare för högt.

## Det som skulle förbättra mest

1. **Ta reda på hur stor andel av det levererade virket som saknar skördardata.** Det är den största enskilda
   felkällan: 30 % utan data nästan fördubblar prisfelet. Gäller särskilt köpt virke och import.
2. **Avlägg eller startplats per leverans.** Biometria skapar leveransinnehåll per avtalsobjekt, handelssortiment och
   startplats, och hpr-filer innehåller koordinater per stam. Kan ett lass kopplas till ett avlägg, och skördardatan
   delas per avlägg, försvinner det mesta av månadsskiftesfelet.
3. **Löpande skördarrapportering.** Med kort sommarlagring ökar annars andelen preliminärt fördelad volym.

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
