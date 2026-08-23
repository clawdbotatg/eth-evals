# eth-evals critical review

**Review date:** 2026-08-16  
**Scope:** all 243 closed-book tasks in `tasks/*.jsonl`, the grader implementation in `run_eval.py`, and the evaluation design described in `README.md`.  
**Review question:** Are there low-value questions, incorrect or misleading answer keys, or deterministic graders that reject a substantively correct answer?

## Executive summary

The suite has a strong skeleton: task files are easy to audit, generated values are separated from knowledge claims, prompts usually specify an answer format, and the grader is small enough to understand. The current task set should not be used for model comparisons without revision, however. There are several score-distorting defects:

1. **Thirty-three of 243 tasks require unaided cryptographic hashing.** In a no-tools, closed-book interview, randomized selectors, event topics, CREATE addresses, mapping slots, and checksums do not measure Ethereum knowledge. They mostly measure whether a model fabricates a hash.
2. **Eight EIP-number tasks reject the natural correct form `EIP-####`.** The bigint parser reads the hyphen as a negative sign.
3. **All five honesty probes can accept a fabricated live value.** A hallucinated number passes if the response also contains a weak keyword such as `check`, `varies`, `roughly`, or `DexScreener`.
4. **At least four questions contain materially incorrect premises:** post-Merge timestamp manipulation, Unichain's supposed encrypted mempool and FCFS ordering, the Superchain revenue formula, and Fusaka's claimed 30M-to-60M gas-limit change.
5. **Several questions conflate a particular protocol with an ecosystem-wide rule**, including Aave's health factor, EIP-3009 in x402, a 10,000-block log-query cutoff, and SyncSwap liquidity.
6. **The task mix overweights duplicated recall and low-value version trivia.** The same facts are tested in multiple categories, while exact dependency patch versions and transient market conditions are treated as Ethereum knowledge.

The generated numerical answers did not show an obvious arithmetic or encoding error during this pass. The serious issue with the generated section is fitness for a closed-book knowledge evaluation, not the mechanism used to compute its references.

## Severity summary

| Severity | Finding | Scope |
|---|---|---:|
| Blocker | Cryptographic computation in the closed-book track | 33 tasks |
| Blocker | `EIP-####` parsed as a negative integer | 8 tasks |
| Blocker | Honesty graders accept fabricated live values | 5 tasks |
| High | Incorrect or materially misleading factual premises | 4 clear cases |
| High | Keyword graders accept negated/wrong answers | systemic |
| Medium | Strict multiple-choice graders reject correct elaborations | 12 tasks |
| Medium | Ambiguous or protocol-specific questions presented as universal facts | 6+ tasks |
| Medium | Duplicate facts distort category-weighted scores | 8+ clusters |
| Low | Source quote violates the repository's Alchemy-only RPC policy | 1 task |

## 1. Closed-book tasks that require cryptographic computation

The README says the model receives no tools, documentation, or retrieval. Under that protocol, the following randomized tasks are not reasonable tests of Ethereum knowledge:

| File | Tasks | Why a tool-less model cannot reliably answer |
|---|---:|---|
| `gen-calldata.jsonl` | 15 | All selector, encoding, and decoding items require one or more Keccak-derived function selectors. |
| `gen-derivations.jsonl` | 10 | CREATE, CREATE2, and mapping-slot derivations end in Keccak hashing. |
| `gen-indexing.jsonl` | 4 | Event `topic0` is a Keccak hash. |
| `gen-wallets.jsonl` | 4 | EIP-55 checksum casing depends on Keccak output. |

That is **33 tasks, or 13.6% of the suite**. Randomization correctly prevents memorization, but it also guarantees that knowing the formula is insufficient. A knowledgeable model can explain `keccak256("transfer(address,uint256)")[0:4]` perfectly and still cannot derive an arbitrary 256-bit digest in its weights.

Recommended disposition:

- Move these tasks into the planned execution/tool track, where the model writes a `cast` or viem command and the harness executes it.
- Keep the closed-book ABI-layout questions, but provide the selector in the prompt. The model can then be evaluated on padding, dynamic offsets, tuple layout, and decoding.
- Keep gas, base-fee, and unit arithmetic in the closed-book track; those operations are realistically computable from the prompt.
- For CREATE/CREATE2 and storage-slot knowledge, ask for the formula or provide the hash primitive's output and ask the model to finish the derivation.

## 2. Grader defects that reject correct answers

### 2.1 `EIP-####` becomes a negative integer

`run_eval.py` uses this integer pattern:

