# eth-evals — orientation for the next agent

Benchmark for "can an AI actually build on Ethereum." Two halves today:
a **closed-book knowledge quiz** (saturated — top models ~98%) and a new
**execution harness** that grades agents on real chain state. `README.md` is
the public overview; `NEXT_STEPS_REPORT.md` is the full v2 design (read it
before adding anything big). This file is what you actually need to not
break things.

## Hard rules

1. **NO model runs without Austin's explicit ok.** Every real run costs money
   and lands in results. Self-tests, `test_exec.py`, and scripted
   reference/fixture runs are free and always fine. When Austin says go, see
   "Running a sweep" below.
2. **Never a public RPC.** `harness/rpc_policy.py` enforces Alchemy-only for
   upstreams; keep it that way. `ALCHEMY_API_KEY` lives in gitignored `.env`.
3. **Never commit keys.** The only 64-hex constants in the repo are the
   secp256k1 curve order in `scenarios/*/scenario.py` and the obvious
   `0x111…1` / `0x222…2` placeholder r/s values in
   `tasks-live/tx.jsonl` — public math and dummy fixtures, not secrets.
   Scenario wallet keys are derived at runtime and never saved.

## Definition of done (run all of these before claiming anything works)

```bash
python3 run_eval.py --self-test                 # 242/242, ~910 fixtures
python3 run_eval.py --self-test --track tools   # 33/33
python3 test_graders.py                         # grader-helper regressions
python3 run_live_eval.py --self-test            # live-truth cmds resolve
python3 test_exec.py                            # exec harness (~15s, real anvil, no model)
python3 report.py                               # must not crash
```

All were green at commit `080964b` (2026-08-19). Needs `anvil`/`cast`
(foundry, installed via brew) and Python stdlib only.

## State as of 2026-08-19

- 242 closed-book tasks (`tasks/*.jsonl`), 33 tool-track (`tasks-tools/`),
  51 live (`tasks-live/`: live 10, calibration 7, addresses 24, protocol 3,
  tx 7 — 2026-08-30/31 expansion; every address truth-cmd verifies on-chain
  code, most also make a functional call — e.g. Lido stETH name(), Curve
  3pool coins(0)=DAI, Comet baseToken()=USDC, univ2 factory getPair). Graders hardened (see below),
  MC balanced 10/10/10/9. `PURPOSE.md` + `GOAL.md` (2026-08-30) state the
  target: top model ~80% on concepts, 50–75% on execution — saturation is a
  maintenance signal. Live tasks are OUTSIDE the manifest, so adding them
  does not orphan ranked closed-book runs.
- **The leaderboard is intentionally empty.** Results now carry a benchmark
  manifest hash; all 14 saved runs in `results/` predate it and `report.py`
  parks them as legacy, unranked. The first fresh sweep repopulates it.
