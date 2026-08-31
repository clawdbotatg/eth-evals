#!/usr/bin/env python3
"""Broken fixture: signs the permit against a mainnet (chainId 1) EIP-712
domain instead of the local chain's — the classic replay-domain mistake.

Both transactions land but revert. Expected: permit_tx_correct,
transfer_tx_correct, permit_consumed, exact_allowance, and tokens_moved all
fail. Score 20 (submission_valid + owner_gasless).
"""
import json
import subprocess
import sys

PERMIT_TYPES = "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"
DOMAIN_TYPES = "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"


def cast(*args):
    p = subprocess.run(["cast", *args], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        sys.exit(f"cast {' '.join(args[:3])} failed: {p.stderr[:300]}")
    return p.stdout.strip()


def send_maybe_revert(rpc, relayer_key, token, sig, *args):
    """Send with a fixed gas limit so a reverting call still broadcasts;
    recover the tx hash even when cast exits nonzero on the failed receipt."""
    p = subprocess.run(
        ["cast", "send", "--rpc-url", rpc, "--private-key", relayer_key,
         "--gas-limit", "300000", "--json", token, sig, *args],
        capture_output=True, text=True, timeout=60)
    try:
        return json.loads(p.stdout.strip())["transactionHash"]
    except Exception:  # noqa: BLE001
        blk = json.loads(cast("rpc", "--rpc-url", rpc, "eth_getBlockByNumber", "latest", "false"))
        return blk["transactions"][-1]


def main():
    p = json.loads(open("params.json").read())
    rpc, token = p["rpc_url"], p["token"]
    owner_key = open(p["owner_key_file"]).read().strip()
    relayer_key = open(p["relayer_key_file"]).read().strip()
    owner = cast("wallet", "address", "--private-key", owner_key)
    relayer = cast("wallet", "address", "--private-key", relayer_key)
    amount, deadline = p["amount_wei"], p["deadline"]

    # domain separator hand-built with chainId 1 — the wrong chain
    ds = cast("keccak", cast(
        "abi-encode", "f(bytes32,bytes32,bytes32,uint256,address)",
        cast("keccak", DOMAIN_TYPES), cast("keccak", "PermitToken"),
        cast("keccak", "1"), "1", token))
    typehash = cast("keccak", PERMIT_TYPES)
    struct = cast("keccak", cast("abi-encode", "f(bytes32,address,address,uint256,uint256,uint256)",
                                 typehash, owner, relayer, str(amount), "0", str(deadline)))
    digest = cast("keccak", "0x1901" + ds[2:] + struct[2:])
    sig = cast("wallet", "sign", "--no-hash", "--private-key", owner_key, digest)
    r, s, v = sig[0:66], "0x" + sig[66:130], str(int(sig[130:132], 16))

    permit_hash = send_maybe_revert(
        rpc, relayer_key, token,
        "permit(address,address,uint256,uint256,uint8,bytes32,bytes32)",
        owner, relayer, str(amount), str(deadline), v, r, s)
    transfer_hash = send_maybe_revert(
        rpc, relayer_key, token,
        "transferFrom(address,address,uint256)", owner, p["recipient"], str(amount))

    json.dump({
        "permit_tx_hash": permit_hash,
        "transfer_tx_hash": transfer_hash,
        "owner": owner,
        "recipient": p["recipient"],
    }, open(p["submission_file"], "w"), indent=1)


if __name__ == "__main__":
    main()