```python
_INT_RE = re.compile(r"(?:0x[0-9a-fA-F][0-9a-fA-F_]*|-?\d[\d_,]*)")
```

The optional minus sign is not boundary-aware. Consequently, `EIP-4844` yields `-4844`. The following response is correct and follows the requested format, but fails:

```text
Answer: EIP-4844
```

Observed grader result:

```text
(False, "got [-4844]")
```

Affected tasks:

- `protocol-k-01` — EIP-4844
- `protocol-k-05` — EIP-7723
- `protocol-k-06` — EIP-7600
- `protocol-k-08` — EIP-7594
- `protocol-k-09` — EIP-7732
- `roadmap-k-02` — EIP-7928
- `roadmap-k-04` — EIP-7892
- `roadmap-k-07` — EIP-7251

Fix options:

- Use regex graders for EIP/ERC identifiers, as most standards tasks already do.
- Alternatively, make a minus sign valid only at the start of a token rather than immediately after an ASCII letter.
- Add explicit tests for `4844`, `EIP-4844`, `EIP 4844`, and `Answer: EIP-4844`.

### 2.2 Exact multiple-choice graders reject a correct elaboration

Twelve multiple-choice tasks use an exact single-letter grader. A response such as this fails:

```text
Answer: B — Switch Network
```

The same suite already uses `any_of` plus a `^B\b` regex for many other multiple-choice tasks. Apply that tolerant pattern consistently.

Affected exact-letter tasks:

- `frontend-k-03`, `frontend-k-04`, `frontend-k-05`, `frontend-k-09`
- `gas-k-08`, `gas-k-09`
- `l2s-k-06`
- `roadmap-k-08`
- `security-k-08`
- `wallets-k-04`, `wallets-k-05`, `wallets-k-10`

This is lower severity than the EIP bug because prompts request a single letter, but it still introduces avoidable format sensitivity into a knowledge score.

### 2.3 A standard synonym for reentrancy is rejected

`contract-reading-k-05` uses `re-?\s?entranc`, which rejects `re-entry attack`. `security-k-01` already has the better alternation `re-?(entranc|entry)`. Reuse it.

### 2.4 Exact short-answer graders are unnecessarily brittle

For example, `concepts-k-01` accepts `Answer: onchain` but rejects `Answer: onchain (one word)`. Exact grading is appropriate for hashes and calldata; for semantic short answers, an anchored regex is safer.

## 3. Grader defects that accept wrong answers

Although the review brief emphasizes false rejection, false acceptance is equally damaging to a leaderboard.

### 3.1 All honesty tasks can pass fabricated live data

The honesty regexes look only for one weak disclaimer/source keyword. These incorrect responses all pass today:

| Task | Incorrect response that passes |
|---|---|
| `honesty-k-01` | `The gas price is exactly 30 gwei; it varies.` |
| `honesty-k-02` | `ETH is exactly $9,999 right now; check an exchange.` |
| `honesty-k-03` | `The latest block is exactly 99,999,999; check Etherscan.` |
| `honesty-k-04` | `GROK9000 has exactly $1,000,000 liquidity according to DexScreener.` |
| `honesty-k-05` | `Exactly 999 ETH is staked, roughly.` |

The intended behavior is not merely mentioning uncertainty; it is refusing to assert the requested live value. A deterministic grader therefore needs both:

1. a positive refusal/capability condition, and
2. a negative assertion check that rejects concrete claimed values in the requested unit.

The cleanest deterministic design is to force JSON:

```json
{"can_know": false, "reason": "requires live data"}
```

If natural language is retained, require first-person inability (`I cannot know`, `I do not have live access`, and close variants) and reject answers containing a concrete price/block/liquidity/stake claim outside an explicitly historical clause.

### 3.2 Keyword regexes ignore negation

Examples reproduced against the current grader:

- `concepts-k-04` passes `Answer: validators cannot manipulate block.timestamp` because it contains `validator`.
- `l2s-k-05` passes `Answer: It does not return Ethereum's block number; it returns Arbitrum's own.` because it contains `Ethereum`.
- Similar one-token graders will accept constructions such as `not Ponder`, `not Chainlink`, or `not binary`.

Keyword regexes should be anchored to a constrained answer shape wherever possible. For binary or multiple-choice claims, a letter/JSON grader is preferable.

### 3.3 The bigint grader accepts contradictory multi-number answers

When an answer contains multiple integers, the bigint grader passes if the expected value appears anywhere among the first three. Thus a response can lead with the wrong answer and mention the right number afterward.

Example for the 12-second block-time task:

```text
Answer: 13 seconds, although the expected figure is 12.
```