- Execution track (`harness/` + `scenarios/`) has six scenarios passing
  exit criteria across three tracks (transactions / security / build):
  `tx-eip1559-transfer`; `erc2612-permit` (2026-08-30 —
  gasless permit + delegated transferFrom; owner has tokens but zero ETH;
  committed precompiled `PermitToken`, runs offline; fixtures 90/65/20);
  `fork-swap` (2026-08-30 — pinned mainnet fork via
  `harness/fork_proxy.py`, a loopback proxy that keeps the Alchemy key out
  of anvil's argv where the agent's `ps` could read it; swap exact ETH →
  USDC to a recipient, Chainlink-derived min-out, delta-based grading
  because mainnet addresses hold prior state, no dangling approvals;
  fixtures 70/90+violation/55; needs `ALCHEMY_API_KEY` in `.env` —
  test_exec skips its section without it, and DON'T force a base fee on a
  fork, the pinned block's real base fee rules); and `vault-exploit-patch`
  (2026-08-30 — Security track; agent gets a Foundry project with a
  first-depositor-inflation vault, writes an exploit test + patches the
  vault; grading builds throwaway forge projects OUTSIDE the workspace and
  runs `forge test`, swapping original/agent/reference vaults × agent/
  canonical exploits × a hidden functional suite; no forge-std, tests declare
  `Vm` inline; the exploit_is_real milestone catches cheatcode-faked exploits
  by re-running them against a safe vault; fixtures 70/70/75; forge-only, no
  chain); and `repo-repair` (2026-08-30 — Build track; a Foundry repo whose
  `src/Sale.sol` has five planted defects: compile error (`latestAnswer` vs
  `latestRoundData`), decimal-scaling (6/18/8-dec: cost = amt*price/1e20),
  missing oracle-staleness check, missing proceeds accounting, missing owner
  check; `Mocks.sol`/`Registry.sol` are correct localization noise; hidden
  functional suite per milestone; fixtures 15/80/80); and `ctf-challenge`
  (2026-08-31 — Build track; a faithful port of BuidlGuidl CTF Challenges 1-4
  from `ctf-argentina` (`extension` branch), deployed on the scenario's anvil
  with a minimal no-OZ `NFTFlags` registry stub. Agent registers a team then
  captures three flags: keccak calldata key, a helper contract with the right
  `accessKey`, a payment-callback contract. LEAK-RESISTANT: the access-key
  string and required wei are SEEDED per run (contracts compiled at
  setup_chain), so `broken_memorized` — the original public `LET_ME_IN` / 1
  gwei — captures flags 1-2 but loses 3-4; grading reads registry
  `hasMinted`; fixtures 10/35/65). No agent has been run against any of them
  yet.

  Two forge gotchas the vault scenario hit: (1) `vm.prank(x); f(g())` — the
  prank is consumed by the INNER call `g()`, not `f`; read into a var first.
  (2) `forge test --json` returns per-test status keyed by `fn()`; a compile
  error yields non-JSON, so treat unparseable stdout as "didn't compile".

## Grading architecture — the non-obvious parts

`run_eval.py` is the whole closed-book engine. Grader types: `numeric`,
`bigint`, `exact`, `regex`, `regex_all`, `json`, `any_of`. Things that are
deliberate and easy to re-break:

- **The negation guard** (`_NEG_RE` + the flip in `grade()`): a grader match
  only proves the expected token APPEARED. "Answer: not 12" used to pass 179
  of 242 graders. Now any pass whose *answer line* matches `_NEG_RE` is
  flipped to fail — **unless the task's own `reference` is negated** (honesty
  tasks answer "cannot"; `l2s-k-05` / `toolchain-k-05` answer "not X").
  Those 4 tasks are the only ones a negation probe still passes; that is
  expected and correct.
  - **"false" is deliberately NOT in `_NEG_RE`**: honesty answers are JSON
    containing `"can_know": false` — adding it flips correct answers to fail.
    Same caution applies before adding "no" (too common in valid answers).
