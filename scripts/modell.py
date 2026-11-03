"""Saved models: a named set of parameters to switch back to, and how complicated each is.

A model is a TOML file in modeller/ that `--config` reads directly, with a
[modell] table saying what it is, which code it was saved with and how it did.
Complexity is the number of parts in PARTS that the model uses: each rule and
each number a reader must know to follow an estimate. Bookkeeping every model
needs for a correct invoice (reversed loads, corrections, reclassification,
destinations, write-offs) is not counted. Performance is how much of the gap to
the naive estimate, the month's harvest, the model closes, as a share of what
the standard model closes, on the climb's development seeds. The search asks
for that share in every scenario, not only on average.

    uv run python scripts/modell.py lista
    uv run python scripts/modell.py delar --config modeller/enkel.toml
    uv run python scripts/modell.py spara NAMN --beskrivning "..." [--config FIL] [--set k=v] [--utvardera]
    uv run python scripts/modell.py sok --delar 0.2 --prestanda 0.8
    uv run treedist run ... --config modeller/NAMN.toml
"""

from __future__ import annotations

import argparse
import json
import time
import tomllib
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, fields, replace
from pathlib import Path

import pandas as pd
from climb import DEV_SEEDS, HOLDOUT_SEEDS, _git, _parse, evaluate, log

from treedist.config import Config, load_config

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "modeller"
DEFAULT = Config()


def _sibling(c: Config) -> bool:
    return c.donor_sibling_cm > 0


def _intervals(c: Config) -> bool:
    return c.intervals


def _finite(c: Config) -> bool:
    return c.intervals and c.finite_population


def _donors(c: Config) -> bool:
    return c.intervals and c.donor_draws


def _volume(c: Config) -> bool:
    return c.intervals and c.volume_error


# Name, kind, what it does, whether a config uses it.
PARTS = [
    ("liggare", "regel", "Lager per arbetsorder och sortiment förs mellan månaderna och leveransen dras ur det",
     lambda c: True),
    ("brutto", "regel", "Bruttovolymen lämnar lagret, nettovolymen faktureras", lambda c: c.draw_gross),
    ("harvester_bias", "parameter", "Skördarens överskattning", lambda c: c.harvester_bias != 0),
    ("handling_loss", "parameter", "Svinn mellan skördare och industri", lambda c: c.handling_loss != 0),
    ("aldst_forst", "regel", "Äldst först när leveranserna börjar före skördens slut", lambda c: c.oldest_first),
    ("S2", "regel", "Leverans utöver lagret fördelas som arbetsorderns historik", lambda c: c.history_fallback),
    ("S3", "regel", "Virke utan skördardata lånar ett volymviktat medel av sortimentets arbetsordrar", lambda c: True),
    ("donor_destination_weight", "parameter", "Givare med samma destination väger mer",
     lambda c: c.donor_destination_weight != 1),
    ("donor_group_weight", "parameter", "Givare i samma grupp väger mer", lambda c: c.donor_group_weight != 1),
    ("syskon", "regel", "Givare viktas efter hur väl de passar syskonsortimentets grovlek", _sibling),
    ("donor_sibling_cm", "parameter", "Minsta bandbredd för syskonvikten", _sibling),
    ("pool_min_pairs", "parameter", "Antal par som krävs för syskonvikten", _sibling),
    ("S4", "regel", "Sortiment helt utan skördardata bokas på OKÄND", lambda c: True),
    ("dirichlet", "regel", "Intervall: brus kring fördelningen efter effektivt antal stockar", _intervals),
    ("design_effect", "parameter", "Stockar per oberoende stock", _intervals),
    ("andlighet", "regel", "Bruset minskar ju större del av skörden som levererats", _finite),
    ("pool_remaining_share", "parameter", "Antagen kvarvarande andel för S2 och S3", _finite),
    ("default_log_volume", "parameter", "Medelstockvolym när antal saknas", _intervals),
    ("hel_givare", "regel", "S3 i Monte Carlo: en hel givare per dragning", _donors),
    ("volymfel", "regel", "Volymens mätfel per leverans och metod", _volume),
    ("unit_cv", "parameter", "Mätfel per enhet, per metod", _volume),
    ("systematic_sd", "parameter", "Systematiskt fel per metod", _volume),
    ("default_units", "parameter", "Antal enheter när det saknas, per metod", _volume),
]

# Everything that can be left out, and the settings that leave it out. The search adds groups back.
MINIMAL = {
    "draw_gross": False,
    "harvester_bias": 0.0,
    "handling_loss": 0.0,
    "oldest_first": False,
    "history_fallback": False,
    "donor_destination_weight": 1.0,
    "donor_group_weight": 1.0,
    "donor_sibling_cm": 0.0,
    "intervals": False,
}
GROUPS = {
    "brutto": ["draw_gross"],
    "kalibrering": ["harvester_bias", "handling_loss"],
    "aldst_forst": ["oldest_first"],
    "S2": ["history_fallback"],
    "destination": ["donor_destination_weight"],
    "grupp": ["donor_group_weight"],
    "syskon": ["donor_sibling_cm"],
    "intervall": ["intervals"],
    # Only meaningful with intervals on: the parts that a light interval model leaves out.
    "andlighet": ["finite_population"],
    "hel_givare": ["donor_draws"],
    "volymfel": ["volume_error"],
}
# Intervals from the noise around the composition alone: three parts instead of ten.
LIGHT_INTERVALS = {"intervals": True, "finite_population": False, "donor_draws": False, "volume_error": False}


