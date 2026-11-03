# Exempelresor från skördning till leverans

Genererad av [example_journeys.py](../scripts/example_journeys.py) ur simulatorn. Varje resa visar vad som hände
med stockarna och vad `treedist` skattade utan att se dem. Diametrar är klassbottnar, volymviktade. Felindex är
andelen volym i fel diameterklass. Bedömningen av antagandena finns i [antaganden.md](antaganden.md).

## Slutavverkning, en leveransmånad: AO00051, GRAN_SAG

- **Bestånd:** slutavverkning i region sodra, 3,844 stockar, 781 m3fub på 2 avlägg.
- **Planerad destination:** SAG_GROV. **Faktisk:** SAG_GROV.
- **Skördarrapport:** 2026-06.
- **Svinn:** 52 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 08/06–13/06 | 1938 | 286 | 20.5 | 18/06–21/06 | 7 | 9 |
| 2 | 13/06–18/06 | 1906 | 495 | 26.3 | 23/06–27/06 | 11 | 9 |

Inmätt: 18 leveranser, 772.0 m3fub brutto och 763.0 netto, mot 769.4 som faktiskt kom fram och 769.2 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-06 | 763.0 | 100% | 0% | 0% | 22.8 | 23.2 | 0.03 |

Över hela arbetsordern: felindex 0.03 för diameterfördelningen.

## Slutavverkning över ett månadsskifte: AO00059, TALL_SAG

- **Bestånd:** slutavverkning i region norra, 5,872 stockar, 876 m3fub på 3 avlägg.
- **Planerad destination:** SAG_KLEN. **Faktisk:** SAG_KLEN.
- **Skördarrapport:** 2026-06.
- **Svinn:** 36 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 12/06–17/06 | 1967 | 252 | 19.1 | 21/06–23/06 | 6 | 8 |
| 2 | 17/06–22/06 | 1961 | 371 | 22.8 | 26/06–27/06 | 9 | 6 |
| 3 | 22/06–28/06 | 1944 | 253 | 19.3 | 02/07–02/07 | 6 | 7 |

Inmätt: 21 leveranser, 867.5 m3fub brutto och 858.5 netto, mot 869.4 som faktiskt kom fram och 885.5 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-06 | 609.2 | 100% | 0% | 0% | 20.1 | 20.3 | 0.02 |
| 2026-07 | 249.3 | 100% | 0% | 0% | 19.1 | 18.3 | 0.07 |

Över hela arbetsordern: felindex 0.01 för diameterfördelningen.

## Gallring: AO00085, GRAN_SAG

- **Bestånd:** gallring i region mellan, 1,667 stockar, 173 m3fub på 4 avlägg.
- **Planerad destination:** SAG_KLEN. **Faktisk:** SAG_KLEN.
- **Skördarrapport:** 2026-10, 2026-11.
- **Svinn:** 0 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 21/10–25/10 | 402 | 36 | 16.2 | 13/11–13/11 | 1 | 21 |
| 2 | 25/10–29/10 | 420 | 43 | 17.3 | 18/11–18/11 | 1 | 22 |
| 3 | 29/10–02/11 | 422 | 48 | 18.1 | 19/11–22/11 | 2 | 19 |
| 4 | 02/11–06/11 | 423 | 46 | 17.7 | 14/11–16/11 | 2 | 10 |

Inmätt: 6 leveranser, 174.4 m3fub brutto och 171.9 netto, mot 173.1 som faktiskt kom fram och 172.2 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-11 | 171.9 | 97% | 3% | 0% | 16.2 | 16.4 | 0.02 |

Över hela arbetsordern: felindex 0.02 för diameterfördelningen.

## Utan skördardata: AO00079, TALL_SAG

- **Bestånd:** slutavverkning i region sodra, 2,688 stockar, 849 m3fub på 3 avlägg.
- **Planerad destination:** SAG_MIX. **Faktisk:** SAG_MIX.
- **Skördarrapport:** saknas helt.
- **Svinn:** 28 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 21/09–24/09 | 888 | 206 | 24.8 | 14/10–17/10 | 5 | 23 |
| 2 | 24/09–26/09 | 944 | 251 | 26.6 | 03/10–07/10 | 6 | 9 |
| 3 | 26/09–29/09 | 856 | 393 | 33.2 | 07/10–14/10 | 9 | 13 |

Inmätt: 20 leveranser, 843.5 m3fub brutto och 834.3 netto, mot 841.2 som faktiskt kom fram och 838.7 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-10 | 834.3 | 0% | 0% | 100% | 26.5 | 28.2 | 0.13 |

Över hela arbetsordern: felindex 0.13 för diameterfördelningen.

## Sen skördarrapport: AO00022, GRAN_SAG

- **Bestånd:** slutavverkning i region sodra, 2,049 stockar, 633 m3fub på 1 avlägg.
- **Planerad destination:** SAG_GROV. **Faktisk:** SAG_GROV.
- **Skördarrapport:** 2026-04.
- **Svinn:** 12 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 07/03–21/03 | 2049 | 633 | 28.1 | 19/04–10/05 | 15 | 46 |

Inmätt: 15 leveranser, 630.0 m3fub brutto och 624.4 netto, mot 629.0 som faktiskt kom fram och 634.2 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-04 | 354.9 | 100% | 0% | 0% | 27.0 | 27.0 | 0.03 |
| 2026-05 | 269.6 | 100% | 0% | 0% | 27.0 | 27.2 | 0.05 |

Över hela arbetsordern: felindex 0.01 för diameterfördelningen.

## Omdirigerad till annat sågverk: AO00039, TALL_SAG

- **Bestånd:** slutavverkning i region mellan, 3,102 stockar, 724 m3fub på 4 avlägg.
- **Planerad destination:** SAG_KLEN. **Faktisk:** SAG_MIX.
- **Skördarrapport:** 2026-04, 2026-05.
- **Svinn:** 35 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 22/04–25/04 | 824 | 161 | 23.1 | 15/05–18/05 | 4 | 23 |
| 2 | 25/04–29/04 | 787 | 228 | 27.3 | 24/05–30/05 | 6 | 30 |
| 3 | 29/04–02/05 | 769 | 211 | 26.8 | 19/05–23/05 | 5 | 20 |
| 4 | 02/05–06/05 | 722 | 124 | 21.8 | 12/05–15/05 | 3 | 9 |

Inmätt: 18 leveranser, 717.2 m3fub brutto och 710.8 netto, mot 716.0 som faktiskt kom fram och 732.3 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-05 | 710.8 | 100% | 0% | 0% | 24.3 | 24.3 | 0.01 |

Över hela arbetsordern: felindex 0.01 för diameterfördelningen.

## Flödet som helhet

Simulering med frö 71, 12 månader, efter 2 månaders inkörning.

| Storhet | Simulatorn |
|---|---|
| Tid från fällning till leverans per m3fub, 10/50/90 % | 8 / 18 / 34 dagar |
| Medeltid enligt Littles lag, lager delat med flöde | 18 dagar |
| Skördetid per arbetsorder, median | 15 dagar |
| Från sista fällning till första lass, median | 6 dagar |
| Leveranskampanj, median | 15 dagar |
| Volym per arbetsorder och sortiment, slutavverkning, median | 721 m3fub |
| Volym per arbetsorder och sortiment, gallring, median | 188 m3fub |
| Lass per arbetsorder och sortiment, median | 15 |
| Bruttovolym per leverans, median | 44.5 m3fub |
| Andel arbetsordrar som levererar i två månader eller fler | 44% |
| Andel stockar som når sågverk efter skördarens rapportmånad | 57% |
