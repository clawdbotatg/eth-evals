# ethskills-evals — what it is and what it means for eth-eval

Written 2026-09-04 after reading https://github.com/BuidlGuidl/ethskills-evals
(HEAD `928975d`, 285 commits, active that week). Read this before touching the
"ethskills with/without A/B" item in `CLAUDE.md` loose ends. Nothing here has
been run by us; it is a read of their repo.

## One paragraph

BuidlGuidl's eval for the ethskills library (https://ethskills.com). It asks one
question per skill: does the model already pass without the skill? Every task
runs in two arms, `no_skill` and `with_skill`, 3 runs each, fresh Claude Code or
Codex process per run. A blind LLM judge grades prose `expect:` lines against
the workspace output. It is built on their `skill-eval-framework`. There is no
runner binary. You open `claude` or `codex` in the repo and the agent
orchestrates from `AGENTS.md`.

## Size at HEAD

| Thing | Count |
| --- | ---: |
| Tasks (`tasks/*.yaml`) | 101 |
| Skills under test | 19 |
| Reports (`reports/*.md`) | 60 |
| Mistake records (`mistakes/`) | 102 |
| Harness code (TypeScript) | ~3.2k lines |

Skills: addresses, audit, building-blocks, concepts, frontend-playbook,
frontend-ux, gas, indexing, l2s, noir, orchestration, protocol, qa, security,
ship, standards, testing, tools, wallets.

## How a benchmark runs

Three guarded scripts. Always all three. The rulebook is `AGENTS.md`.

```bash
yarn setup        --task tasks/<id>.yaml --variant no_skill|with_skill --run <n> --executor claude|codex
yarn run-executor --run artifacts/<id>/<run-id> --model <model>
yarn verify       --run artifacts/<id>/<run-id> --judge-agent claude|codex --judge-model <model>
```

- `setup` builds a workspace OUTSIDE the repo (`~/.cache/ethskills-evals/<run-id>/<task-id>/`
  or `EVAL_WORKSPACE_ROOT`), seeds it as its own git repo with a baseline
  commit, drops `TASK.md` and optionally a template. Hard-fails if any grading
  material would leak in. For `with_skill` it copies the skill to
  `.agents/skills/<name>/` (codex native) plus `.claude/skills/<name>/` (claude).
- `run-executor` spawns the agent on `TASK.md` only. Claude runs with
  `--setting-sources project`; codex gets a private `CODEX_HOME` and
  `--disable shell_snapshot`. A killed executor is a dead run, not a zero.
- `verify` snapshots output (`run.diff` against the baseline, or `output/`),
  runs a fresh blind judge, writes `result.yaml`, deletes the workspace.

Three roles, any mix of Claude Code and Codex: orchestrator, executor, judge.
Hard rules from `AGENTS.md`: the orchestrator never does the task itself; the
executor never sees the expect lines; runs are append-only (a re-run is a new
run id); grade only after the executor finished; one stack per benchmark, a
second stack is a separate report.

## Task spec

```yaml
skill: skills/gas          # vendored skill dir, pinned commit
input: |                   # executor prompt, identical across variants
template: templates/se-2   # optional workspace seed
expect:                    # judged conditions, the whole grading surface
  - "..."
runs: 3
status: live | retired
notes: free text
```

Two task shapes, and the split between them is the whole method:

- **quiz** = "knows when asked." A question with the concept named.
- **goal** = "applies unprompted." A build task where the discipline has to
  surface on its own. Example: `addresses-goal-001` asks for a viem script that
  swaps large USDC into WETH on Base. Nothing mentions addresses, venues, or
  verification. Seven expect lines then grade native vs bridged USDC, the exact
  Base deployment addresses, venue choice justified by Base liquidity, a written
  verify-before-funds instruction, and calling the right router within the venue.

Their keep-the-skill verdict needs quiz passing both arms AND goal splitting
(`no_skill` fails, `with_skill` passes). A goal that passes both arms means one thing: the
model already has the habit.

## Grading

- The judge gets the task input, the numbered expect lines, and the captured
  evidence. Prompt: "You are grading a coding-agent run. You are blind to the
  variant and skill." Returns strict JSON per condition. `pass` for the run =
  every expect line passed.
- Judge is chosen per benchmark. Usually the same model that executed;
  `result.yaml` then says `self_judged: true` and the report has to say so.
- **Regrade, don't re-run.** Editing an expect line and re-judging saved
  evidence is `yarn verify --regrade --reason "..."`. Writes a separate
  `<run-id>-regrade-<n>/result.yaml` with `regrade_of` pointing back. The source
  record is not touched and does not know it was superseded, so only the report
  says which reading a table is on. `expect_sha` fingerprints the rubric a grade
  was made against. Rewording `input:` is NOT regradeable (`input_sha` guards
  it): that needs a fresh baseline in both arms.
- `retracted: <reason>` marks a grade that measured the harness, not the model.
  Kept, excluded from counts.
- `yarn run-stats` reads a `## run stats` footer from transcripts for cost
  tables. Older runs lack it; those reports read `usage` blocks by hand.

## What they found

Numbers from the latest reports. Pass = all expect lines.

| Skill (report) | Stack | no_skill | with_skill | Note |
| --- | --- | ---: | ---: | --- |
| security (2026-08-31) | codex gpt-5.4 | 16/24 | 22/24 | goal-001 vault 0/3 to 3/3. All no-skill builds shipped first-depositor-vulnerable share math. Tokens +59%. |
| testing (2026-09-01) | codex gpt-5.6 | 13/18 | 15/18 | 0 of 6 goal runs chose fuzzing or invariants, even after reading a skill that says to. |
| gas minimal (2026-08-31 regrade) | codex + claude judge | 1/12 | 9/12 | goal-001 was 3/3, went to 0/3 once the rubric demanded an actual measurement. |
| addresses (2026-08-18) | claude opus-5 | 2/3 | 3/3 | goal-001. The one no-skill fail was missing a written verify-before-funds note. |

