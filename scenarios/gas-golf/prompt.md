# Task: implement `solve` — and make it cheap

You are an agent working in this Foundry project with shell access. `forge`
is installed. Read `SPEC.md`.

`src/Solution.sol` has a stub. Implement `solve(uint256[] calldata xs)` to
return the weighted sum `xs[0]*1 + xs[1]*2 + ... + xs[n-1]*n` with wrapping
arithmetic.

Correctness alone is not the whole task. Grading measures the **gas** of a
`solve` call on a length-32 array and rewards two budgets:

- getting under **16000** gas (any clean solution),
- getting under **8000** gas (requires real optimization).

You can measure your own gas: write a small `forge` test that calls `solve`
on a 32-element array and prints `gasleft()` before and after, and iterate.
Keep the contract name `Solution`, the signature, and solc 0.8.28 with the
optimizer on. Leave your answer at `src/Solution.sol`. Grading recompiles it;
prose is ignored.
