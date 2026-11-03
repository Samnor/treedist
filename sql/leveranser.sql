/*
Leveransmätningar för en månad i det format `treedist run --leverans` läser.

Källa: DMSKOGSRORELSEN.dbo.fLeveransaggregatVolym. Nycklarna är surrogatnycklar (SN). De
fungerar som de är så länge skördardatan använder samma nycklar för arbetsorder och
handelssortiment; annars behöver de översättas via dimensionstabellerna.

Handelssortimentet är det inmätta, som faktureras. Producerat sortiment är det skördaren
apterade och som skördardatan förs på; virke som klassats om vid inmätningen dras ur det
producerade sortimentets lager men faktureras som inmätt.

Månaden bestäms av RedovisningDatum. Transportdatum får ligga tidigare.

Antaganden att bekräfta med kontrollfrågorna längst ned:
  - ÄrVederlagsgrundande = 'J' betyder att raden ligger till grund för betalning.
  - Netto- och bruttokolumnerna är vederlagsmätt volym. Virke som bara är ankomstmätt
    tas med först den månad det vederlagsmäts och ligger kvar i lagret till dess.
  - Vrak och avdrag ingår i brutto men inte i netto. Vraket lämnar då lagret utan att
    faktureras.
  - Sortiment utan volym i m3fub, till exempel energived i ton eller MWh, tas inte med.
*/

DECLARE @Period char(7) = '2026-01';
DECLARE @Start date = CAST(@Period + '-01' AS date);
DECLARE @Slut date = DATEADD(month, 1, @Start);

SELECT
    CONCAT(LeveransnummerSN, '')               AS leverans_id,
    CONCAT(ArbetsorderSN, '')                  AS arbetsorder,
    CONCAT(InmättHandelssortimentSN, '')       AS handelssortiment,
    CONCAT(ProduceratHandelssortimentSN, '')   AS producerat_handelssortiment,
    CONCAT(MottagningsplatsSN, '')             AS mottagningsplats,
    MIN(TransporteratDatum)                    AS leveransdatum,
    SUM(ISNULL(NettoLeveransaggregatM3FUB, 0)) AS volym_m3fub,
    SUM(BruttoLeveransaggregatM3FUB)           AS brutto_m3fub
FROM dbo.fLeveransaggregatVolym
WHERE RedovisningDatum >= @Start
  AND RedovisningDatum < @Slut
  AND ÄrVederlagsgrundande = N'J'
  AND BruttoLeveransaggregatM3FUB > 0
GROUP BY LeveransnummerSN, ArbetsorderSN, InmättHandelssortimentSN, ProduceratHandelssortimentSN,
         MottagningsplatsSN
ORDER BY leverans_id, arbetsorder, handelssortiment;


/*
Arbetsordrar för `--arbetsordrar`. Grupp är produktionsområdet.

ERSÄTT destinationen: den planerade destinationen finns i arbetsordertabellen och ska hämtas
därifrån, med samma nyckel som MottagningsplatsSN. Frågan nedan tar arbetsorderns största
mottagningsplats i väntan på det. Den saknar arbetsordrar som ännu inte levererat något, och
deras skörd redovisas då utan destination.
*/

WITH Volym AS (
    SELECT ArbetsorderSN, ArbetsorderProduktionsområdeSN, MottagningsplatsSN,
           SUM(BruttoLeveransaggregatM3FUB) AS brutto
    FROM dbo.fLeveransaggregatVolym
    WHERE ÄrVederlagsgrundande = N'J' AND BruttoLeveransaggregatM3FUB > 0
    GROUP BY ArbetsorderSN, ArbetsorderProduktionsområdeSN, MottagningsplatsSN
), Rangordnad AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY ArbetsorderSN ORDER BY brutto DESC) AS nr
    FROM Volym
)
SELECT CONCAT(ArbetsorderSN, '')                 AS arbetsorder,
       CONCAT(MottagningsplatsSN, '')            AS destination,
       CONCAT(ArbetsorderProduktionsområdeSN, '') AS grupp
FROM Rangordnad
WHERE nr = 1;


/* ---------------------------------------------------------------------------------
Kontrollfrågor. Kör dem en gång på ett år av data och skicka resultatet.
--------------------------------------------------------------------------------- */