Patterns across the 60 reports:

1. Skills help on goal tasks, barely on quizzes. Top models already know the
   concept when asked. The lift is in habit, not knowledge.
2. Early wins evaporated under stricter rubrics. The gas regrade is the clean
   example. Judge-on-prose grading is only as good as the expect lines.
3. Cost goes up with the skill. They report tokens and median duration next to
   score. Durations are measured under contention (4 runs at a time) and they
   say so.
4. Codex hit the cyber refusal on security goal tasks after doing the work.
   Those runs were deleted and re-run, not counted. Same thing we saw in the
   Fable vs GPT-5.6 race report.
5. Codex default model was recorded as `null` in YAML for a whole benchmark.
   Pass `--model` explicitly.

## The mistakes loop

`mistakes/<skill>/<id>.yaml` is a failure record: symptom, expected pattern,
which skill section, frequency per arm, status. It feeds back into the skill.
Best example: `addresses-aerodrome-slipstream-missing`. The skill listed
Aerodrome's v2 router. Base USDC/WETH depth is in Slipstream, a different
router with a different ABI (tickSpacing, not fee). A run quoted both at a
500k clip: v2 router filled 1283 bps below mid, Slipstream 14 bps. Every
address was genuine, so `eth_getCode` passed. Fix: the addresses skill went
from 547 lines of address tables to a short verification-and-venue discipline
with no tables, and the task got a new expect line for router-within-venue.

Several skills were cut to "minimal" versions the same way (gas is 38 lines).
The `*-minimal-*` reports compare old vs reduced skill.

## How this relates to eth-eval

Different question. They measure skill lift. We measure model ability.

| | ethskills-evals | eth-eval (us) |
| --- | --- | --- |
| Question | does the skill help | can the model build on Ethereum |
| Arms | no_skill vs with_skill | model vs model |
| Grading | LLM judge on prose expect lines | deterministic: regex/bigint graders, chain state via JSON-RPC, `forge test` |
| Runs per cell | 3 | 1 per task, 50+ tasks |
| Chain | real Base/mainnet reads inside the agent, nothing broadcast | dedicated anvil per attempt, pinned forks via proxy |
| Effort | tokens + duration in reports | turns/cost/tokens per row (`harness/agent_io.py`) |
| Workspace | outside repo, own git, skill dropped in | temp dir, env scrubbed, hidden grading |

Overlap worth knowing:

- Their `security-goal-001` (permissionless vault) is the same first-depositor
  bug as our `vault-exploit-patch` scenario. They show no-skill Codex ships it
  3/3; we could show whether a given model catches and patches it.
- Their quiz tasks overlap our closed-book categories (addresses, l2s, gas,
  security, standards). Ours are saturated at ~98%; theirs pass both arms too.
  Same finding from two directions.
- Their addresses-goal-001 is a stronger "applies unprompted" test than any of
  our tasks-live address checks. Worth borrowing the shape.

## What we could do with it

The deferred A/B in `CLAUDE.md` ("ethskills with/without, expensive, build
after the execution pack is calibrated") is exactly what this repo does. We
have a cleaner grader. The cheap version, no new infra:

1. Add a `--skill <dir>` option to `harness/run_scenario.py` that copies a
   SKILL.md into the workspace at `.claude/skills/<name>/` before the agent runs.
2. Vendor the matching ethskills skill per scenario: security for
   `vault-exploit-patch`, addresses or gas for `fork-swap`, standards for
   `erc2612-permit`, testing for `repo-repair`.
3. Run each scenario N seeds with and without. Report score/solved/zero per arm
   plus cost. That is the SRE-Bench triple from `SRE_BENCH_LESSONS.md`.

Rule 1 in `CLAUDE.md` still applies: no model runs without Austin's ok.

## Gotchas if we borrow their skills

- **Their gas skill tells agents to use public RPCs** (`publicnode`,
  `mainnet.base.org`, `eth.drpc.org`). That is their content, not our code. If
  we inject it into a scenario, either strip those lines or accept that the
  agent may hit a public RPC from inside the workspace. Our `rpc_policy.py`
  only governs our own upstreams.
- Skills end with a "send feedback via feedback/SKILL.md" line. Harmless, but
  it is a network call the agent may attempt.
- Skills are pinned per commit in their `skills/` dir. Pin ours the same way and
  record the sha next to results, or the manifest guarantee is meaningless.
- Their isolation is not a sandbox: same uid, `$HOME` above the workspace,
  sibling runs visible two dirs up. Ours is the same. Neither fixes it.

## Where to look

- Repo: https://github.com/BuidlGuidl/ethskills-evals
- Rulebook: `AGENTS.md` (288 lines, the schemas are in there)
- Judge prompt: `lib/judge.ts` around line 169
- Best task to read: `tasks/addresses-goal-001.yaml` (the notes explain the
  quiz/goal method)
- Best mistake to read: `mistakes/addresses/addresses-aerodrome-slipstream-missing.yaml`
- Best reports: `reports/security-2026-08-31.md`, `reports/gas-minimal-2026-08-31.md`
  (the regrade story), `reports/testing-2026-09-01.md`
- Framework it sits on: https://github.com/BuidlGuidl/skill-eval-framework
- Skills source: https://ethskills.com/<name>/SKILL.md
