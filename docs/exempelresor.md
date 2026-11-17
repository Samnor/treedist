# Exempelresor från skördning till leverans

Genererad av [example_journeys.py](../scripts/example_journeys.py) ur simulatorn. Varje resa visar vad som hände
med stockarna och vad `treedist` skattade utan att se dem. Diametrar är klassbottnar, volymviktade. Felindex är
andelen volym i fel diameterklass. Bedömningen av antagandena finns i [antaganden.md](antaganden.md).

## En leveransmånad: AO00041, TALL_SAG

- **Skörd:** 2,743 stockar, 618 m3fub på 4 avlägg.
- **Planerad destination:** SAG_MIX. **Faktisk:** SAG_MIX.
- **Skördarrapport:** 2026-05.
- **Svinn:** 0 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 03/05–06/05 | 682 | 161 | 25.0 | 09/05–12/05 | 4 | 6 |
| 2 | 06/05–09/05 | 706 | 213 | 27.8 | 14/05–18/05 | 5 | 8 |
| 3 | 09/05–12/05 | 702 | 102 | 20.3 | 19/05–22/05 | 3 | 10 |
| 4 | 12/05–15/05 | 653 | 142 | 24.1 | 23/05–26/05 | 4 | 11 |

Inmätt: 16 leveranser, 618.1 m3fub brutto och 610.1 netto, mot 617.6 som faktiskt kom fram och 626.2 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|
| 2026-05 | 610.1 | 99% | 1% | 24.6 | 24.5 | 0.04 |

Över hela avtalsobjektet: felindex 0.04 för diameterfördelningen.

## Över ett månadsskifte: AO00083, GRAN_SAG

- **Skörd:** 2,096 stockar, 647 m3fub på 1 avlägg.
- **Planerad destination:** SAG_GROV. **Faktisk:** SAG_GROV.
- **Skördarrapport:** 2026-10, 2026-11.
- **Svinn:** 0 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 26/10–16/11 | 2096 | 647 | 28.1 | 20/11–09/12 | 15 | 23 |

Inmätt: 15 leveranser, 648.2 m3fub brutto och 640.7 netto, mot 647.0 som faktiskt kom fram och 663.3 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|
| 2026-11 | 354.6 | 100% | 0% | 27.8 | 27.5 | 0.05 |
| 2026-12 | 286.1 | 100% | 0% | 27.8 | 27.8 | 0.07 |

Över hela avtalsobjektet: felindex 0.03 för diameterfördelningen.

## Sen skördarrapport: AO00022, GRAN_SAG

- **Skörd:** 2,049 stockar, 633 m3fub på 1 avlägg.
- **Planerad destination:** SAG_GROV. **Faktisk:** SAG_GROV.
- **Skördarrapport:** 2026-03, 2026-04.
- **Svinn:** 12 stockar kom aldrig fram.

| Avlägg | Fälld | Stockar | m3fub | Medeldiameter, cm | Levererad | Lass | Dagar på avlägg, median |
|---|---|---|---|---|---|---|---|
| 1 | 07/03–21/03 | 2049 | 633 | 28.1 | 19/04–10/05 | 15 | 46 |

Inmätt: 15 leveranser, 630.0 m3fub brutto och 624.4 netto, mot 629.0 som faktiskt kom fram och 634.2 enligt skördaren.

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|
| 2026-04 | 354.9 | 100% | 0% | 27.5 | 27.5 | 0.05 |
| 2026-05 | 269.6 | 97% | 3% | 27.5 | 27.7 | 0.07 |

Över hela avtalsobjektet: felindex 0.03 för diameterfördelningen.

## Omdirigerad till annat sågverk: AO00039, TALL_SAG

- **Skörd:** 3,102 stockar, 724 m3fub på 4 avlägg.
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

| Månad | Levererat netto | Från eget lager (S1) | Från historik (S2) | Skattad medeldiameter | Verklig | Felindex diameter |
|---|---|---|---|---|---|---|
| 2026-05 | 710.8 | 100% | 0% | 24.8 | 24.8 | 0.02 |

Över hela avtalsobjektet: felindex 0.02 för diameterfördelningen.

## Flödet som helhet

Simulering med frö 71, 12 månader, efter 2 månaders inkörning.

| Storhet | Simulatorn |
|---|---|
| Tid från fällning till leverans per m3fub, 10/50/90 % | 8 / 18 / 34 dagar |
| Medeltid enligt Littles lag, lager delat med flöde | 18 dagar |
| Skördetid per avtalsobjekt, median | 15 dagar |
| Från sista fällning till första lass, median | 6 dagar |
| Leveranskampanj, median | 15 dagar |
| Volym per avtalsobjekt och sortiment, median | 613 m3fub |
| Lass per avtalsobjekt och sortiment, median | 15 |
| Bruttovolym per leverans, median | 44.5 m3fub |
| Andel avtalsobjekt som levererar i två månader eller fler | 44% |
| Andel stockar som når sågverk efter skördarens rapportmånad | 59% |
