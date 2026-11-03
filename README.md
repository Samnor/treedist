# TreeDistributionSimulator

Tar fram matriser per destination och handelssortiment som beskriver hur månadens levererade virke fördelar sig över
diameter och längd, utifrån mätningar av olika säkerhet, och ett fakturaunderlag per destination.

Skördardatan, skördarens produktionsrapportering, vet fördelningen men mäter vid avverkning. Inmätningen vid industri
vet volymen, brutto och netto, men inget om dimensioner. Leveransen kommer dessutom efter skörden, så månadens skörd beskriver inte månadens leveranser. Därför
håller `treedist` en liggare över skördat men olevererat virke per arbetsorder och fördelar leveransvolymen utifrån den.

- [Metod](docs/metod.md): hur det fungerar, parametrar och begränsningar
- [Metodjämförelse](docs/metodjamforelse.md): tre metoder, akademiska begrepp och jämförelse med forskningen
- [Underlag för simulering](docs/simuleringsunderlag.md): vad årsredovisningar och Biometria säger om data
- [Exempelresor](docs/exempelresor.md) och [antaganden](docs/antaganden.md): virkets väg från skördare till sågverk,
  och hur rimliga antagandena är
- [AGENTS.md](AGENTS.md): hur en ny datakälla kopplas in, skrivet så att en modell kan göra det
- [Portabilitet](docs/portabilitet.md): hur väl en enklare modell kopplar in nya källor, och vad `check` fångar

## Kom igång

