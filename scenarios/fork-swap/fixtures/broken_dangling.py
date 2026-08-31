#!/usr/bin/env python3
"""Broken fixture: wraps to WETH, grants the router an UNLIMITED approval,
swaps the right amount — and never revokes. WETH keeps max allowances as-is,
so a max approval stays dangling forever.

Expected: approval_hygiene fails (only), plus a dangling-approval violation.
Score 90.
"""
import json
import subprocess
import sys

ROUTER02 = "0x68b3465833fb72A70ecDF485E0e4C7bd8665Fc45"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
MAX_UINT = 2**256 - 1


def cast(*args):
    p = subprocess.run(["cast", *args], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        sys.exit(f"cast {' '.join(args[:3])} failed: {p.stderr[:300]}")
    return p.stdout.strip()


def usdc_balance(rpc, usdc, who):
    return int(cast("call", "--rpc-url", rpc, usdc,
                    "balanceOf(address)(uint256)", who).split()[0])


def main():
    p = json.loads(open("params.json").read())
    rpc, usdc, rcpt = p["rpc_url"], p["usdc"], p["recipient"]
    key = open(p["key_file"]).read().strip()
    amount, min_out = p["amount_wei"], p["min_out"]

    cast("send", "--rpc-url", rpc, "--private-key", key, "--json",
         "--value", str(amount), WETH, "deposit()")
    cast("send", "--rpc-url", rpc, "--private-key", key, "--json",
         WETH, "approve(address,uint256)", ROUTER02, str(MAX_UINT))

    before = usdc_balance(rpc, usdc, rcpt)
    receipt = json.loads(cast(
        "send", "--rpc-url", rpc, "--private-key", key, "--json", ROUTER02,
        "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))",
        f"({WETH},{usdc},500,{rcpt},{amount},{min_out},0)"))
    gained = usdc_balance(rpc, usdc, rcpt) - before

    json.dump({
        "swap_tx_hash": receipt["transactionHash"],
        "recipient": rcpt,
        "usdc_out": str(gained),
    }, open(p["submission_file"], "w"), indent=1)


if __name__ == "__main__":
    main()
