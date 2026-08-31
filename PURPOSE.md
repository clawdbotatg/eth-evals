# Purpose

eth-evals measures how good an LLM is at Ethereum.

Three sections, matching how a builder actually levels up:

1. **Concepts** — does it understand Ethereum? What it's for, how it works,
   what things cost today, what the protocol looks like right now.
2. **Transactions** — can it build and propose real transactions? Calldata,
   signing, nonces, approvals, permits, swaps.
3. **Building** — can it build on Ethereum? Solidity, security, standard
   patterns, working code that passes real tests on a real chain.

Anything that can answer a prompt can be scored: a bare LLM, an agent with
tools, a full harness, a harness plus skills. Same suite, same graders. When
a new model ships, we run it and see if it understands Ethereum better than
the last one.

## What this is not

Not a trivia contest and not a trick suite. Every question is mainstream
knowledge a working Ethereum builder has. Difficulty comes from being
**current** (the chain moves; training data doesn't) and **applied** (graded
by whether the transaction lands and the code works, not whether the prose
sounds right) — never from esoterica.