- **Self-test synthesizes negation probes for every task** (3 per task, built
  from the reference's answer line). A new task with a token-presence grader
  will fail self-test until its grader can't be negated past. Opt-out flag
  `checks.no_auto_negation` exists but nothing uses it yet — prefer fixing
  the grader.
- **bigint = first integer on the answer line, exactly one distinct value.**
  "12 or 13", "12-13", "2 (EIP-1559)" all fail as ambiguous. `EIP-4844`
  parses as 4844, not -4844 (`_INT_RE` lookbehind). Without an Answer line,
  the response's LAST integer wins.
- **`ans_line()`** = content after the last "Answer:" marker, else last
  non-empty line. Nearly every grader scopes to it. Change it and everything
  shifts.
- **The manifest** (`manifest_hash()`): sha256 over the canonical full task
  corpus + `inspect.getsource` of every grading function + `_NEG_RE.pattern`.
  Consequence: **any edit to a task or a grading function orphans all saved
  results** — deliberate, that's the integrity guarantee. Don't "fix" this by
  excluding graders from the hash. `--category`/`--limit` runs are flagged
  `subset: true` and never ranked.
- **`report.py`** imports from `run_eval` and ranks only runs whose manifest
  equals the current on-disk one; everything else prints under LEGACY with a
  reason column. Coverage tables fall back to legacy data with a STALE label
  when no compatible runs exist.
- **`gen/rebalance_mc.py`** did the MC rebalance (seed 2026). It is NOT
  idempotent — rerunning reshuffles again and orphans the manifest. Don't
  rerun it unless MC answers drift unbalanced again. It swaps option text,
  updates grader letters (canonicalizing letter regexes to `^\(?X\b`),
  reference, and maps letters in `checks` fixtures through the swap
  permutation.

## Execution harness (`harness/` + `scenarios/`)

Per attempt: fresh temp workspace → dedicated `anvil` on a free port with a
generated chain id → `scenario.setup_chain()` funds derived accounts →
agent runs with `cwd=workspace`, prompt on stdin, env scrubbed
(`CLAUDECODE`, `CLAUDE_CODE_*`, `ANTHROPIC_API_KEY`, `ALCHEMY_API_KEY`,
`BANKR_API_KEY`, `OPENAI_API_KEY`) → hidden grading from OUTSIDE the
workspace, against chain state via JSON-RPC → teardown. `--save` writes a
redacted bundle to gitignored `exec-results/`.

A scenario dir needs: `scenario.json` (metadata + milestone points),
`prompt.md` (template), `scenario.py` (`generate(seed)`, `setup_chain`,
`workspace_files`, `grade` → `(milestones, violations)`), `reference.py`
(must score 100/100 every seed), `fixtures/broken_*.py` (must fail for
distinct reasons). `test_exec.py` is the exit-criteria gate — extend it when
adding a scenario.

`tx-eip1559-transfer` specifics:
- Instance params derive deterministically from the seed (keys via
  sha256 → mod curve order; address via `cast wallet address`). Odd wei
  amounts so a rounded guess can't pass.
- **Every third seed starts the sender at a nonzero nonce** — agents must
  query, not assume 0. `grade()` checks `tx.nonce == start_nonce` and final
  nonce `== start_nonce + 1` (extra transactions = safety violation).
- Milestones: submission_valid 10 / raw_type2 10 / sender_recovered 10 /
  fields_correct 20 / receipt_success 20 / state_correct 20 / fee_bound 10.
  Every point maps to a chain assertion; prose is never graded.
- Broken fixtures and their expected failure signatures (asserted in
  test_exec.py): `broken_unsigned` = signs but never broadcasts (score ≤10);
  `broken_legacy` = type-0 tx (fails raw_type2 + fields only, 70);
  `broken_wrong_value` = value−1 wei (fails fields + state only, 60).
- Grading trusts anvil for signature recovery (`tx.from`) and raw bytes
  (`eth_getRawTransactionByHash` must equal the submitted `raw_tx`).

## Running a sweep (ONLY after Austin's ok)

```bash
# closed-book, CLI agents (the pattern used for the 2026-08-18/19 runs):
python3 run_eval.py --name opus-5 --cmd 'claude -p --model opus' --concurrency 4
# OpenAI-compatible endpoints (bankr gateway):
python3 run_eval.py --name gpt-5.6 --base-url https://llm.bankr.bot/v1 \
    --model gpt-5.6-sol --api-key-env BANKR_API_KEY --auth xapikey
# exec scenario against a real agent:
python3 harness/run_scenario.py --scenario tx-eip1559-transfer --seed 1 \
    --name fable --agent-cmd 'claude -p --model fable' --save
```

`run_eval.py` aborts after 10 consecutive target errors (an outage is not a
score) and refuses to save a run with unreached tasks unless `--save-partial`.

## Loose ends / open decisions

- **TWO exec tracks now coexist — coordinate before touching either.**
  `run_exec_eval.py` + `exec/` + `results-exec/` is a PARALLEL track built in
  another session (committed 1ea5846/8318133 on 2026-08-19, while this doc was
  being written): the model's *answer* (calldata/script) is injected into
  hidden Foundry tests on a pinned mainnet fork — answer-injection grading.
  `harness/` + `scenarios/` (this doc's track) is agent-in-workspace grading:
  the agent gets a shell, a wallet, and a live local chain. They test
  different things (can it produce the right artifact vs can it operate).
  Neither subsumes the other yet; a future consolidation should keep both
  grading modes but share the manifest/reporting layer.
- **Deferred on purpose** (see the "do it" conversation, 2026-08-19):
  capability gates and track weights (too few execution tasks to be stable —
  report the score vector instead), and the ethskills with/without A/B
  (expensive; build after the execution pack is calibrated).
- Next scenarios in priority order (NEXT_STEPS_REPORT.md §"First execution
  task pack"): ERC-2612 permit → pinned-fork swap (needs `rpc_policy.
  alchemy_url()`, already built) → vault exploit+patch → broken-repo repair.
- Known cosmetic gap: `report.py` header says "manifest e88bd…" — that hash
  changes every time tasks/graders change; that's the design, not a bug.
