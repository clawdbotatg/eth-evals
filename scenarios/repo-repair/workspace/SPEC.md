# Sale spec

`Sale` sells a product token for a payment token at an oracle price.

- **payment token**: 6 decimals (USDC-like)
- **product token**: 18 decimals
- **oracle answer**: 8 decimals, USD per whole product token
  (Chainlink-style `latestRoundData`)

## Required behavior

1. **Correct pricing / decimals.** To buy `productAmount` (in 18-decimal
   product units), the buyer pays, in 6-decimal payment units:

   `cost = productAmount * price / 1e20`

   (18-decimal product × 8-decimal price → 6-decimal payment). The buyer
   receives exactly `productAmount` of the product token.

2. **Oracle freshness.** A price whose `updatedAt` is older than `maxAge`
   seconds must be rejected — `buy` reverts rather than trading on a stale
   price. A non-positive answer is also rejected.

3. **Proceeds accounting.** `totalProceeds` tracks the payment collected so
   far. `withdrawProceeds(to)` sends exactly the accumulated proceeds and
   resets the counter.

4. **Access control.** Only the `owner` (the deployer) may call
   `withdrawProceeds`.

## Your job

Make `Sale` compile and satisfy every point above. Keep the contract name,
the constructor signature, and the external function signatures (`price`,
`buy(uint256)`, `withdrawProceeds(address)`). The other files in `src/` are
correct — the bug is in `Sale.sol`.
