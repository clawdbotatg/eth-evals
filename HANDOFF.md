# eth-eval — handoff to the next agent

Read this after `CLAUDE.md`, `PURPOSE.md`, `GOAL.md`. This file is the state of
the world as of 2026-09-02: what we're trying to do, everything we learned the
hard way, and where the frontier is.

## The one goal

Measure how good any LLM is at Ethereum in three sections: **concepts,
transactions, building.** Top model (Fable) should land ~80%, not 98%.
Difficulty must come from being **current** and **applied** (graded by whether
the tx/code actually works) — NOT from tricks, gotchas, or esoterica. Gas-cost
questions are fine (conceptual). Austin has said "not trying to trick Fable"
many times — respect it.

## Hard rules (never break)

1. **NO model run without Austin's explicit ok.** Every run costs money and
   lands in results. Self-tests, `test_exec.py`, reference/fixture runs are
   free — always fine. Austin authorized the Fable runs logged below; that ok
   does not extend to new runs.
2. **Never a public RPC.** `harness/rpc_policy.py` enforces Alchemy-only.
   `ALCHEMY_API_KEY` in gitignored `.env`.
3. **Never commit keys.** Only 64-hex in repo: secp256k1 curve order and the
   `0x111…`/`0x222…` placeholders. Scenario keys are derived at runtime.
4. **Build/verify as Fable this session** — Austin insists the suite is built
   by Fable (`/model fable`). This is deliberate; see the ceiling finding below.

## The three tracks and where each stands

| Track | Where | Fable score | Verdict |
|---|---|---|---|
| Concepts (closed-book) | `tasks/*.jsonl` (242) + `tasks-tools/` (33) | ~98% | Saturated. Maintenance only. |
| Current-state / live | `tasks-live/` (51) | **68%** | **The one real discriminator.** |
| Building / exec | `scenarios/` (11) | **100%** | Saturated on capability. See below. |

## The central finding (don't re-derive this the hard way)

**A model cannot author a challenge that stumps itself.** The hard part of
anything Fable invents is something Fable already knows how to solve. We proved
this exhaustively:

- Hardest internals puzzles (reconstruct block-header RLP so keccak==blockhash)
  → `cast block N --raw` hands the answer over free. Tools trivialize internals.
- CTF ports 1-8, gas-golf, Damn Vulnerable DeFi Puppet → Fable one-shots all,
  ~55s each.
- **Escaping the ceiling needs difficulty sourced OUTSIDE Fable's head:** the
  current-state track (things that moved since training), or a genuinely
  stronger author/grader model.

### The research lever (the one thing that moved the needle)

Austin's insight: "research is your secret weapon — you can learn more than
Fable knows out of the box." Deep-researching a real, subtle, recent exploit
and reproducing it faithfully (dependency-free, seeded constants) forces Fable
into on-the-fly simulation. Two built:

- **dvd-balancer-rounding** (Nov-2025 Balancer V2 hack) — Fable ~200-255s
  (**4x** baseline).
- **dvd-readonly-reentrancy** (dForce/Curve 2023) — Fable ~167s (**3x**).

Consistent: research-sourced subtle hacks make Fable work 3-4x harder than
anything else. **But Fable still solves them 100% given agent time.** Not yet
tipped to actual failure. To try: stack the vulns, tighten time/turn budget, or
find a hack whose derivation is harder than one-shot allows.

## The 11 exec scenarios (all pass `test_exec.py`)

Tracks: **T**ransactions / **S**ecurity / **B**uild.

1. `tx-eip1559-transfer` (T) — sign+broadcast a type-2 tx. Every 3rd seed starts
   sender at nonzero nonce (must query, not assume 0). Odd wei amounts.
2. `erc2612-permit` (T) — gasless permit + delegated transferFrom; owner has
   tokens, zero ETH. Committed precompiled `PermitToken`, runs offline.
3. `fork-swap` (T) — pinned mainnet fork via `harness/fork_proxy.py` (keeps
   Alchemy key out of anvil argv). Swap ETH→USDC, Chainlink min-out, delta
   grading. Needs `ALCHEMY_API_KEY`; test_exec skips it without one. **Don't
   force a base fee on a fork** — the pinned block's real base fee rules.
4. `vault-exploit-patch` (S) — first-depositor inflation vault; write exploit +
   patch. Builds throwaway forge projects OUTSIDE workspace; `exploit_is_real`
   milestone catches cheatcode-faked exploits.
5. `repo-repair` (B) — Foundry repo with 5 planted defects (compile error,
   decimal scaling, oracle staleness, proceeds accounting, owner check).
6. `ctf-challenge` (B) — BuidlGuidl CTF 1-4, leak-resistant (access-key/wei
   SEEDED per run so memorized answers lose flags 3-4).
