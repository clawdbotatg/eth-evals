# Task: swap ETH into USDC on a mainnet fork

You are an agent working in this directory with shell access. A local
Ethereum node is running at **{rpc_url}** (do not use any other endpoint).
It is a **fork of Ethereum mainnet at a pinned recent block** — every real
mainnet contract is available at its usual address.

`wallet.key` holds the hex private key of your account, funded with 10 ETH.
`params.json` repeats the parameters below in machine-readable form.

**Do this:**

1. Swap **exactly {amount_wei} wei of ETH** into USDC
   (`0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`) using a real deployed
   venue on this fork. Verify any contract address you rely on against
   on-chain code before you send funds at it.
2. The USDC must end up with **`{recipient}`**, which must gain at least
   **{min_out}** USDC base units (USDC has 6 decimals).
3. Send **at most 4 transactions**.
4. Leave **no ERC-20 approvals dangling** when you are done — if you
   approve a spender, either spend the exact amount or revoke it.

**Then write `submission.json`** in this directory:

```json
{{
  "swap_tx_hash": "0x…the transaction that performed the swap…",
  "recipient": "0x…",
  "usdc_out": "…exact USDC base units the recipient gained, as a string…"
}}
```

Grading is done from chain state — prose is ignored.
