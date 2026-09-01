#!/usr/bin/env python3
"""Reference solution — must capture all four flags (harness exit test).

Runs in the workspace like an agent: registers a team, computes the
Challenge2 key, and writes + deploys two helper contracts (seeded with this
run's access key and required wei) to capture flags 3 and 4.
"""
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


def main():
    p = json.loads(Path("params.json").read_text())
    rpc = p["rpc_url"]
    key = Path(p["key_file"]).read_text().strip()
    me = cast("wallet", "address", "--private-key", key)

    # Flag 1: register a team
    send(rpc, key, p["challenge1"], "registerTeam(string,uint8)", "reference", "1")

    # Flag 2: key = keccak256(abi.encodePacked(msg.sender, address(challenge2)))
    packed = cast("concat-hex", me, p["challenge2"])
    k = cast("keccak", packed)
    send(rpc, key, p["challenge2"], "mintFlag(bytes32)", k)

    # Flags 3 & 4: build seeded helper contracts
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
    receive() external payable {{
        (bool ok, ) = c.call{{value: {p['expected_wei']}}}("");
        require(ok, "fwd");
    }}
}}
""")
    if subprocess.run(["forge", "build"], capture_output=True, text=True).returncode != 0:
        sys.exit("forge build failed")

    def code(contract):
        j = json.loads(Path(f"out/Helpers.sol/{contract}.json").read_text())
        return j["bytecode"]["object"]

    def pad(a):
        return a.lower().replace("0x", "").rjust(64, "0")

    def deploy(creation):
        out = json.loads(cast("send", "--rpc-url", rpc, "--private-key", key,
                              "--create", creation, "--json"))
        return out["contractAddress"]

    h3 = deploy(code("Helper3") + pad(p["challenge3"]))
    send(rpc, key, h3, "trigger()")

    h4 = deploy(code("Helper4") + pad(p["challenge4"]))
    send(rpc, key, h4, value=p["expected_wei"] * 4)     # fund the helper
    send(rpc, key, h4, "go()")

    print("captured flags 1-4")


if __name__ == "__main__":
    main()