Installera med [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Stäng en månad med exempeldatat:

```bash
uv run treedist run --period 2026-01 --skordning examples/demo/skordning_2026-01.csv --leverans examples/demo/leverans_2026-01.csv --prislista examples/demo/prislista.csv --avslutade-ao examples/demo/avslutade_ao_2026-01.csv --arbetsordrar examples/demo/arbetsordrar.csv --state state --out out/2026-01
```

Har källsystemet ett eget format beskrivs det i en TOML-fil i stället för fem filargument, och `check` prövar
datan mot kontraktet och mot rimliga värden innan något körs:

```bash
uv run treedist check --period 2026-01 --kalla examples/kalla/kalla.toml
```

```bash
uv run treedist run --period 2026-01 --kalla examples/kalla/kalla.toml --state state --out out/2026-01
```

Månader körs i följd eftersom varje månad bygger vidare på föregående liggare i `state/`. Att köra om senaste månaden
är säkert: den utgår från liggaren före. Saknas en månad, eller finns senare månader, stoppas körningen.

Utvärdera metoden mot simulerat facit, och skapa egen syntetisk indata:

```bash
uv run treedist backtest --manader 12
```

```bash
uv run treedist simulate --out examples/egen --manader 6
```

Klättra mot en bättre metod, en bedömd ändring i taget. Varje kandidat jämförs med den bästa hittills på samma
simuleringar och tas bara om skillnaden är större än bruset. Utvecklingsfrön används för besluten och kontrollfrön för
att pröva resultatet. Försöken loggas i `climb/logg.jsonl`, och processen för strukturella ändringar beskrivs i
[.claude/skills/metod-klattring](.claude/skills/metod-klattring/SKILL.md).

```bash
uv run python scripts/climb.py params --budget 30
```

```bash
uv run python scripts/climb.py holdout
```

En förenkling tar bort en del i stället för att lägga till en, och får kosta lite. `forenkla` prövar flera
borttagningar mot samma baslinje; varje steg får kosta högst 0,25 i poäng och en hel klättring högst 1,0.

```bash
uv run python scripts/climb.py forenkla donor_group_weight=1 'design_effect=100,pool_min_pairs=5'
```

Sparade modeller ligger i [modeller/](modeller), en TOML-fil per modell som `--config` läser direkt, med kod,
antal delar och resultat i tabellen `[modell]`. Byt modell genom att ange en annan fil, till exempel
`--config modeller/enkel.toml`: 4 av 23 delar och 92 % av standardmodellens förbättring mot den naiva skattningen,
men utan intervall. `modeller/halv.toml` har 9 av 23 delar, 99 % av förbättringen och lätta intervall, och `modeller/halv-volym.toml`
samma med 8 delar och utan att läsa antal stockar, se
[metodjämförelsen](docs/metodjamforelse.md#en-femtedel-av-delarna).

```bash
uv run python scripts/modell.py lista
```

```bash
uv run python scripts/modell.py spara NAMN --beskrivning "vad som ändrats" --utvardera
```

[Flödesrapporten](docs/flodesrapport.html) visar demons månader steg för steg som en graf, från indata via liggaren,
dragningen och säkerhetsklasserna till matriser, faktura och facit. Klicka på ett steg för detaljerna. Skapa den på
nytt efter en ändring i metoden, eller för annan data med `--data` eller `--kalla` och `--perioder`:

```bash
uv run python scripts/flodesrapport.py
```

Kör testerna:

```bash
uv run pytest
```

## Arkitektur

Metoden ändras inte när den flyttas till ny data. Det som ändras är en adapter som översätter källans format till
fem kanoniska tabeller.

```
källans export ──> adapter ──> kanoniska tabeller ──> kärna ──> matriser och faktura
                   (ändras)    contract.py                       ▲
                                                                 └── osäkerhet, valfri
```

| Del | Innehåll | Ändras vid flytt |
|---|---|---|
| `adapters/` | Kanoniska CSV-filer, TOML-mappning eller egen `.py` | Ja, genom en ny källbeskrivning |
| `contract.py` | De fem tabellerna: kolumner, krav, enhet, rimliga värden, betydelse | Nej |
| `check.py` | Formkontroll, rimlighetskontroller och provkörning utan att spara | Nej |
| `core/` | Liggare, fördelning, matriser och faktura. Deterministisk | Nej |
| `uncertainty/` | Monte Carlo-intervall. Stängs av med `intervals = false` | Nej |
| `dev/` | Simulator och utvärdering. Behövs inte i drift | Nej |

Profilen [enkel](examples/profil_enkel.toml) kör utan Monte Carlo: fakturan och matriserna blir desamma, men
spridning och intervall saknas. Säkerhetsklasserna visar fortfarande hur säker fördelningen är. Golden-testet i
`tests/test_portability.py` kontrollerar att demons fakturor och matriser inte ändras av omstruktureringar, och
liggaren sparar sin kontraktsversion så att en gammal liggare inte läses med ett nytt format.

## Indata

CSV med en rad per observation, eller källans egna filer genom en adapter. `uv run treedist kontrakt` skriver ut
tabellerna med enhet, rimliga värden och betydelse. Decimalkomma och decimalpunkt fungerar båda.

**Skördardata** (`--skordning`). Månadens nya rader ur en tabell utan dubbletter. En rad får bara förekomma i en månad.

| Kolumn | Krav | Beskrivning |
|---|---|---|
| `arbetsorder` | Ja | |
| `handelssortiment` | Ja | |
| `diametergrupp` | Ja | Klassbotten i cm. Tom för sortiment utan klasser |
| `langdgrupp` | Ja | Klassbotten i cm. Tom för sortiment utan klasser |
| `volym_m3fub` | Ja | |
| `antal_stockar` | Nej | Ger bättre osäkerhetsskattning |
| `avverkningsdatum` | Nej | Får vara tidigare än perioden, annars antas perioden |

**Inmätning vid industri** (`--leverans`). Per lastbil eller summerat per arbetsorder och sortiment. Får inte innehålla diameter- eller
längdgrupp.

| Kolumn | Krav | Beskrivning |
|---|---|---|
| `arbetsorder` | Ja | |
| `handelssortiment` | Ja | Inmätt sortiment, det som faktureras |
| `producerat_handelssortiment` | Nej | Sortimentet i skördardatan, om virket klassats om vid inmätningen. Annars samma som inmätt |
| `volym_m3fub` | Ja | Nettovolym, det som faktureras. Negativ på en rad som vänder ett lass, med samma tecken på brutto |
| `brutto_m3fub` | Nej | Används för lagret. Annars antas samma som netto |
| `mottagningsplats` | Nej | Faktisk destination. Annars används den planerade |
| `leverans_id` | Nej | Lastbilens leveransnummer. Ett lass får ha flera arbetsordrar och sortiment |
| `leveransdatum` | Nej | Transportdatum. Får vara före perioden om lasset redovisas månaden efter. Saknas det antas månadens slut |
| `matmetod` | Nej | `stockmatning`, `travmatning`, `vagning`, `skordarmatning` eller `okand` |
| `antal_matenheter` | Nej | Antal stockar eller travar i leveransen |

**Prislista.** Halvöppna intervall `[min, max)` på klassbottnar, tomt betyder öppet.

| Kolumn | Beskrivning |
|---|---|
| `handelssortiment` | |
| `diameter_min`, `diameter_max` | |
| `langd_min`, `langd_max` | |
| `pris_kr_per_m3fub` | |
| `destination` | Valfri. Regler med destination ersätter de allmänna för den destinationen |

Överlappande regler stoppar körningen. En regel utan gränser är en reservregel som bara gäller där inget annat matchar.
Priserna i exempeldatat är påhittade.

**Avslutade arbetsordrar**, valfritt: en kolumn `arbetsorder`. Kvarvarande lager skrivs av och underskott blir
slutgiltiga.

**Arbetsordrar**, via `--arbetsordrar`: kolumnerna `arbetsorder` och `destination`, plus `grupp` om region och
avverkningsform finns. Virke utan skördardata lånar fördelning från liknande arbetsordrar, viktade efter destination,
grupp och arbetsorderns andra sortiment. Skörd och lager redovisas på den planerade destinationen.

**Konfiguration**, valfritt: en TOML-fil till `--config` med parametrarna i [docs/metod.md](docs/metod.md).
`intervals = false` ger profilen enkel.

## Utdata

```
out/2026-01/
  fakturor/<destination>.md          fakturaunderlag per destination
  faktura_rader.csv                  alla leveransrader och korrigeringar
  sammanfattning.md                  volymer och andel per säkerhetsklass
  matriser/<destination>/<sortiment>/*.csv   matriser med diameter som rader, längd som kolumner
  matriser_lang.csv                  samma matriser i långt format
  leverans_ao_lang.csv               fördelningen per arbetsorder och säkerhetsklass
  korrigeringar_ao_lang.csv          korrigeringar av tidigare månader
  avstamning_ao.csv                  lagerbalans per arbetsorder och sortiment
  manifest.json                      parametrar och kontrollsummor för indatan
```

Matriserna per destination och sortiment:

| Fil | Innehåll |
|---|---|
| `levererat` | Bästa skattning, m3fub. Summerar till nettovolymen hos destinationen |
| `levererat_S1` … `levererat_S4` | Samma volym uppdelad efter säkerhet. Summerar till `levererat` |
| `andel` | Andel av sortimentets levererade volym |
| `std_fordelning` | Spridning vid fast volym, alltså osäkerheten i fakturans fördelning |
| `std`, `p05`, `p95` | Spridning och 90 %-intervall inklusive volymmätningens fel |
| `skordat_ra` | Månadens skördarrapport utan kalibrering, på planerad destination |
| `lager_utgaende` | Skördat men inte levererat vid månadens slut, på planerad destination |
| `korrigering` | Omfördelning av tidigare preliminära volymer |
| `pris`, `varde` | Pris och värde per cell |

## Säkerhetsklasser

| Klass | Fördelningen kommer från | Status |
|---|---|---|
| S1 | AO:ns eget skördarlager | Slutlig |
| S2 | AO:ns skördehistorik, när mer levererats än lagret räcker till | Preliminär |
| S3 | Andra arbetsordrar i samma sortiment | Preliminär |
| S4 | Inget, bokas på `OKÄND` | Preliminär, debiteras bara med uttrycklig prisregel |

Fakturans volym är alltid inmätningens. När skördardata kommer in i efterhand rättas den preliminära fördelningen
med `KORRIGERING`-rader på nästa faktura. Deras volym går jämnt ut medan värdet kan bli plus eller minus.

## Viktigt att veta

Metoden är bara prövad mot simulerad data. Där placerar den cirka 5,5 % av volymen fel per månad, destination och sortiment,
mot 17 % för att bara använda månadens skörd. Värdeintervallet träffar 87–93 % mot nominellt 90 %, och flera parametrar
bygger på antaganden. Ange `mottagningsplats` om den finns: omdirigerat virke som bokas på planerad destination nästan
fördubblade felet i simuleringen. Se [begränsningarna](docs/metod.md#medvetna-begränsningar) innan siffrorna används skarpt.
