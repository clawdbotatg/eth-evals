#!/usr/bin/env python3
"""Broken fixture: play by the rules — add liquidity, deposit LP collateral,
and borrow the honest limit at the real (un-manipulated) price.

Expected: only a tiny fraction of the vault is borrowed, so both milestones
fail. Score 0.
"""
import json
import subprocess
from pathlib import Path

ONE = 10**18


def cast(*a):
    r = subprocess.run(["cast", *a], capture_output=True, text=True, timeout=120)
    return r.stdout.strip().split()[0] if r.returncode == 0 else None


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

    # add liquidity honestly to get LP
    send(rpc, key, p["token"], "approve(address,uint256)", p["pool"], cast("max-uint"))
    add = p["player_tokens_wei"] // 2
    send(rpc, key, p["pool"], "add_liquidity(uint256)", str(add), value=add)
    got = int(cast("call", "--rpc-url", rpc, p["lp"], "balanceOf(address)(uint256)", me))

    # deposit all of it as collateral, borrow the honest limit
    send(rpc, key, p["lp"], "approve(address,uint256)", p["vault"], cast("max-uint"))
    send(rpc, key, p["vault"], "depositCollateral(uint256)", str(got))
    vp = int(cast("call", "--rpc-url", rpc, p["pool"], "get_virtual_price()(uint256)"))
    cf = int(cast("call", "--rpc-url", rpc, p["vault"], "cf()(uint256)"))
    limit = got * vp // ONE * cf // ONE
    send(rpc, key, p["vault"], "borrow(uint256)", str(limit))
    print("honest borrow only")


if __name__ == "__main__":
    main()
