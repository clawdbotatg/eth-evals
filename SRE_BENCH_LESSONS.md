# What eth-evals takes from SRE-Bench

Status: **design only, nothing below is built** (2026-09-03). Item 0 shipped.

SRE-Bench (Columbia, arXiv 2608.11469, sre-bench.lol) grades agents on
reverse-engineering private binaries. Different domain, same problem as ours:
the top model saturates, the next tier ties, and one number per model tells
you nothing. These are the parts worth copying, in the order to build them.

## 0. Effort next to every score — DONE (commit 2d7b0da)

Every result row carries turns, cost, tokens, API seconds. Two models that
tie on score split on effort. Gap: only `claude -p` reports it. The codex
wrapper needs its `--json` event stream parsed the same way.

## 1. Difficulty axes: run each scenario several ways

**The idea.** SRE-Bench compiles each program 16 ways (optimized or not,
symbols or stripped, static or dynamic, 8 protection presets). Same task,
controlled difficulty. Their headline result was not a score. It was which
axis hurts: stripping symbols costs half a point, optimization is free,
protections halve the top model and zero the rest.

**Our version.** A scenario stays one `scenario.py`. It gains a `variants`
list. Each variant is a named set of switches applied at `workspace_files`
and `setup_chain` time. Candidate axes for Ethereum:

| Axis | Easy | Hard |
|---|---|---|
| source | verified Solidity in workspace | bytecode only, no source |
| interface | ABI file given | no ABI, agent must recover selectors |
| indirection | direct contract | behind a proxy (1967 / minimal clone / diamond) |
| token | plain ERC-20 | fee-on-transfer, no-return-value (USDT-style), rebasing, 6-dec |
| chain | local anvil, clean state | pinned mainnet fork with prior state |
| noise | only the relevant contracts | decoy contracts with similar names |
| help | bare model | model + ethskills (or any skill pack) |

Not every axis applies to every scenario. Start with `source`, `interface`,
`token`, and `help`. Those four cover most of what a real builder hits.

**Grading does not change.** The hidden grader reads chain state either way.
Variants only change what the agent is given.

**Reporting.** Score per (model, scenario, variant). Then the delta per axis
averaged over scenarios: "bytecode-only costs Fable 22 points, Opus 40."
That sentence is the product.

**Exit criteria.** Reference solves every variant at 100. Each broken
fixture still fails for its reason on every variant. `test_exec.py` gains
one loop over variants per scenario.

**Cost.** Each axis roughly doubles run count for that scenario. Pick the
two or three axes per scenario that matter. Budget before running.

## 2. Three numbers, not one

SRE-Bench reports per model: mean score, share fully solved, share scored
zero. Zero rate was 16 to 83 percent across models, which told them tasks
are mostly pass/fail and partial credit hides that.

We have milestone points already. `report.py` and the arena page should show
for the exec track: **score** (mean milestone share), **solved** (share at
max), **zero** (share at 0). A high zero rate on a scenario says the first
milestone is the wall. A low solved rate with a high score says the last
milestone is. Both are calibration signals, and free.

## 3. A hidden scenario set

SRE-Bench's programs were never public and it only publishes what a cheap
model could recover from the binary in under 200 requests. They checked.

Our CTF scenarios port public BuidlGuidl challenges. Per-run seeding keeps
the answers fresh but the structure is in training data. Plan:

- Keep two or three scenarios in a private repo, same layout, same
  `test_exec.py` gate, never committed here.
- Results from hidden scenarios are reported with the scenario name only.
- The public suite says which scenarios are hidden and how many milestones
  each has, nothing else.
- When a hidden scenario's top score creeps past 90 percent, promote it to
  public and write a new hidden one. Saturation is the rotation signal.

Do this before publishing any leaderboard, not after.

## 4. Repeats and variance, which they lack

SRE-Bench ran every model once, no confidence intervals. We already know a
50-task closed-book run moves 3 tasks between repeats. Keep the repeat
support in `run_scenario.py --repeat` and report pass rate over repeats for
exec, not one score. This is a place we are ahead. Don't give it up.

## 5. Publishing: versioned JSON with a shared validator

Their site is static: `data/results/v0.json`, `models.json`,
`variants.json`, and one `check-data.mjs` that validates with the same pure
functions the page renders with. Publishing a new version is copying a file.

Ours is close. The arena already tails an append-only `events.jsonl` and
publishing a run is copying that file. What's missing:

- A results version tied to the manifest hash, so the page can refuse to
  mix runs from different manifests.
- A `models.json` with display names and orgs.
- A validator script run in the test gate.

Build this when there is a run worth publishing, not before.

## 6. Contribution rules, if we ever open it up

SRE-Bench's contribute page is a good template: code never public,
last commit before a cutoff date, behavior auto-verifiable, several
independently graded tasks per target, reproducible transforms with
documented configs. Their team builds the binaries and writes the graders
themselves; contributors only supply the program.

Our equivalent: contributors supply a contract system and a reference
solution. We write the milestones and the broken fixtures. A "protection"
contribution is a reproducible variant transform (item 1), not a task.

## What not to copy

- Single runs. See item 4.
- Dropping refusals and context errors from the average. That flatters
  models that bail. We count them as failures and abort on an outage.
- 500 steps and 6 hours per attempt. Our scenarios should stay under 15
  minutes. A long budget hides cost differences; effort capture shows them.

## Order

1 (variants, starting with source/interface/token/help) → 2 (three numbers)
→ 3 (hidden set) → 5 (publish). Item 4 is a rule, not work. Item 6 waits.
None of this runs a model. Real runs still need Austin's ok.