-- 1. Vilka värden har flaggorna, och hur mycket volym bär de?
SELECT ÄrVederlagsgrundande, ÄrVrak, MätningstypASN, MåttslagskvalitetASN,
       COUNT(*) AS rader,
       SUM(BruttoLeveransaggregatM3FUB) AS brutto,
       SUM(NettoLeveransaggregatM3FUB) AS netto,
       SUM(AnkomstmättEjVederlagsmättBruttoM3FUB) AS ej_vederlagsmatt
FROM dbo.fLeveransaggregatVolym
WHERE RedovisningDatum >= '2025-01-01'
GROUP BY ÄrVederlagsgrundande, ÄrVrak, MätningstypASN, MåttslagskvalitetASN
ORDER BY brutto DESC;

-- 2. Går brutto ihop med netto, vrak och avdrag?
SELECT SUM(BruttoLeveransaggregatM3FUB) AS brutto,
       SUM(NettoLeveransaggregatM3FUB) AS netto,
       SUM(VrakM3FUB) AS vrak,
       SUM(AvdragM3FUB) AS avdrag,
       SUM(BruttoLeveransaggregatM3FUB - NettoLeveransaggregatM3FUB
           - ISNULL(VrakM3FUB, 0) - ISNULL(AvdragM3FUB, 0)) AS rest,
       SUM(CASE WHEN NettoLeveransaggregatM3FUB > BruttoLeveransaggregatM3FUB THEN 1 ELSE 0 END)
           AS rader_netto_over_brutto
FROM dbo.fLeveransaggregatVolym
WHERE RedovisningDatum >= '2025-01-01' AND ÄrVederlagsgrundande = N'J';

-- 3. Hur ofta skiljer sig producerat, inmätt och fördelat sortiment åt?
SELECT CASE WHEN InmättHandelssortimentSN = ProduceratHandelssortimentSN
            THEN 'samma' ELSE 'olika' END AS producerat_mot_inmatt,
       CASE WHEN InmättSortimentSSTESN = FördeladSortimentSSTESN
            THEN 'samma' ELSE 'olika' END AS inmatt_mot_fordelat,
       COUNT(*) AS rader,
       SUM(BruttoLeveransaggregatM3FUB) AS brutto
FROM dbo.fLeveransaggregatVolym
WHERE RedovisningDatum >= '2025-01-01' AND ÄrVederlagsgrundande = N'J'
GROUP BY CASE WHEN InmättHandelssortimentSN = ProduceratHandelssortimentSN
              THEN 'samma' ELSE 'olika' END,
         CASE WHEN InmättSortimentSSTESN = FördeladSortimentSSTESN
              THEN 'samma' ELSE 'olika' END;

-- 4. Hur många dagar ligger transport före redovisning?
SELECT DATEDIFF(day, TransporteratDatum, RedovisningDatum) AS dagar,
       SUM(BruttoLeveransaggregatM3FUB) AS brutto
FROM dbo.fLeveransaggregatVolym
WHERE RedovisningDatum >= '2025-01-01' AND ÄrVederlagsgrundande = N'J'
GROUP BY DATEDIFF(day, TransporteratDatum, RedovisningDatum)
ORDER BY dagar;

-- 5. Hur stor del av volymen saknar m3fub, är import eller köpvirke?
SELECT ÄrImport,
       CASE WHEN VirkesköpkontraktSN > 0 THEN 'köpvirke' ELSE 'eget' END AS ursprung,
       LeveransaggregatUMåttslagSN,
       COUNT(*) AS rader,
       SUM(CASE WHEN BruttoLeveransaggregatM3FUB IS NULL THEN 1 ELSE 0 END) AS rader_utan_m3fub,
       SUM(BruttoLeveransaggregatM3FUB) AS brutto
FROM dbo.fLeveransaggregatVolym
WHERE RedovisningDatum >= '2025-01-01' AND ÄrVederlagsgrundande = N'J'
GROUP BY ÄrImport, CASE WHEN VirkesköpkontraktSN > 0 THEN 'köpvirke' ELSE 'eget' END,
         LeveransaggregatUMåttslagSN
ORDER BY brutto DESC;