def parts(cfg: Config) -> list[str]:
    return [name for name, _, _, used in PARTS if used(cfg)]


def _config(overrides: dict) -> Config:
    return replace(Config(), **overrides)


def _overrides(cfg: Config) -> dict:
    """The fields that differ from today's defaults."""
    return {f.name: getattr(cfg, f.name) for f in fields(Config)
            if f.name != "volume_methods" and getattr(cfg, f.name) != getattr(DEFAULT, f.name)}


def performance(results: list[pd.DataFrame]) -> list[dict]:
    """Price error and the share of the standard's gain over the naive estimate, the first result being the standard."""
    standard = results[0]
    gain = (standard["prisfel_naiv"] - standard["prisfel"]).mean()
    rows = []
    for result in results:
        closed = result["prisfel_naiv"] - result["prisfel"]
        per_scenario = (closed.groupby(result["scenario"]).mean()
                        / (standard["prisfel_naiv"] - standard["prisfel"]).groupby(standard["scenario"]).mean())
        rows.append({
            "prisfel": round(float(result["prisfel"].mean()), 2),
            "prisfel_naiv": round(float(result["prisfel_naiv"].mean()), 2),
            "prestanda": round(float(closed.mean() / gain), 3),
            "prestanda_per_scenario": per_scenario.round(3).to_dict(),
            "varde_90": None if result["varde_90"].isna().all() else round(float(result["varde_90"].mean()), 3),
            "poang": None if result["poang"].isna().all() else round(float(result["poang"].mean()), 3),
        })
    return rows


