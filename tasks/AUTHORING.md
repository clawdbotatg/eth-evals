# Authoring knowledge tasks for eth-evals

Each task interrogates a **vanilla LLM with no docs and no tools** on knowledge
asserted in an ethskills.com SKILL.md file. The point of the eval is to measure
how much of ethskills a model already knows, so:

**The ground truth is the skill file's claim, not your own knowledge.** Every
task must carry a `source_quote` field with the verbatim line(s) from the
SKILL.md that the expected answer comes from. If you can't quote it, don't
write the task.

## Task schema (one JSON object per line, .jsonl)

```json
{"id": "<category>-k-01", "category": "<category>", "source": "<skill-name>",
 "kind": "fact|recommendation",
 "prompt": "…question… \nEnd your reply with a line of the form \"Answer: <short answer>\".",
 "grader": {…},
 "reference": "Answer: …a passing answer…",
 "source_quote": "verbatim text from SKILL.md",
 "checks": {"must_pass": ["Answer: …paraphrase…"], "must_fail": ["Answer: …wrong…"]}}
```

`checks` (optional but strongly encouraged): adversarial fixtures graded by
`--self-test`. `must_pass` = correct answers in other phrasings (prefixed
identifiers, elaborations, synonyms); `must_fail` = wrong answers that a sloppy
grader might accept (negations, wrong values, keyword mentions). The reference
alone proves nothing — it was written to fit the grader.

`kind`: `fact` = objective (an EIP number, a mechanism, an interface member).
`recommendation` = ethskills' opinionated guidance (which tool, which pattern) —
still valid to test, but tagged so reports can split them.

## Graders available (deterministic — there is no LLM judge)

- `{"type":"exact","expect":"str"}` — normalized compare (whitespace/quotes/
  backticks stripped; case-insensitive unless `"case_sensitive":true`). Checked
  against the whole response, its last line, and the `Answer:` line.
- `{"type":"regex","pattern":"…"}` — searched in the `Answer:` line (or add
  `"on":"full"` for the whole response). Case-insensitive by default.
- `{"type":"regex_all","patterns":["…","…"]}` — every pattern must match.
- `{"type":"json","expect":{…}}` — model told "Reply with JSON only". Strings
  compare normalized; `"~sub"` means substring; dicts allow extra keys.
- `{"type":"bigint","expect":123}` — the FIRST integer (decimal or 0x hex) on
  the Answer line must match exactly; `EIP-4844` parses as 4844, not -4844.
- `{"type":"numeric","expect":1.5,"tol":0.01}`
- `{"type":"any_of","options":[grader,…]}` — pass if any sub-grader passes.

## Quality rules

1. **The question must uniquely determine the answer.** A knowledgeable
   Ethereum dev reading only the question should converge on one answer. If two
   defensible answers exist, either constrain the question until one survives,
   use `any_of`/regex alternation to accept the synonyms, or drop the task.
2. **Never leak the answer in the question.**
3. **Force a short, gradeable answer**: end prompts with the `Answer:` line
   instruction, or "Reply with JSON only: {schema}". Multiple-choice (A/B/C/D)
   is fine and often the cleanest for conceptual material.
4. **Regex discipline**: a wrong answer must not accidentally match. Anchor on
   distinctive tokens (`checks?-effects?-interactions?`, `\b4337\b`), never on
   generic words (`secure`, `contract`). For "name the attack" style questions,
   alternate the accepted names: `re(entranc|entry)`.
5. **Test transferable Ethereum knowledge the file asserts** — mechanisms,
   interfaces, numbers, tool behavior, failure modes. Do NOT test the file's
   own structure, marketing copy, or internal phase names that only make sense
   inside ethskills (exception: a `recommendation` task about which tool/pattern
   to use is good — that's the ecosystem consensus the file encodes).
6. **Difficulty mix** per skill: ~3 easy (any competent model should pass),
   ~4 medium, ~3 hard/esoteric (the file's deepest cuts). The hard tail is what
   separates models.
7. **No contested/aging claims** (prices, "currently the cheapest L2", TVL).
   Version-pinned facts are fine if stated as such in the file. Fork-roadmap
   questions are the exception: date-tag them in the prompt ("as of mid-2026")
   and expect them to be refreshed each upgrade.
8. **Canon fallback (v1 categories only — mev, cypherpunk, cryptoecon,
   roadmap):** prefer an ethskills quote as the answer key. When the topic
   isn't in ethskills, a fact is allowed if it is unambiguous, stable, and
   canonical (an EIP spec, the Cypherpunk Manifesto, Flashbots docs) — then
   `source_quote` names that source. Never invent from model memory alone.
9. **Self-contained code questions (contract-reading):** when the prompt
   includes the full Solidity source, the code itself is the ground truth —
   no external quote needed; set `source_quote` to "self-contained".
10. **No unaided keccak.** A closed-book task may never require producing a
    hash digest (selector, topic0, CREATE/CREATE2 address, EIP-55 casing,
    mapping slot) — no model can compute keccak in its weights. Either give
    the hash in the prompt and test the surrounding rule, or put the task in
    `tasks-tools/` (run with `--track tools` against a tool-using agent).
11. **Multiple-choice grading**: always `any_of` of an exact letter plus the
    tolerant regex `^\(?X\b` — "Answer: B — reason" must pass. Never bare
    `{"type":"exact","expect":"B"}`.
12. **Honesty tasks force JSON** (`{"can_know": false, …}`) — a disclaimer
    keyword next to a fabricated value must not pass, and keyword regexes
    can't tell the difference.