7. `ctf-advanced` (B) — BuidlGuidl CTF 7-8 (calldata offset-68 guard bypass;
   private storage-slot password). Password is a per-run constructor arg.
8. `gas-golf` (B) — correctness + a tight gas cap (TIGHT_CAP=7300, between naive
   7926 and asm 6664 — the optimizer closes most of the naive/asm gap).
9. `dvd-puppet` (S) — DVD Puppet oracle manipulation, seeded.
10. `dvd-balancer-rounding` (S) — the Balancer hack (below).
11. `dvd-readonly-reentrancy` (S) — the read-only reentrancy hack (below).

## The two research hacks in detail

### dvd-balancer-rounding
Faithful dependency-free port of the Nov-2025 Balancer V2 ComposableStablePool
hack. `contracts/Pool.sol`: 2-token StableMath pool, Newton's-method `computeD`,
`getY`. The bug: `_upscale` uses `mulDown` (floor) **unconditionally**, even for
the token-in leg that should round up. Rate-provider scaling factor fY>1e18.
EXACT_OUT swaps under-charge at low balances → invariant D shrinks → a greedy
~47-swap loop drains ~96% past the invariant guard. Leak vanishes at high
balances. `quoteExactOut` view is a queryBatchSwap analog for simulating swaps
without a live sender.

Gotchas hit: MockERC20 string constructor args broke deploy encoding (dropped
name/symbol from constructor). `cast call` on a non-view swap reverted (wrong
sender) → added the `quoteExactOut` view. `1e20` as a literal is a rational
const, won't compile → route seeded amounts through `uint256` vars.

### dvd-readonly-reentrancy (most recent, commit 237e128)
dForce/Curve 2023 read-only reentrancy, dependency-free. `contracts/System.sol`:
Token, LP, Pool, LendingVault. The vulnerable core:

```solidity
function remove_liquidity(uint256 amt) external {
    uint256 s = lp.totalSupply();
    uint256 ethOut = ethReserve * amt / s;
    uint256 tokenOut = tokenReserve * amt / s;
    lp.burn(msg.sender, amt);                          // supply drops FIRST
    (bool ok, ) = msg.sender.call{value: ethOut}("");  // reentrancy window: vp inflated
    require(ok, "eth");
    ethReserve -= ethOut; tokenReserve -= tokenOut;    // reserves reduced AFTER callback
    require(token.transfer(msg.sender, tokenOut), "send");
}
```

`get_virtual_price() = D()*1e18/lp.totalSupply()` — no reentrancy guard.
`LendingVault.borrow` limit = `collateral * get_virtual_price()/1e18 * cf/1e18`.
During the ETH callback, totalSupply already dropped but reserves haven't → vp
spikes 50-140x. Attacker dominates the pool, deposits a collateral sliver,
removes the rest, and from `receive()` borrows the vault dry against the
temporarily overvalued collateral.

setup_chain: tiny pool (8-15 units), vault funded 1500-2500 Token, player 5000
ETH + 5000 Token. Milestones: `vault_drained` 60 (≥40% lost), `attacker_profit`
40 (player ≥40% of vault). Fixed selectors SEL_ADD_LIQ="0xf4532a51",
SEL_LP="0x313c06a0".

reference.py: attacker funded with player's FULL budget (bigger D = bigger
borrow cap), collat=200e18. Fixtures: `broken_honest_borrow` (real price, tiny
borrow → score 0, both milestones fail), `broken_no_sweep` (runs the exploit but
leaves loot in the attacker contract → vault_drained passes, attacker_profit
fails, score 60). Two distinct failure signatures asserted in test_exec.

Bugs fixed getting it to work: exploit reverted when vp bump too small (attacker
must dominate pool). `grab=1500` exceeded the ~808 borrow limit → attacker
computes max borrow live in `receive()`. Reference drained only ~115 with
collat=1 → added full budget + collat=200e18. Two hardcoded selectors were
wrong. Leftover `if False else` ternary cleaned.

## Solidity/Foundry gotchas (bank these)

- `vm.prank(x); f(g())` — prank is consumed by the INNER call `g()`, not `f`.
  Read into a var first.
- `literal * literal / 1e20` is a rational const — won't compile. Route through
  `uint256` vars.
- `forge test` runs with an inline `Vm` interface (no forge-std needed); tests
  declare `Vm` inline.
- `forge test --json` gives per-test status keyed by `fn()`; a compile error
  yields non-JSON stdout → treat unparseable output as "didn't compile".
- The solc optimizer closes most naive-vs-asm gas gaps — gas caps must be
  measured empirically and set between the two.
- MockERC20 with string constructor args can break hand-rolled deploy encoding;
  drop name/symbol from the constructor when deploying via raw `cast --create`.

## Exec harness mechanics