def _toml_value(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def save(name: str, cfg: Config, description: str, results: dict | None) -> Path:
    used = parts(cfg)
    values = asdict(cfg)
    methods = values.pop("volume_methods")
    lines = [f"# Modell {name}. Kör med --config modeller/{name}.toml; se scripts/modell.py.", ""]
    lines += [f"{key} = {_toml_value(value)}" for key, value in values.items()]
    for method, numbers in methods.items():
        lines += ["", f"[volume_methods.{method}]", *(f"{k} = {_toml_value(v)}" for k, v in numbers.items())]
    meta = {
        "namn": name,
        "beskrivning": description,
        "kod": _git(),
        "sparad": time.strftime("%Y-%m-%d"),
        "delar": len(used),
        "delar_av": len(PARTS),
        "anvanda_delar": used,
        # TOML has no null: a measure the model lacks, such as coverage without intervals, is left out.
        **{k: v for k, v in (results or {}).items() if v is not None},
    }
    lines += ["", "[modell]"]
    for key, value in meta.items():
        if isinstance(value, dict):
            continue
        lines.append(f"{key} = {_toml_value(value)}")
    for key, value in meta.items():
        if isinstance(value, dict):
            lines += ["", f"[modell.{key}]", *(f"{_toml_value(k)} = {_toml_value(v)}" for k, v in value.items())]
    MODELS.mkdir(exist_ok=True)
    path = MODELS / f"{name}.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _evaluate(configs: list[dict]) -> list[pd.DataFrame]:
    with ProcessPoolExecutor() as pool:
        return evaluate(pool, configs, DEV_SEEDS)


def command_save(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    cfg = replace(cfg, **_parse(args.set))
    results = None
    if args.utvardera:
        standard, model = performance(_evaluate([{}, _overrides(cfg)]))
        results = {**model, "standardens_prisfel": standard["prisfel"]}
        with ProcessPoolExecutor() as pool:
            _, control = performance(evaluate(pool, [{}, _overrides(cfg)], HOLDOUT_SEEDS))
        results |= {"kontroll_prisfel": control["prisfel"], "kontroll_prestanda": control["prestanda"],
                    "kontroll_varde_90": control["varde_90"],
                    "kontroll_prestanda_per_scenario": control["prestanda_per_scenario"]}
    path = save(args.namn, cfg, args.beskrivning, results)
    print(f"Sparad: {path.relative_to(ROOT)}, {len(parts(cfg))} av {len(PARTS)} delar")


def command_parts(args: argparse.Namespace) -> None:
    cfg = replace(load_config(args.config), **_parse(args.set))
    used = set(parts(cfg))
    for name, kind, text, _ in PARTS:
        print(f"{'x' if name in used else ' '} {name:26s} {kind:9s} {text}")
    print(f"{len(used)} av {len(PARTS)} delar, {len(used) / len(PARTS):.0%}")


def command_list(args: argparse.Namespace) -> None:
    for path in sorted(MODELS.glob("*.toml")):
        text = path.read_text(encoding="utf-8")
        # A model saved for older code keeps its description in the first comment line instead.
        meta = tomllib.loads(text).get("modell", {"beskrivning": text.splitlines()[0].lstrip("# ")})
        performance_share = meta.get("prestanda")
        print(f"{path.stem:24s} kod {meta.get('kod', '?'):16s} {meta.get('delar', '?'):>2}/{meta.get('delar_av', '?')} delar"
              f"  prisfel {meta.get('prisfel', '–')}  prestanda {performance_share if performance_share is not None else '–'}"
              f"  {meta.get('beskrivning', '')}")


def command_search(args: argparse.Namespace) -> None:
    """Forward selection from the smallest model: add the group that gains most per part, within the budget."""
    budget = args.delar * len(PARTS)
    chosen = {**MINIMAL, **(LIGHT_INTERVALS if args.intervall else {}), **_parse(args.start)}
    # With intervals the climb's score ranks the additions, so that calibration counts as well as price.
    measure = "poang" if chosen.get("intervals") else "prisfel"
    remaining = {name: group for name, group in GROUPS.items()
                 if any(chosen.get(f, getattr(DEFAULT, f)) != getattr(DEFAULT, f) for f in group)}
    trail = []
    while True:
        # Every group is measured, so the cost of leaving out each one is known; only those within budget can be taken.
        candidates = {name: {**chosen, **{f: getattr(DEFAULT, f) for f in group}} for name, group in remaining.items()}
        names = list(candidates)
        results = performance(_evaluate([{}, chosen, *candidates.values()]))
        standard, current, *added = results
        size = len(parts(_config(chosen)))
        trail.append({"modell": dict(chosen), "delar": size, **current})
        log({"typ": "modell", "kandidat": chosen, "delar": size, **current})
        print(f"\n{size} delar ({size / len(PARTS):.0%}): prisfel {current['prisfel']} mot standard "
              f"{standard['prisfel']} och naivt {current['prisfel_naiv']}, prestanda {current['prestanda']:.1%}, "
              f"poäng {current['poang']} mot {standard['poang']}, värde inom 90 % {current['varde_90']}"
              f"  {current['prestanda_per_scenario']}")
        for name, result in zip(names, added):
            extra = len(parts(_config(candidates[name]))) - size
            log({"typ": "modell", "kandidat": candidates[name], "delar": size + extra, **result})
            print(f"  + {name:12s} {extra} delar: prisfel {result['prisfel']}, prestanda {result['prestanda']:.1%}, "
                  f"poäng {result['poang']}, värde inom 90 % {result['varde_90']}  {result['prestanda_per_scenario']}")
        # Gain per part: lower score or price error, or the extra performance share.
        sign = -1 if measure == "poang" else 1
        key = "poang" if measure == "poang" else "prestanda"
        rate = {n: sign * (r[key] - current[key]) / max(len(parts(_config(candidates[n]))) - size, 1)
                for n, r in zip(names, added) if len(parts(_config(candidates[n]))) <= budget}
        # Every scenario must reach the target: an average can hide one we are unsure of in reality.
        if min(current["prestanda_per_scenario"].values()) >= args.prestanda or not rate:
            break
        best = max(rate, key=rate.get)
        if rate[best] <= 0:
            break
        print(f"  Tar {best}.")
        chosen = candidates[best]
        del remaining[best]
    print(f"\nResultat: {len(parts(_config(chosen)))} av {len(PARTS)} delar, prestanda {trail[-1]['prestanda']:.1%}, "
          f"ändringar mot standard: {_overrides(_config(chosen))}")
    (ROOT / "climb" / f"{args.ut}.json").write_text(json.dumps(trail, indent=2, ensure_ascii=False) + "\n",
                                                     encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    keep = commands.add_parser("spara", help="Spara en modell i modeller/")
    keep.add_argument("namn")
    keep.add_argument("--beskrivning", required=True)
    keep.add_argument("--config", type=Path)
    keep.add_argument("--set", action="append", default=[], metavar="NYCKEL=VÄRDE")
    keep.add_argument("--utvardera", action="store_true", help="Mät prisfel och prestanda på utvecklings- och kontrollfrön")
    show = commands.add_parser("delar", help="Vilka delar en modell använder")
    show.add_argument("--config", type=Path)
    show.add_argument("--set", action="append", default=[], metavar="NYCKEL=VÄRDE")
    commands.add_parser("lista", help="Sparade modeller")
    search = commands.add_parser("sok", help="Minsta modellen som når en andel av standardens prestanda")
    search.add_argument("--delar", type=float, default=0.2, help="Högst denna andel av delarna")
    search.add_argument("--prestanda", type=float, default=0.8, help="Minst denna andel av prestandan i varje scenario")
    search.add_argument("--intervall", action="store_true", help="Börja med lätta intervall, tre delar, och rangordna efter poäng")
    search.add_argument("--start", action="append", default=[], metavar="NYCKEL=VÄRDE", help="Ändra startmodellen")
    search.add_argument("--ut", default="sok_modell", help="Filnamn i climb/ för sökvägen")
    args = parser.parse_args()
    {"spara": command_save, "delar": command_parts, "lista": command_list, "sok": command_search}[args.command](args)


if __name__ == "__main__":
    main()
