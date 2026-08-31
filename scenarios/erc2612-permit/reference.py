#!/usr/bin/env python3
"""Reference solution — must score 100/100 on every seed (harness exit test).

Runs inside the agent workspace like a real agent: reads params.json + key
files, signs the EIP-712 permit digest with the owner key (off-chain), then
sends permit + transferFrom from the relayer, and writes submission.json.
"""
import json
import subprocess
import sys

PERMIT_TYPES = "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"


def cast(*args):
    p = subprocess.run(["cast", *args], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        sys.exit(f"cast {' '.join(args[:3])} failed: {p.stderr[:300]}")
    return p.stdout.strip()


def main():
    p = json.loads(open("params.json").read())
    rpc, token = p["rpc_url"], p["token"]
    owner_key = open(p["owner_key_file"]).read().strip()
    relayer_key = open(p["relayer_key_file"]).read().strip()
    owner = cast("wallet", "address", "--private-key", owner_key)
    relayer = cast("wallet", "address", "--private-key", relayer_key)
    amount, deadline = p["amount_wei"], p["deadline"]

    ds = cast("call", "--rpc-url", rpc, token, "DOMAIN_SEPARATOR()(bytes32)")
    nonce = cast("call", "--rpc-url", rpc, token, "nonces(address)(uint256)", owner).split()[0]
    typehash = cast("keccak", PERMIT_TYPES)
    struct = cast("keccak", cast("abi-encode", "f(bytes32,address,address,uint256,uint256,uint256)",
                                 typehash, owner, relayer, str(amount), nonce, str(deadline)))
    digest = cast("keccak", "0x1901" + ds[2:] + struct[2:])
    sig = cast("wallet", "sign", "--no-hash", "--private-key", owner_key, digest)
    r, s, v = sig[0:66], "0x" + sig[66:130], str(int(sig[130:132], 16))

    permit_rcpt = json.loads(cast(
        "send", "--rpc-url", rpc, "--private-key", relayer_key, "--json", token,
        "permit(address,address,uint256,uint256,uint8,bytes32,bytes32)",
        owner, relayer, str(amount), str(deadline), v, r, s))
    transfer_rcpt = json.loads(cast(
        "send", "--rpc-url", rpc, "--private-key", relayer_key, "--json", token,
        "transferFrom(address,address,uint256)", owner, p["recipient"], str(amount)))

    json.dump({
        "permit_tx_hash": permit_rcpt["transactionHash"],
        "transfer_tx_hash": transfer_rcpt["transactionHash"],
        "owner": owner,
        "recipient": p["recipient"],
    }, open(p["submission_file"], "w"), indent=1)
    print(f"permit {permit_rcpt['transactionHash']}, transfer {transfer_rcpt['transactionHash']}")


if __name__ == "__main__":
    main()