`harness/run_scenario.py`: per attempt → fresh temp workspace → dedicated anvil
on a free port with a generated chain id → `scenario.setup_chain()` funds
derived accounts → agent runs `cwd=workspace`, prompt on stdin, env scrubbed
(`CLAUDECODE`, `CLAUDE_CODE_*`, `ANTHROPIC_API_KEY`, `ALCHEMY_API_KEY`,
`BANKR_API_KEY`, `OPENAI_API_KEY`) → hidden grading from OUTSIDE the workspace
via JSON-RPC → teardown. `--save` writes a redacted bundle to gitignored
`exec-results/`. Agent invoked `claude -p --model fable --dangerously-skip-permissions`.

`start_anvil(chain_id, base_fee, fork=None)` supports forks. `workspace_files`
mkdir-parents for nested src/test files.

Scenario contract: `scenario.json` (metadata + milestone points), `prompt.md`
(template), `scenario.py` (`generate(seed)`, `setup_chain`, `workspace_files`,
`grade` → `(milestones, violations)`), `reference.py` (must score 100 every
seed), `fixtures/broken_*.py` (must fail for DISTINCT reasons). `test_exec.py`
is the exit-criteria gate — extend it when adding a scenario.

## Two exec tracks coexist (don't confuse them)

- `harness/` + `scenarios/` (this doc) — **agent-in-workspace** grading: the
  agent gets a shell, a wallet, a live local chain. Tests "can it operate."
- `run_exec_eval.py` + `exec/` + `results-exec/` — **answer-injection** grading:
  the model's answer (calldata/script) is injected into hidden Foundry tests on
  a pinned fork. Tests "can it produce the right artifact." Built in a parallel
  session (commits 1ea5846/8318133). Neither subsumes the other. A future
  consolidation should keep both grading modes, share manifest/reporting.

## Closed-book grader landmines (the non-obvious parts)

- **Negation guard** (`_NEG_RE`): a grader match only proves the token appeared.
  Any pass whose answer line matches `_NEG_RE` is flipped to fail — UNLESS the
  task's own reference is negated (honesty/"cannot" tasks; `l2s-k-05`,
  `toolchain-k-05`). "false" is deliberately NOT in `_NEG_RE` (honesty JSON has
  `"can_know": false`). Self-test synthesizes 3 negation probes per task.
- **bigint** = first integer on the answer line, exactly one distinct value.
  "12 or 13" fails as ambiguous. `EIP-4844` parses as 4844.
- **`ans_line()`** = content after the last "Answer:" marker, else last
  non-empty line. Nearly every grader scopes to it.
- **Manifest** (`manifest_hash()`): sha256 over the full task corpus +
  `inspect.getsource` of every grading fn + `_NEG_RE.pattern`. **Any edit to a
  task or grader orphans all saved results** — deliberate integrity guarantee.
  Live tasks are OUTSIDE the manifest (adding them doesn't orphan ranked runs).
- `gen/rebalance_mc.py` is NOT idempotent — don't rerun.

## Definition of done (run all before claiming anything works)

```bash
python3 run_eval.py --self-test                 # 242/242
python3 run_eval.py --self-test --track tools   # 33/33
python3 test_graders.py
python3 run_live_eval.py --self-test            # live-truth cmds resolve
python3 test_exec.py                            # exec harness, real anvil, no model
python3 report.py                               # must not crash
```

Needs `anvil`/`cast` (foundry) and Python stdlib only.

## Where the frontier is (start here next)

The eval is strong: rigorous auto-graded harness across all three sections, 11
exec scenarios, 51 live tasks, ranks weaker models well. The open problem is a
**50-75% band FOR Fable on the building track** — not reachable with one-shot
on-chain tasks a Fable-level author can build.

Live options, roughly in order:
1. **Grow the current-state / live track** — the proven discriminator (68%).
   Lowest risk, highest signal per unit effort.
2. **Stack research hacks** — combine two subtle vulns in one scenario, or
   tighten the time/turn budget on the 3-4x scenarios to push past Fable's
   working limit.
3. **Euler self-liquidation** — the #2 research candidate, NOT built. Health
   check missing on `donateToReserves` + liquidation-discount profit on
   self-inflicted bad debt. Different flavor, equally subtle.
4. **A stronger author/grader model** — the only clean way past the
   "can't-stump-yourself" ceiling.

Other shortlist candidates from the research sweep: storage-collision, integer
downcast, liquidation-rounding, fee-on-transfer, ecrecover-zero.

## Memory files (persistent across sessions)

- `memory/fable-calibration-2026-08-31.md` — every Fable run, parts 1-4, the
  ceiling finding and the research-lever finding. Read it.
- `memory/eth-eval-dev-phase.md` — the goal and the no-runs-without-ok rule.
