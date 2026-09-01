#!/usr/bin/env python3
"""Broken fixture: captures flags 1, 2, 3 correctly (seeded key), but the
Challenge4 helper pays one wei short.

Expected: only flag4 fails. Score 65.
"""
import json
import subprocess
import sys
from pathlib import Path


def cast(*a):
    p = subprocess.run(["cast", *a], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        sys.exit(f"cast failed: {p.stderr[:200]}")
    return p.stdout.strip()


def send(rpc, key, to, *args, value=None):
    cmd = ["send", "--rpc-url", rpc, "--private-key", key, to, *args]
    if value is not None:
        cmd += ["--value", str(value)]
    return cast(*cmd)


def main():
    p = json.loads(Path("params.json").read_text())
    rpc = p["rpc_url"]
    key = Path(p["key_file"]).read_text().strip()
    me = cast("wallet", "address", "--private-key", key)
    underpay = p["expected_wei"] - 1

    send(rpc, key, p["challenge1"], "registerTeam(string,uint8)", "team", "1")
    k = cast("keccak", cast("concat-hex", me, p["challenge2"]))
    send(rpc, key, p["challenge2"], "mintFlag(bytes32)", k)

    Path("src/Helpers.sol").write_text(f"""//SPDX-License-Identifier: MIT
pragma solidity >=0.8.0 <0.9.0;
interface IC {{ function mintFlag() external; }}
contract Helper3 {{
    address c;
    constructor(address _c) {{ c = _c; }}
    function accessKey() external pure returns (string memory) {{ return "{p['access_key']}"; }}
    function trigger() external {{ IC(c).mintFlag(); }}
}}
contract Helper4 {{
    address payable c;
    constructor(address _c) {{ c = payable(_c); }}
    function go() external {{ IC(c).mintFlag(); }}
    receive() external payable {{ (bool ok, ) = c.call{{value: {underpay}}}(""); require(ok, "fwd"); }}
}}
""")
    subprocess.run(["forge", "build"], capture_output=True, text=True)

    def code(c):
        return json.loads(Path(f"out/Helpers.sol/{c}.json").read_text())["bytecode"]["object"]

    def pad(a):
        return a.lower().replace("0x", "").rjust(64, "0")

    def deploy(cr):
        return json.loads(cast("send", "--rpc-url", rpc, "--private-key", key,
                               "--create", cr, "--json"))["contractAddress"]

    h3 = deploy(code("Helper3") + pad(p["challenge3"]))
    send(rpc, key, h3, "trigger()")
    h4 = deploy(code("Helper4") + pad(p["challenge4"]))
    send(rpc, key, h4, value=p["expected_wei"] * 4)
    subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key, h4, "go()"],
                   capture_output=True, text=True)   # reverts (underpaid)
    print("flags 1-3, flag 4 underpaid")


if __name__ == "__main__":
    main()
