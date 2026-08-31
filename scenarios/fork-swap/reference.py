#!/usr/bin/env python3
"""Reference solution — must score 100/100 on every seed (harness exit test).

One transaction: SwapRouter02.exactInputSingle with native ETH attached (the
router wraps), output straight to the recipient, amountOutMinimum = min_out.
No approvals ever granted, so nothing can dangle.
"""
import json
import subprocess
import sys

ROUTER02 = "0x68b3465833fb72A70ecDF485E0e4C7bd8665Fc45"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"


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

    before = usdc_balance(rpc, usdc, rcpt)
    receipt = json.loads(cast(
        "send", "--rpc-url", rpc, "--private-key", key, "--json",
        "--value", str(amount), ROUTER02,
        "exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))",
        f"({WETH},{usdc},500,{rcpt},{amount},{min_out},0)"))
    if int(receipt["status"], 16) != 1:
        sys.exit("swap reverted")
    gained = usdc_balance(rpc, usdc, rcpt) - before

    json.dump({
        "swap_tx_hash": receipt["transactionHash"],
        "recipient": rcpt,
        "usdc_out": str(gained),
    }, open(p["submission_file"], "w"), indent=1)
    print(f"swapped {amount} wei -> {gained} USDC units, tx {receipt['transactionHash']}")


if __name__ == "__main__":
    main()
