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
| Live / current-state | tasks-live/ (51) | 68% | The real discriminator. |
| Building / exec | scenarios/ (11) | 100% | Only Fable has run. See below. |

## The gap to fix first

The building track has been run against **one model** (Fable). Everything
saved in `exec-results/` is Fable. "Saturated" is a one-data-point claim. The
broken fixtures prove bad code fails; they don't show how the model field
spreads. Fix the measurement before making anything harder.

## Plan, in order

0. **Done 2026-09-02 (free):** `run_scenario.py --seeds 1,2,3 --repeat N`
   and `harness/exec_report.py` (pass rate per model x scenario). Live runs
   now carry a manifest hash + mode; `run_live_eval.py --report` groups them
   and parks the four old runs as legacy (they ran on 17/22/50 tasks — the
   68% vs 41% comparison was never apples to apples).
1. **Repeat runs before new scenarios.** Fable x5 on the same seed of three
   scenarios. One 100 is not a pass rate. If it's 3/5 anywhere, the headroom
   already exists and the honest number is pass@1. Needs Austin's ok.
2. **Haiku on all 11.** The old answer-injection track already shows
   Haiku 3/7 vs Sonnet/Opus 7/7, so expect Sonnet-and-up to ace these. Run
   Haiku only until that's disproven. No runner exists for GPT/Grok (the
   harness needs a CLI agent; `codex` could stand in for GPT).
3. **Rerun the live track on all four models** on the same 51 tasks so the
   numbers compare. Note the closed-book live track measures training
   cutoff, not skill; it's the base for the ethskills A/B, not the "can it
   build" number.
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
