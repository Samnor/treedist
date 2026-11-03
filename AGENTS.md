# Instruktion: koppla treedist till en ny datakälla

Den här filen är skriven för en modell eller en person som ska få `treedist` att läsa data från ett nytt
system. Uppgiften är nästan alltid att beskriva källans format, inte att ändra metoden.

## Vad du får ändra

- **En källbeskrivning.** Helst en `.toml`-mappning, se [examples/kalla/kalla.toml](examples/kalla/kalla.toml).
  Bara om mappningen inte räcker, till exempel när tabeller måste slås ihop, en `.py`-fil med
  `read(period) -> dict[str, DataFrame]`. Lägg den i en egen katalog, till exempel `kallor/<system>/`.
- **En konfigurationsfil** till `--config`, till exempel [examples/profil_enkel.toml](examples/profil_enkel.toml).

## Vad du inte får ändra

`src/treedist/core/`, `src/treedist/contract.py`, `src/treedist/schema.py`, `src/treedist/uncertainty/` och
`tests/golden/`. De är metoden och dess facit. Om du tror att något där måste ändras: stanna och fråga en person.
Ett test som slutar fungera ska inte skrivas om för att passera.

## Arbetsgång

1. `uv sync` och sedan `uv run pytest -q`. Allt ska passera innan du börjar.
2. `uv run treedist kontrakt` skriver ut de fem tabellerna med krav, enhet, rimliga värden och betydelse.
   Läs kolumnen Betydelse noga.
3. Kopiera `examples/kalla/kalla.toml` och fyll i källans filer och kolumnnamn.
4. Kör tills inget `FEL` återstår:

   ```bash
   uv run treedist check --period 2026-01 --kalla kallor/system/kalla.toml
   ```

   Varje `VARNING` ska antingen rättas eller förklaras för en person. Med `--state` provkörs månaden mot
   liggaren utan att något sparas.
5. Kör månaderna i ordning, först med profilen enkel:

   ```bash
   uv run treedist run --period 2026-01 --kalla kallor/system/kalla.toml --state state --out out/2026-01 --config examples/profil_enkel.toml
   ```

## Fallgropar som ger fel siffror utan felmeddelande

| Fråga | Rätt | Vanligt fel |
|---|---|---|
| Vilken volym är `volym_m3fub`? | Nettovolym som faktureras, fast under bark | Brutto, eller volym på bark (m3to, m3sk). Bark kan inte räknas om med en fast faktor |
| Vad är `brutto_m3fub`? | Volymen som lämnade avlägget, före avdrag | Samma kolumn som netto |
| Vad är `diametergrupp`? | Klassens nedre gräns i cm, till exempel 24 | Millimeter (240), eller klassens mitt (25) |
| Vad är `leveransdatum`? | Dagen lasset kördes | Redovisningsdatum eller mätdatum en annan månad |
| Vilket sortiment är `handelssortiment` i inmätningen? | Det inmätta, som faktureras | Det skördaren producerade. Det hör hemma i `producerat_handelssortiment` |
| Vilken destination? | `mottagningsplats` är den faktiska, `arbetsordrar.destination` den planerade | Planerad destination i `mottagningsplats` |
| Är arbetsorder-id samma i båda källorna? | Ja, exakt samma sträng | Inledande nollor eller prefix som skiljer. `check` visar det som hög andel S3 |

## Klart betyder

- `treedist check` visar inget `FEL`, och varje `VARNING` är rättad eller förklarad.
- `uv run pytest -q` passerar.
- En körd månad visar fakturerad volym per destination och sortiment lika med inmätningen. Körningen
  stoppar själv om det inte stämmer.
