# eth-eval — next-steps plan

Defensive benchmark. It measures how well an LLM does Ethereum work in three
sections: concepts, transactions, building. The security scenarios are graded
tests of whether a model can find and fix known contract flaws. No live
targets, no real funds. Full state is in `CLAUDE.md`, `PURPOSE.md`, `GOAL.md`.

## Read this first (why this doc stays plain)

An earlier handoff doc packed exploit write-ups into one file and tripped an
automated content filter on load. Keep this doc in neutral eval language:
name each scenario and say what it TESTS, not how to carry an attack out. The
step-by-step mechanics live in each `scenarios/*/scenario.py`, next to the
grader, where they read as test fixtures. Don't move them back up here.

## Where each track stands

| Track | Files | Fable | Note |
|---|---|---|---|
| Concepts | tasks/ (242) + tasks-tools/ (33) | ~98% | Saturated. Maintenance. |
| Live / current-state | tasks-live/ (51) | 76% | Ranks the field. See below. |
| Building / exec | scenarios/ (11) | 100% | 32/32 perfect runs. Haiku 6/11. |

## Measured 2026-09-02 (runs 1-3 of the plan below)

Live closed-book, all four on the same 50 tasks, manifest `dbcf62f7d2`
(raw files in gitignored `results-live/`, `run_live_eval.py --report`):

| model | passed | rate |
|---|---|---|
| Fable | 38/50 | 76% |
| Opus | 35/50 | 70% |
| Sonnet | 21/50 | 42% |
| Haiku | 16/50 | 32% |

Every model is 0/4 on `live-read` (current block / gas) — unknowable
closed-book, so those should be flagged `closed_book: false`. Cost
calibration is 1/7 at best. Addresses and tx calldata are what separate
the tiers.

Exec (`harness/exec_report.py`): **Fable 32/32 perfect runs** including
5x repeats on gas-golf, ctf-advanced, dvd-balancer-rounding — pass@1 is
100%, saturation is real, not a one-sample artifact. **Haiku 6/11 perfect,
mean 83.** Haiku loses every transaction scenario (extra txs, dangling
approvals, wrong end state — 60/50/90) and two security puzzles
(ctf-advanced 50, readonly-reentrancy 60: drained the vault at a loss).
It aces the build scenarios and three of four public-challenge ports.

Timing caveat: `elapsed_s` is wall clock and this laptop slept during the
late runs (pmset log shows sleep/darkwake around 01:14), so the 53-min and
37-min dvd-balancer-rounding entries are not model time. Clean numbers:
Fable 3-4 min there, Haiku 13 min on ctf-advanced (awake). Run sweeps
under `caffeinate -i` next time. Time-to-solve still looks like a signal
the score misses; report it, but only from awake runs.

## Plan, in order

0. **Done 2026-09-02:** runs 1-3 measured (table above). Tooling: `run_scenario.py --seeds 1,2,3 --repeat N`
   and `harness/exec_report.py` (pass rate per model x scenario). Live runs
   now carry a manifest hash + mode; `run_live_eval.py --report` groups them
   and parks the four old runs as legacy (they ran on 17/22/50 tasks — the
   68% vs 41% comparison was never apples to apples).
1. ~~Repeat runs~~ done: Fable 15/15 on repeats. No pass@1 headroom.
2. ~~Haiku on all 11~~ done: 6/11. The track ranks the floor. Sonnet/Opus
   not run (expected to ace; the old answer-injection track had them 7/7).
   No runner exists for GPT/Grok (`codex` could stand in for GPT).
3. ~~Live rerun~~ done, table above. Next: mark the 4 `live-read` tasks
   agent-only; report elapsed time next to pass rate on the exec track;
   run sweeps under `caffeinate -i` so elapsed means something.
4. **Build one long multi-step task — with a hidden adversarial suite.** The
   0.95^10 math assumes no feedback. An agent with `forge test` fixes each
   step, so errors only compound where it can't verify. Design: build a
   small system to a spec on a fork; grade with a hidden functional suite
   AND a hidden attack suite (reuse the existing scenarios' attack code as
   the attackers). Solving a public puzzle is recall; shipping code that
   survives attack is skill. Grow the live track as a side task.

## Don't

- **Don't shrink the time/turn budget to force failures.** That measures
  working under a starved budget, not Ethereum skill. It's a trick; the rules
  say no tricks.
- **Don't add more single-shot security puzzles expecting new headroom.** A
  model that authors the puzzle can solve it. Fable solved the Puppet port
  in under a minute, twice — recall, not reasoning. Attack the agent's own
  code instead.

## Done checks (all free, run before claiming anything works)

```
python3 run_eval.py --self-test
python3 run_eval.py --self-test --track tools
python3 test_graders.py
python3 run_live_eval.py --self-test
python3 test_exec.py
python3 report.py
python3 harness/exec_report.py       # pass rates, not single scores
python3 run_live_eval.py --report    # live runs grouped by manifest
```
