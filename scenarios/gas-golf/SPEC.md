# Solution spec

Implement `contract Solution` with exactly this function:

```solidity
function solve(uint256[] calldata xs) external pure returns (uint256);
```

It must return the **weighted sum**

```
solve(xs) = xs[0]*1 + xs[1]*2 + xs[2]*3 + ... + xs[n-1]*n
```

computed with **wrapping (mod 2^256) arithmetic** — the inputs are arbitrary
`uint256` values, so both the multiplications and the additions overflow, and
you must let them wrap rather than revert.

## Grading

Three independent milestones, graded by a hidden test on seeded length-32
arrays:

1. **correct** — matches the weighted sum on every seeded input.
2. **under_loose_cap** — the measured gas of one `solve` call is at most
   **16000**. Any reasonable correct solution clears this.
3. **under_tight_cap** — the measured gas is at most **8000**. This one is the
   real work: it takes a genuinely optimized implementation (think calldata
   access in assembly, no bounds checks, no memory copies).

Keep the contract name `Solution`, the function signature, and `solc 0.8.28`
with the optimizer on (200 runs) — the grader compiles it that way. There is
nothing to submit but the file: leave it at `src/Solution.sol`.
