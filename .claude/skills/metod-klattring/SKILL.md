---
name: metod-klattring
description: Hill climb treedist's method one judged change at a time with scripts/climb.py. Use when asked to "klättra", "hill climb", "iterera fram en bättre metod", "förbättra metoden", or to report what the climb has done so far.
---

# Metodklättring

Each step tries ONE change to the method, judges it against the current best on the same
simulations, keeps it only if it is better by more than the noise, and records the result.
The point is a trail of small, explained decisions, not one big rewrite.

## Before the first step

1. `uv run python scripts/climb.py status` shows the current best and the latest entries.
2. Read `climb/logg.jsonl` and the experiment table in `docs/metodjamforelse.md`, so an idea
   already tried is not tried again unless something it depends on has changed.
3. Run `uv run pytest -q`; never climb from a red suite.

## One step

1. **Pick one hypothesis** and write down, in a sentence, why it should lower the price error or
   improve calibration. Good sources: the remaining weaknesses in `docs/metodjamforelse.md`, the
   example journeys in `docs/exempelresor.md`, and diagnostics such as z-scores of the value
   interval per certainty tier. A parameter that only moves a number goes to `params` instead.
2. **Implement it behind a Config field** whose default keeps today's behaviour (a flag that is
   off, or a parameter at its neutral value). Add a test that the new path does what it claims.
3. **Judge it:** `uv run python scripts/climb.py compare --set <field>=<value> --note "<hypothesis>"`.
   It runs best and candidate on the same development seeds and prints the paired difference in
   score, its standard error and the price error per scenario. A change counts only if it beats
   the noise by two standard errors and gains at least 0.05.
4. **Better:** make the new value the default in `config.py`, update `docs/metod.md` and the
   experiment table in `docs/metodjamforelse.md`, regenerate the flow report with
   `uv run python scripts/flodesrapport.py`, save the new standard with
   `uv run python scripts/modell.py spara standard-<date> --beskrivning "..." --utvardera` so the
   previous one stays reachable, run the tests, and commit with a message that
   starts `Klättring:`. Then rerun `compare` with no `--set` once, to confirm the new default is
   the new baseline. The step stays in the log.
   **Not better:** revert the code (`git checkout -- src tests`), keep the log entry, and add a
   line to the experiment table only if the result teaches something.
5. Tell the user in one or two lines what was tried and what was decided.

## Parameters

`uv run python scripts/climb.py params --budget 30` climbs the parameters listed in `PARAMS`
automatically, coordinate by coordinate, halving the steps when a full round finds nothing.
The best set is written to `climb/basta.json` and `climb/basta.toml`; it does not change
`config.py`. Moving it into the defaults is a step of its own, done only after `holdout` holds.

## Checking

After every three taken steps, and always before moving parameters into the defaults:
`uv run python scripts/climb.py holdout`. It compares the best against today's defaults on
eight control seeds that no decision has used. A structural step changes the defaults
themselves, so check it against the settings that switch it off:
`holdout --mot <flag>=false`, one `--mot` per step since the last check. If the gain
does not hold there, say so and undo the steps since the last check that held.

## Simplifying

A simplification removes a part instead of adding one, and is judged by what it costs, not
what it gains. Put the removal behind a flag as usual and screen several at once with
`uv run python scripts/climb.py forenkla <k=v[,k=v]> ...`: each costs at most 0.25 in score
(`SIMPLIFY_TOLERANCE`), and a whole simplification climb at most 1.0 (`SIMPLIFY_BUDGET`) from
where it started. Combine the acceptable ones and screen the combination, since removals that
each widen or narrow the intervals add up. Check it with `holdout` with the combination saved
as best, and accept a cost there within the budget. Then delete the code and the parameters,
not just the flags: a removal that is only switched off has simplified nothing. Every result
of the 2026-11-03 simplification is in the experiment table in `docs/metodjamforelse.md`.

## Rules

- Use only inputs the real data has. The delivery measurement gives gross and net volume per
  work order or truck, with no dimensions and no log count; the simulator emits
  `antal_matenheter` only for the volume error model. A step that reads anything else the
  simulator knows is rejected however much it gains (the delivered mean log volume gained
  4.96 and was rejected for this reason).
- Decisions use the development seeds only. Never pick or tune anything from control results.
- One change per step. Do not change the simulator in the same step as the method: a better
  score must come from the method, not from easier data.
- Leave source-based calibration (`harvester_bias`, `handling_loss`, the volume error model)
  out of the climb; the simulator was built from the same numbers, so climbing them only fits it.
- Everything is judged against a simulator. A gain that relies on how the simulator links size
  and mill is a weaker gain; the scenario where destination is unrelated to size is there to
  show it. Say so when a step wins mainly in the other scenarios.
- A comparison takes about a minute and a parameter round about fifteen; run long climbs in the
  background and do not poll.

## Where the error is (2026-11-03, after oldest-first draws; still true after the simplification)

Swapping one part of the allocation for the truth, base scenario, development seeds: knowing
exactly which logs left, in harvester classes, only takes the price error from 7.3 to 6.1. The
rest of S1's error is the harvester's own diameter error, which no method can remove without
dimensions at the mill. S3 is about 11 % of the volume but about 3 kr/m3fub of the error, and
most of it when 30 % lacks harvester data. S2 is under 1 % of the volume. Aim at S3 and at the
uncertainty model before anything else.

## Ideas not yet tried

- Weight donors by how close their harvest dates are to the work order's. The simulator has
  no seasonal difference in size, so it cannot judge this; it needs real data.
- Use every sibling assortment, not only the first. The simulator has two assortments, so
  this is a no-op here.
- Shrink a small work order's history toward its donors' (S2). Under 1 % of the volume in the
  simulator, so hardly worth a step.
