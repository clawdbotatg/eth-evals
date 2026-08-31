# Task: repair a broken Foundry repo

You are an agent working in this Foundry project with shell access. `forge`
is installed. Read `SPEC.md` first.

`src/Sale.sol` does not compile and, once it does, still misbehaves. The
other files in `src/` (`Mocks.sol`, `Registry.sol`) are correct — don't
change them.

Fix `src/Sale.sol` so the project builds and meets every point in `SPEC.md`:
correct decimal-aware pricing, oracle-staleness rejection, proceeds
accounting, and owner-only withdrawals.

Keep the contract name `Sale`, the constructor signature, and the external
function signatures. There is nothing to submit besides the fixed file —
leave it at `src/Sale.sol`. Grading recompiles it against a hidden test
suite; prose is ignored.
