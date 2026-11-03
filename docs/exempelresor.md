# Exempelresor från skördning till leverans

Genererad av [example_journeys.py](../scripts/example_journeys.py) ur simulatorn. Varje resa visar vad som hände
med stockarna och vad `treedist` skattade utan att se dem. Diametrar är klassbottnar, volymviktade. Felindex är
andelen volym i fel diameterklass. Bedömningen av antagandena finns i [antaganden.md](antaganden.md).

## Slutavverkning, en leveransmånad: AO00046, GRAN_SAG

- **Bestånd:** slutavverkning i region mellan, 3,056 stockar, 761 m3fub på 2 avlägg.
- **Planerad destination:** SAG_GROV. **Faktisk:** SAG_GROV.
- **Skördarrapport:** 2026-05, 2026-06.
- **Svinn:** 0 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 16/05–24/05 | 1526 | 345 | 24.7 | 11/07–15/07 | 8 | 54 |
| 2 | 24/05–02/06 | 1530 | 416 | 26.6 | 06/07–11/07 | 10 | 41 |

Inmätt: 18 leveranser, 763.1 m3fub brutto och 756.2 netto, mot 761.0 som faktiskt kom fram och 757.3 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-07 | 756.2 | 100% | 0% | 0% | 24.6 | 24.8 | 0.02 |

Över hela arbetsordern: felindex 0.02 för diameterfördelningen.

## Slutavverkning över ett månadsskifte: AO00070, TALL_SAG

- **Bestånd:** slutavverkning i region mellan, 4,507 stockar, 1062 m3fub på 1 avlägg.
- **Planerad destination:** SAG_KLEN. **Faktisk:** SAG_KLEN.
- **Skördarrapport:** 2026-08, 2026-09.
- **Svinn:** 0 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 16/08–05/09 | 4507 | 1062 | 25.0 | 21/09–09/10 | 24 | 34 |

Inmätt: 24 leveranser, 1059.7 m3fub brutto och 1051.3 netto, mot 1061.9 som faktiskt kom fram och 1049.2 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-09 | 580.4 | 100% | 0% | 0% | 23.8 | 24.1 | 0.03 |
| 2026-10 | 470.9 | 94% | 6% | 0% | 23.8 | 24.0 | 0.05 |

Över hela arbetsordern: felindex 0.03 för diameterfördelningen.

## Gallring: AO00088, TALL_SAG

- **Bestånd:** gallring i region sodra, 2,423 stockar, 233 m3fub på 4 avlägg.
- **Planerad destination:** SAG_KLEN. **Faktisk:** SAG_KLEN.
- **Skördarrapport:** 2026-10, 2026-11.
- **Svinn:** 27 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 24/10–29/10 | 592 | 41 | 14.4 | 15/12–15/12 | 1 | 49 |
| 2 | 29/10–03/11 | 592 | 59 | 17.1 | 04/12–08/12 | 2 | 35 |
| 3 | 03/11–08/11 | 619 | 71 | 18.1 | 28/11–01/12 | 2 | 24 |
| 4 | 08/11–12/11 | 620 | 61 | 17.0 | 09/12–13/12 | 2 | 30 |

Inmätt: 7 leveranser, 229.6 m3fub brutto och 227.7 netto, mot 229.7 som faktiskt kom fram och 242.0 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-11 | 43.7 | 100% | 0% | 0% | 16.2 | 17.1 | 0.12 |
| 2026-12 | 184.0 | 100% | 0% | 0% | 16.2 | 15.6 | 0.07 |

Över hela arbetsordern: felindex 0.04 för diameterfördelningen.

## Utan skördardata: AO00076, GRAN_SAG

- **Bestånd:** slutavverkning i region mellan, 3,247 stockar, 935 m3fub på 1 avlägg.
- **Planerad destination:** SAG_GROV. **Faktisk:** SAG_GROV.
- **Skördarrapport:** saknas helt.
- **Svinn:** 45 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 23/09–05/10 | 3247 | 935 | 27.3 | 12/10–21/10 | 21 | 17 |

Inmätt: 21 leveranser, 922.5 m3fub brutto och 913.3 netto, mot 923.8 som faktiskt kom fram och 949.7 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-10 | 913.3 | 0% | 0% | 100% | 26.3 | 26.3 | 0.11 |

Över hela arbetsordern: felindex 0.11 för diameterfördelningen.

## Sen skördarrapport: AO00080, TALL_SAG

- **Bestånd:** slutavverkning i region sodra, 1,637 stockar, 439 m3fub på 2 avlägg.
- **Planerad destination:** SAG_GROV. **Faktisk:** SAG_GROV.
- **Skördarrapport:** 2026-10, 2026-11.
- **Svinn:** 7 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 14/09–24/09 | 840 | 213 | 25.8 | 21/10–25/10 | 5 | 35 |
| 2 | 24/09–04/10 | 797 | 225 | 27.1 | 15/10–20/10 | 6 | 18 |

Inmätt: 11 leveranser, 433.7 m3fub brutto och 429.1 netto, mot 436.7 som faktiskt kom fram och 451.7 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-10 | 429.1 | 85% | 15% | 0% | 25.6 | 25.5 | 0.04 |

Korrigeringar: 2026-11: 14.2 m3fub flyttade mellan klasser

Över hela arbetsordern: felindex 0.04 för diameterfördelningen.

## Omdirigerad till annat sågverk: AO00083, TALL_SAG

- **Bestånd:** slutavverkning i region mellan, 3,704 stockar, 966 m3fub på 3 avlägg.
- **Planerad destination:** SAG_MIX. **Faktisk:** SAG_KLEN.
- **Skördarrapport:** 2026-10.
- **Svinn:** 163 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 16/10–20/10 | 1249 | 308 | 25.6 | 16/11–22/11 | 7 | 32 |
| 2 | 20/10–24/10 | 1240 | 268 | 24.2 | 01/12–06/12 | 6 | 43 |
| 3 | 24/10–28/10 | 1215 | 390 | 28.6 | 22/11–30/11 | 9 | 31 |

Inmätt: 22 leveranser, 926.0 m3fub brutto och 916.7 netto, mot 924.0 som faktiskt kom fram och 1005.2 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Lånat (S3) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|---|
| 2026-11 | 661.4 | 100% | 0% | 0% | 25.8 | 26.3 | 0.04 |
| 2026-12 | 255.4 | 100% | 0% | 0% | 25.8 | 23.2 | 0.20 |

Över hela arbetsordern: felindex 0.03 för diameterfördelningen.

## Flödet som helhet

Simulering med frö 71, 12 månader, efter 2 månaders inkörning.

| Storhet | Simulatorn |
|---|---|
| Tid från fällning till leverans per m3fub, 10/50/90 % | 19 / 31 / 52 dagar |
| Medeltid enligt Littles lag, lager delat med flöde | 34 dagar |
| Skördetid per arbetsorder, median | 15 dagar |
| Från sista fällning till första lass, median | 17 dagar |
| Leveranskampanj, median | 15 dagar |
| Volym per arbetsorder och sortiment, slutavverkning, median | 851 m3fub |
| Volym per arbetsorder och sortiment, gallring, median | 115 m3fub |
| Lass per arbetsorder och sortiment, median | 15 |
| Bruttovolym per leverans, median | 44.5 m3fub |
| Andel arbetsordrar som levererar i två månader eller fler | 47% |
| Andel stockar som når sågverk efter skördarens rapportmånad | 87% |