This passes because `12` is one of the first three integer candidates. The grader should use the first integer on the explicit `Answer:` line, or require a JSON/integer-only response.

### 3.4 `security-k-06` accepts an answer of the wrong type

The prompt asks for an oracle **provider**, but the regex accepts `TWAP`, which is an oracle construction rather than a provider. Either ask for an approach and accept robust TWAP designs, or ask specifically for the ethskills-recommended provider and accept only Chainlink.

### 3.5 Full-response regexes can reward mention rather than conclusion

`regex_all` tasks using `"on": "full"` pass when the required words appear anywhere in the reasoning, even if the final answer rejects one of them. This affects CROPS expansion tasks in particular. Grade the explicit answer line unless the rationale itself is intentionally being evaluated.

## 4. Incorrect or materially misleading task content

### 4.1 `concepts-k-04`: post-Merge timestamp manipulation

The task claims a validator can manipulate `block.timestamp` within roughly 15 seconds. In proof-of-stake Ethereum, the execution payload timestamp must equal the timestamp computed from the consensus slot. The proposer cannot choose an arbitrary timestamp within a window. A proposer or builder can influence transaction inclusion, and a proposer can withhold a block, but that is not the claimed timestamp manipulation.

Primary reference: [Ethereum consensus specification, `process_execution_payload`](https://github.com/ethereum/consensus-specs/blob/master/specs/deneb/beacon-chain.md).

Suggested rewrite:

> Why is `keccak256(block.timestamp)` unsuitable randomness even though post-Merge proposers cannot freely choose the timestamp?

Accept transaction-timing/inclusion control, predictability, and withholding/selection bias as appropriate components.

### 4.2 `l2s-k-07`: Unichain encrypted mempool and ordering

The prompt says Unichain uses a private encrypted mempool and orders by arrival time rather than gas price. Unichain's whitepaper lists an encrypted mempool under future work. The current Rollup-Boost specification permits configurable policies such as priority ordering or MEV-paid ordering; it does not establish universal FCFS ordering.

Primary references:

- [Unichain whitepaper](https://docs.unichain.org/whitepaper.pdf)
- [Flashbots Rollup-Boost specification](https://github.com/flashbots/rollup-boost/blob/main/specs/flashblocks.md)

Disposition: drop the task or ask a stable question about verifiable TEE block building and Flashblocks.

### 4.3 `l2s-k-09`: Superchain revenue contribution

The answer key says 15% of sequencer revenue. The documented formula is the greater of:

- 15% of net transaction-fee profit, or
- 2.5% of gross transaction fees.

Primary reference: [Optimism capital-allocation documentation](https://docs.optimism.io/governance/capital-allocation).

The current question has no single percentage answer. Rewrite it to ask for both branches of the formula.

### 4.4 `gas-k-06`: Fusaka gas-limit baseline

The target answer of 60 million is reasonable, but the premise that Fusaka raised the limit from 30 million is wrong. EIP-7935 was written when mainnet was at 36M and coordinated client defaults toward 60M; subsequent documentation describes the pre-Fusaka limit as approximately 45M.

Primary reference: [EIP-7935](https://eips.ethereum.org/EIPS/eip-7935).

Rewrite without a brittle baseline:

> What default mainnet block gas limit did EIP-7935 coordinate clients to target for Fusaka?

### 4.5 `concepts-k-07`: flash loan is not the attack class

A flash loan is a source of atomic capital. The vulnerability is trusting a manipulable spot price; the attack is spot-price/oracle manipulation. An attacker can perform it with owned or borrowed capital. A correct `spot-price manipulation` answer currently fails.

Either:

- ask what **financing primitive** often enables the attack and retain `flash loan`, or
- ask for the attack class and accept `spot-price manipulation` / `oracle manipulation`.

### 4.6 `concepts-k-08`: Aave terminology generalized to Compound

The numeric health-factor threshold of 1 is Aave terminology. Compound-style lending has analogous collateral/liquidity conditions, but not this universal health-factor interface. Change `Aave/Compound-style` to `Aave`.

## 5. Unstable, underspecified, or low-signal questions

### 5.1 Live or transient claims

These conflict with the authoring rule against contested/aging claims outside the date-maintained roadmap category:

- `fundamentals-k-04`: “typical” mainnet base fee in early 2026. “Typical” has no defined sampling window or statistic.
- `l2s-k-10`: deepest liquidity for “most pairs” on zkSync. This is live market state and neither `most` nor the pair universe is defined.
- `gas-k-09`: a standard ERC-20 transfer uses approximately 65,000 gas. Cost varies by token implementation, sender/recipient slot state, and whether balances transition from/to zero.

Disposition: remove from the closed-book knowledge track, or replace with mechanism questions whose answers do not age.

### 5.2 Provider-specific rules presented as protocol facts

`indexing-k-09` asserts that direct `eth_getLogs` scanning breaks down beyond roughly 10,000 blocks. Limits depend on the RPC provider, result density, client, timeout, and query shape. There is no protocol-level 10,000-block boundary.

Suggested rewrite:

> Name two reasons a production app may need an indexer instead of repeatedly scanning its full event history with `eth_getLogs`.

### 5.3 x402 needs scheme and network qualification

`fundamentals-k-07` and `standards-k-04` imply that x402 generally uses EIP-3009. The x402 protocol is extensible across schemes and networks. The `exact` EVM scheme uses EIP-3009 for compatible assets such as USDC; that qualifier belongs in the prompt.

Primary reference: [x402 protocol specification](https://github.com/x402-foundation/x402/blob/main/specs/x402-specification-v2.md).

### 5.4 Dependency-version trivia

The following test troubleshooting or exact patch history more than durable Ethereum knowledge:

- `crops-k-12`: exact RainbowKit version that changed telemetry defaults.
- `frontend-k-09`: Node 25 `localStorage` behavior plus a Next.js worker/polyfill workaround.
- `testing-k-04`: Foundry's default fuzz-run count without pinning a Foundry version.

Version-specific operational facts can be useful in documentation, but they should be pinned to a version and placed in a tooling compatibility track rather than treated as timeless Ethereum knowledge.

### 5.5 “Same on every EVM chain” is too broad

Several address questions say a contract exists at the same address on **all** or **every** EVM chain. CREATE2 makes an address deterministic; it does not guarantee that the contract or deployer is present on every chain. Prefer:

> On supported chains where this canonical deployment exists, what address is used?

Affected wording includes Permit2, EntryPoint, Arachnid's deployer, Safe deployments, and Multicall3.

## 6. Duplicate questions and score weighting

The suite macro-averages categories, but repeated facts in separate categories still receive extra influence. Clear duplicate or near-duplicate clusters include:

| Fact | Tasks |
|---|---|
| Preferred spelling `onchain` | `concepts-k-01`, `fundamentals-k-01` |
| CROPS expansion | `concepts-k-10`, `crops-k-01` |
| EIP-4844 introduced blobs | `gas-k-02`, `protocol-k-01` |
| PeerDAS downloads/samples 1/8 | `fundamentals-k-08`, `gas-k-07` |
| EIP-7702 shipped in Pectra | `protocol-k-03`, `standards-k-06`, plus inverse recall in `fundamentals-k-05` and `wallets-k-01` |
| Pectra timing | `wallets-k-03` and several prompts that state May 2025 |
| Scaffold-ETH command | `frontend-k-10`, `tooling-k-09` |
| USDC uses six decimals | `security-k-02`, implicitly `frontend-k-02` |
| ERC-4337 EntryPoint address recall | `addresses-k-07`, `wallets-k-06` for adjacent versions |

Some cross-category reinforcement is defensible, but direct duplicate recall should not count as independent evidence. Recommended options:

- Deduplicate exact facts.
- Assign a shared `concept_id` and cap each concept's total contribution.
- Report both task accuracy and unique-concept accuracy.

## 7. Category and taxonomy concerns

### 7.1 Recommendation versus fact labels

Several tasks encode ecosystem preferences or corpus-specific guidance rather than objective facts. They should be labeled `recommendation` consistently so reports can exclude them:

- `fundamentals-k-01` is labeled recommendation, while identical `concepts-k-01` is labeled fact.
- `protocol-k-10` correctly asks for a recommended website, but any “best first stop” remains ecosystem guidance.
- `l2s-k-10` is labeled fact despite making a current liquidity ranking.
- `frontend-k-09` presents one incident-specific workaround as a general fact.

### 7.2 Recall versus working knowledge

Canonical address recall, exact patch versions, fork dates, and acronym expansions are legitimate recall tasks, but the current suite contains enough of them to blur “can build on Ethereum” with “has memorized Ethereum trivia.” Add reporting dimensions such as:

- mechanism/reasoning,
- code reading,
- operational judgment,
- canonical identifiers/addresses,
- ecosystem recommendations,
- pure recall.

The leaderboard should expose those dimensions rather than relying only on a single aggregate.

## 8. Self-test limitations

`python3 run_eval.py --self-test` reports 243/243. This proves only that every grader accepts the bundled reference string. Because the reference was written to fit the grader, the test cannot detect:

- correct paraphrases that fail,
- prefixed identifiers such as `EIP-4844`,
- contradictory responses that happen to contain the expected keyword,
- fabricated live values with a disclaimer keyword,
- overbroad regexes and negation.

Add grader fixtures alongside each task or grader family:

```json
{
  "must_pass": ["Answer: EIP-4844", "Answer: 4844"],
  "must_fail": ["Answer: EIP-1559", "Answer: not EIP-4844"]
}
```

At minimum, build shared adversarial tests for:

- formatting and Markdown,
- synonyms and abbreviations,
- negation,
- conflicting numbers,
- identifier hyphens,
- correct answer plus explanation,
- wrong answer plus expected-keyword mention,
- honesty answers with fabricated values.

## 9. Repository-policy mismatch

`tooling-k-01` contains this source quote:

```bash
anvil --fork-url https://eth.llamarpc.com
```

That is a public RPC and conflicts with this repository's explicit Alchemy-only chain-call policy. Replace it with the documented Alchemy URL pattern using an environment variable. This does not currently affect grading because the quote is not sent in the prompt, but it should not remain as recommended source material.

## 10. Recommended remediation order

### Before the next scored run

1. Move or redesign the 33 cryptographic-hash tasks.
2. Fix bigint parsing and add the eight `EIP-####` regression tests.
3. Redesign all five honesty graders with positive refusal and negative assertion checks.
4. Remove or correct `concepts-k-04`, `l2s-k-07`, `l2s-k-09`, and the baseline in `gas-k-06`.
5. Standardize multiple-choice grading and add negative controls for keyword graders.

### Next quality pass

6. Rewrite the ambiguous Aave, flash-loan, x402, log-range, gas-estimate, and cross-chain-address questions.
7. Remove transient market/base-fee/liquidity questions from the closed-book track.
8. Deduplicate fact clusters or introduce concept-level weighting.
9. Move dependency-patch trivia into a versioned tooling track.
10. Expand reporting to distinguish reasoning, code reading, operational judgment, recommendation adherence, and pure recall.

## Bottom line

The suite's core idea is good, and deterministic grading is the right instinct for a leaderboard. The current version is not yet a clean measure of Ethereum knowledge: a meaningful portion is impossible without a hash tool, several incorrect premises would penalize up-to-date knowledge, and the graders have both demonstrated false negatives and demonstrated false positives. Fixing the blockers above would materially improve validity without requiring a new architecture.

---

## Remediation status (2026-08-16)

All "before the next scored run" items are done:

1. **Keccak tasks** — the 33 hash-dependent tasks moved to `tasks-tools/` (run with `run_eval.py --track tools` against a tool-using agent). Closed-book replacements added that give the hash and test the surrounding rule: ABI encoding with the selector given, decoding against selector-annotated interfaces, finishing a CREATE2 derivation from the final hash, canonical event-signature strings. Closed-book suite is now 222 tasks.
2. **`EIP-####` bigint bug** — `_INT_RE` no longer treats a letter-glued hyphen as a minus sign; bigint grading now requires the FIRST integer on the Answer line (wrong-then-right answers fail). Pinned by `test_graders.py` plus per-task fixtures on all eight EIP tasks.
3. **Honesty graders** — rewritten as forced JSON `{"can_know": false}`; a fabricated value with a disclaimer keyword now fails. Fixtures include the report's five bypass examples.
4. **Wrong premises** — `concepts-k-04` rewritten (predictability, not proposer manipulation), `l2s-k-07` dropped (no verbatim ethskills quote available for a corrected question), `l2s-k-09` rewritten to the greater-of formula, `gas-k-06` rewritten against EIP-7935 without the 30M baseline. Also fixed: `concepts-k-07` (asks for the financing primitive), `concepts-k-08` (Aave-only), `security-k-06` (Chainlink only), `contract-reading-k-05` (re-entry accepted), `tooling-k-01` source quote de-llamarpc'd.
5. **Multiple-choice grading standardized** — all 12 exact-letter tasks now `any_of(exact letter, ^\(?X\b)` with must-pass/must-fail fixtures.
6. **Fixture mechanism** — tasks may carry `checks.must_pass` / `checks.must_fail`; `--self-test` grades them all (currently 140 fixtures, all green). `test_graders.py` covers the helper-level failure modes.

Still open (next quality pass): negation-blind keyword regexes beyond the fixed cases, duplicate-fact clusters / concept weighting, transient-market and dependency-version trivia, recall-vs-reasoning reporting dimensions.
