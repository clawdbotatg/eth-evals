# Task: gasless token transfer via EIP-2612 permit

You are an agent working in this directory with shell access. A local
Ethereum node is running at **{rpc_url}** (do not use any other endpoint).
Inspect the node yourself for anything not stated here (chain id, balances,
token state).

An ERC-20 token with EIP-2612 permit support is deployed at **{token}**
(name "PermitToken", version "1").

Two accounts, keys in this directory:

- `owner.key` — the **owner**. Holds PMT tokens but has **zero ETH**. It
  must never send a transaction; it can only sign.
- `relayer.key` — the **relayer**. Holds ETH and pays all gas.

**Do this:**

1. Have the owner sign an EIP-2612 permit (an EIP-712 typed-data signature —
   mind the domain: name, version, chain id, verifying contract) approving
   the **relayer** to spend **exactly {amount_wei}** token wei. Use
   deadline **{deadline}** and the owner's current permit nonce.
2. From the **relayer**, call `permit(...)` on the token with that signature.
3. From the **relayer**, call `transferFrom(...)` moving **exactly
   {amount_wei}** token wei from the owner to `{recipient}`.
4. Send **exactly two transactions total**, both from the relayer — first
   the permit, then the transferFrom. The owner sends none.
5. Permit exactly the amount you move: after the transfer the owner's
   allowance to the relayer must be **zero**. Never use an unlimited
   approval.

**Then write `submission.json`** in this directory:

```json
{{
  "permit_tx_hash": "0x…",
  "transfer_tx_hash": "0x…",
  "owner": "0x…owner address…",
  "recipient": "0x…recipient address…"
}}
```

Grading is done from chain state and the submitted transactions — prose is
ignored.
