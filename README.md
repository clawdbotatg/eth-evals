# eth-evals

**How much Ethereum does an LLM actually know?**

An evaluation suite that interrogates a vanilla LLM — no docs, no tools, no
retrieval — on the working knowledge an Ethereum builder needs: the same
knowledge [ethskills.com](https://ethskills.com) packages for AI agents.

Two questions it answers:

1. **Which model knows Ethereum best?** A leaderboard across 242 closed-book
   tasks in 25 categories: wallets, standards, security, testing, tooling, gas,
   calldata, derivations, L2s, frontend, indexing, protocol, concepts,
   addresses, fundamentals, units, toolchain (Foundry/Hardhat 3/Scaffold-ETH 2
   conventions), navigation (where you go: abi.ninja, explorers, faucets,
   Sourcify, SpeedRun Ethereum) — plus CROPS (censorship resistance / open
   source / privacy / security), MEV, cryptoeconomics (walkaway-test
   scenarios), cypherpunk ideals, fork roadmap (date-tagged), contract-reading
   (full Solidity source in the prompt), and honesty (live-data questions where
   the only right closed-book answer is `{"can_know": false}`).
2. **What can ethskills stop teaching?** Every knowledge task is keyed to a
   specific ethskills SKILL.md claim. When every frontier model aces a skill's
   tasks, that content is already in the models and is a candidate for
   trimming. The endgame: the models know everything and ethskills retires.

## Design: where the answers come from (not the authoring LLM)

An LLM helped author this eval, which is a bias risk — an LLM writing questions
from its own knowledge would build an eval of *what LLMs already know*. Two
defenses:

- **Computational tasks (`gen/`)** — ground truth is *computed*, never authored:
  ABI calldata, event signatures, CREATE2 derivations, gas and unit math come
  from foundry's `cast` or integer math straight from the spec pseudocode
  (sanity-asserted against known vectors, e.g. EIP-1014's CREATE2 test vector).
  Instances are randomized from a seed — regenerate per release
  (`python3 gen/generate_tasks.py --seed <new>`), so there is nothing to memorize.
  **No closed-book task requires unaided keccak**: anything that ends in
  producing a hash digest (selectors, topic0, EIP-55, CREATE/CREATE2, mapping
  slots) lives in `tasks-tools/` and runs with `--track tools` against a
  tool-using agent; the closed-book versions give the hash and test the
  surrounding rule (padding, layout, selector matching, address truncation,
  canonical signature strings).
- **Knowledge tasks (`tasks/skill-*.jsonl`)** — the answer key is the ethskills
  file's claim, not the author's opinion. Every task carries a `source_quote`
  field with the verbatim SKILL.md line it grades against, and a `source` field
  naming the skill, so per-skill coverage is reportable and every answer is
  auditable against the corpus.

Residual bias disclosed: question *selection* still passed through an LLM, and
pure-recall items are trained-on by definition (tagged and accepted).

Grading is 100% deterministic (exact / regex / JSON-shape / bigint) — there is
no LLM judge. `--self-test` grades every task's bundled reference answer AND
its adversarial fixtures (`checks.must_pass` / `checks.must_fail` — correct
paraphrases that must pass, wrong answers that must fail) and must be 100%
before any run counts. `python3 test_graders.py` additionally pins the grader
helpers against known failure modes (`EIP-4844` ≠ -4844, wrong-then-right
numbers, fabricated values beside a disclaimer).

Hardened 2026-08-19 after an adversarial review:

- **Negation guard** — a grader match means the expected token *appeared*, not
  that the answer asserted it. `Answer: not 12` used to pass 179/242 graders;
  now any passing answer whose answer line is negated is flipped to a fail
  (unless the task's own correct answer is negated, e.g. honesty tasks).
  Self-test synthesizes three negation probes for *every* task.
- **Integer answers commit to one value** — `12 or 13`, `12-13` fail.
- **Balanced multiple choice** — correct positions were 28/39 on B (blind-B
  scored 72.5% on that slice); now 10/10/10/9 via `gen/rebalance_mc.py`.
- **Benchmark manifest** — every result records a sha256 over the full task
  corpus + grader source, plus the harness commit. `report.py` ranks only runs
  on the current manifest; older / subset runs are listed as legacy, never
  ranked together (the previous leaderboard silently mixed 176- and 242-task
  runs).

## Run it

```bash
python3 run_eval.py --self-test                       # graders green? (zero tokens)

# any OpenAI-compatible endpoint:
python3 run_eval.py --name gpt-5.6 --base-url https://llm.bankr.bot/v1 \
    --model gpt-5.6-sol --api-key-env BANKR_API_KEY --auth xapikey

# any CLI harness (prompt on stdin, answer on stdout):
python3 run_eval.py --name haiku --cmd 'claude -p --model haiku' --concurrency 4

# tool track (33 keccak tasks — needs an agent with cast, not a bare model):
python3 run_eval.py --track tools --name haiku --cmd 'claude -p --model haiku'

python3 report.py          # leaderboard + per-skill ethskills coverage
python3 report.py --md     # markdown tables
```

Protocol: temperature 0, pass@1, no retries, deterministic graders, bootstrap
95% CI over categories. Stdlib-only Python; `cast` (foundry) needed only to
*regenerate* tasks, not to run them.

## Task format

One JSON object per line in `tasks/*.jsonl`:

```json
{"id": "gas-k-03", "category": "gas", "source": "gas", "kind": "fact",
 "prompt": "...question ending with an answer-format instruction...",
 "grader": {"type": "regex", "pattern": "burn(ed|t)?"},
 "reference": "Answer: it is burned",
 "source_quote": "The base fee is burned, not paid to validators."}
```

`kind: "recommendation"` marks ethskills' opinionated guidance (which tool,
which pattern) vs objective `fact`s. The leaderboard reports them separately
(`facts` vs `rec-adh`) — a model can be right and disagree with an opinion,
so recommendation adherence never blends into the factual score.

See `tasks/AUTHORING.md` for the authoring rules and grader semantics.

## Live / agentic track

`run_live_eval.py` + `tasks-live/` test whether a tool-using AGENT (claude -p,
codex, …) can do real Ethereum work right now: current block/gas/ETH price,
a Uniswap pool's live liquidity, a proxy's implementation slot, building exact
transfer calldata with correct decimals. No LLM judge: the harness computes
ground truth itself via `cast` against the same RPC at grade time, and
compares within a declared tolerance. Needs `RPC_URL` in a gitignored `.env`
(Alchemy — never a public RPC).

```bash
python3 run_live_eval.py --self-test                        # truth cmds resolve
python3 run_live_eval.py --name haiku --cmd 'claude -p --model haiku'
```

## Execution track (v2 vertical slice)

`harness/run_scenario.py` + `scenarios/` evaluate whether an agent can do real
Ethereum work, graded from **chain state and raw transactions**, never prose.
Each attempt gets a fresh temp workspace and a dedicated anvil on a generated
chain id; hidden grading runs outside the workspace; upstream credentials are
scrubbed from the agent env and redacted from saved bundles
(`harness/rpc_policy.py` also enforces the Alchemy-only / no-public-RPC rule
for future fork scenarios).

First scenario: **tx-eip1559-transfer** — construct, sign, broadcast, and
verify an exact-value type-2 transfer under a fee bound, with per-milestone
partial credit (submission / envelope / signature / fields / receipt / state /
fee) and generated variants (chain id, keys, odd wei amounts, nonzero starting
nonce every third seed).

```bash
python3 test_exec.py    # exit criteria: reference 100/100 on every seed,
                        # 3 broken solutions fail for 3 distinct reasons,
                        # env scrubbed, public RPCs rejected (~15s, no model)
python3 harness/run_scenario.py --scenario tx-eip1559-transfer --seed 1 --reference
python3 harness/run_scenario.py --scenario tx-eip1559-transfer --seed 1 \
    --name fable --agent-cmd 'claude -p --model fable' --save
```

## Roadmap

- **More execution scenarios** (see `NEXT_STEPS_REPORT.md`): ERC-2612 permit,
  pinned-fork swap, vault exploit+patch, broken-Foundry-repo repair, proxy
  upgrade — then capability gates and a score vector per track.
- **ethskills A/B**: same model, same scenario instance, with vs without the
  skill, isolated paired sessions — does the skill close the gap for weaker
  models? (That finding is the whole ballgame for ethskills.)
