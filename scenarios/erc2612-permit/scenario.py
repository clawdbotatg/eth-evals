"""erc2612-permit: generation + hidden grading.

Owner holds tokens but zero ETH; a funded relayer must execute an EIP-2612
permit signed off-chain by the owner, then transferFrom. Grades EIP-712
signing (the chain-id-bound domain), delegated execution, and approval
hygiene (exact allowance, nothing dangling) — from chain state only.
"""
import hashlib
import json
import random
import subprocess
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.ethrpc import rpc, hexint  # noqa: E402

SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GWEI = 10**9
# anvil's default unlocked dev account 0 — deploys the token at setup
ANVIL0 = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

SEL_PERMIT = "0xd505accf"
SEL_TRANSFER_FROM = "0x23b872dd"
SEL_TRANSFER = "0xa9059cbb"
SEL_BALANCE_OF = "0x70a08231"
SEL_ALLOWANCE = "0xdd62ed3e"
SEL_NONCES = "0x7ecebe00"


def _derive_key(seed, role):
    h = hashlib.sha256(f"eth-eval-permit2612-{seed}-{role}".encode()).digest()
    k = int.from_bytes(h) % (SECP256K1_N - 1) + 1
    return f"0x{k:064x}"


def _addr(privkey):
    out = subprocess.run(["cast", "wallet", "address", "--private-key", privkey],
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(f"cast wallet address failed: {out.stderr[:200]}")
    return out.stdout.strip()


def _pad(v):
    return f"{int(v, 16) if isinstance(v, str) else int(v):064x}"


def generate(seed):
    rng = random.Random(f"permit2612-{seed}")
    owner_key = _derive_key(seed, "owner")
    relayer_key = _derive_key(seed, "relayer")
    amount = rng.randrange(10**18, 10**21) | 1     # odd token-wei amount
    inst = {
        "seed": seed,
        "chain_id": 32_000_000 + rng.randrange(1_000_000),
        "owner_key": owner_key,
        "owner": _addr(owner_key),
        "relayer_key": relayer_key,
        "relayer": _addr(relayer_key),
        "recipient": _addr(_derive_key(seed, "recipient")),
        "amount_wei": amount,
        "owner_start_wei": amount + (rng.randrange(10**17, 10**18) | 1),
        "deadline": 20_000_000_000,
        "base_fee_wei": 1 * GWEI,
        "relayer_fund_wei": 10 * 10**18,
    }
    return inst


def setup_chain(inst, rpc_url):
    """Deploy the token from anvil's dev account, seed the owner with tokens
    (and deliberately zero ETH), fund only the relayer."""
    bytecode = (Path(__file__).parent / "token_bytecode.txt").read_text().strip()
    txh = rpc(rpc_url, "eth_sendTransaction", [{"from": ANVIL0, "data": bytecode}])
    receipt = rpc(rpc_url, "eth_getTransactionReceipt", [txh])
    token = receipt["contractAddress"]
    assert token and hexint(receipt["status"]) == 1, "token deploy failed"
    inst["token"] = token

    data = SEL_TRANSFER + _pad(inst["owner"]) + _pad(inst["owner_start_wei"])
    txh = rpc(rpc_url, "eth_sendTransaction", [{"from": ANVIL0, "to": token, "data": data}])
    assert hexint(rpc(rpc_url, "eth_getTransactionReceipt", [txh])["status"]) == 1

    rpc(rpc_url, "anvil_setBalance", [inst["relayer"], hex(inst["relayer_fund_wei"])])
    assert hexint(rpc(rpc_url, "eth_chainId")) == inst["chain_id"]
    assert hexint(rpc(rpc_url, "eth_getBalance", [inst["owner"], "latest"])) == 0
    assert _tok(rpc_url, token, SEL_BALANCE_OF + _pad(inst["owner"])) == inst["owner_start_wei"]


def workspace_files(inst, rpc_url):
    prompt = (Path(__file__).parent / "prompt.md").read_text().format(
        rpc_url=rpc_url, token=inst["token"], amount_wei=inst["amount_wei"],
        deadline=inst["deadline"], recipient=inst["recipient"])
    params = {
        "rpc_url": rpc_url,
        "token": inst["token"],
        "recipient": inst["recipient"],
        "amount_wei": inst["amount_wei"],
        "deadline": inst["deadline"],
        "owner_key_file": "owner.key",
        "relayer_key_file": "relayer.key",
        "submission_file": "submission.json",
    }
    return {
        "prompt.md": prompt,
        "params.json": json.dumps(params, indent=1),
        "owner.key": inst["owner_key"] + "\n",
        "relayer.key": inst["relayer_key"] + "\n",
    }


def _tok(rpc_url, token, data):
    """uint256 read from the token via eth_call."""
    return hexint(rpc(rpc_url, "eth_call", [{"to": token, "data": data}, "latest"]))


def _tx_ok(rpc_url, inst, tx_hash, selector):
    """(pass, detail) for: tx exists, sent by relayer, to the token, calls
    `selector`, and its receipt succeeded."""
    try:
        tx = rpc(rpc_url, "eth_getTransactionByHash", [tx_hash])
        receipt = rpc(rpc_url, "eth_getTransactionReceipt", [tx_hash])
    except Exception:  # noqa: BLE001
        tx = receipt = None
    if not tx or not receipt:
        return False, "transaction not found on chain"
    checks = {
        "from_relayer": tx["from"].lower() == inst["relayer"].lower(),
        "to_token": (tx.get("to") or "").lower() == inst["token"].lower(),
        "selector": (tx.get("input") or "")[:10].lower() == selector,
        "status": hexint(receipt["status"]) == 1,
    }
    return all(checks.values()), \
        ("" if all(checks.values()) else "bad: " + ",".join(k for k, v in checks.items() if not v))


def grade(inst, workspace, rpc_url):
    ms = {}
    violations = []

    def m(name, ok, detail=""):
        ms[name] = {"pass": bool(ok), "detail": detail}

    sub_path = Path(workspace) / "submission.json"
    sub, sub_err = None, ""
    if sub_path.exists():
        try:
            sub = json.loads(sub_path.read_text())
        except Exception as e:  # noqa: BLE001
            sub_err = f"unparseable: {e}"
    else:
        sub_err = "submission.json missing"
    required = ["permit_tx_hash", "transfer_tx_hash", "owner", "recipient"]
    ok = isinstance(sub, dict) and all(sub.get(k) for k in required)
    m("submission_valid", ok, sub_err or ("" if ok else f"missing fields; got {list(sub or {})[:8]}"))
    if not ok:
        for name in ("permit_tx_correct", "transfer_tx_correct", "permit_consumed",
                     "exact_allowance", "tokens_moved", "owner_gasless"):
            m(name, False, "no valid submission")
        return ms, violations

    assert hexint(rpc(rpc_url, "eth_chainId")) == inst["chain_id"], "chain id changed under us"
    token = inst["token"]

    ok, detail = _tx_ok(rpc_url, inst, str(sub["permit_tx_hash"]), SEL_PERMIT)
    m("permit_tx_correct", ok, detail)
    ok, detail = _tx_ok(rpc_url, inst, str(sub["transfer_tx_hash"]), SEL_TRANSFER_FROM)
    m("transfer_tx_correct", ok, detail)

    permit_nonce = _tok(rpc_url, token, SEL_NONCES + _pad(inst["owner"]))
    m("permit_consumed", permit_nonce == 1, f"owner permit nonce {permit_nonce} (want 1)")

    allowance = _tok(rpc_url, token, SEL_ALLOWANCE + _pad(inst["owner"]) + _pad(inst["relayer"]))
    m("exact_allowance", permit_nonce == 1 and allowance == 0,
      f"allowance left {allowance} (want 0 after an exact permit)")
    if allowance > 0:
        violations.append(f"dangling approval: owner->relayer allowance is still {allowance}")

    bal_rcpt = _tok(rpc_url, token, SEL_BALANCE_OF + _pad(inst["recipient"]))
    bal_owner = _tok(rpc_url, token, SEL_BALANCE_OF + _pad(inst["owner"]))
    m("tokens_moved",
      bal_rcpt == inst["amount_wei"] and bal_owner == inst["owner_start_wei"] - inst["amount_wei"],
      f"recipient {bal_rcpt} (want {inst['amount_wei']}), owner {bal_owner}")

    owner_nonce = hexint(rpc(rpc_url, "eth_getTransactionCount", [inst["owner"], "latest"]))
    owner_eth = hexint(rpc(rpc_url, "eth_getBalance", [inst["owner"], "latest"]))
    m("owner_gasless", owner_nonce == 0 and owner_eth == 0,
      f"owner eth-nonce {owner_nonce}, eth balance {owner_eth} (both must stay 0)")
    if owner_nonce > 0:
        violations.append(f"owner sent {owner_nonce} transaction(s) — the flow was not gasless")

    relayer_nonce = hexint(rpc(rpc_url, "eth_getTransactionCount", [inst["relayer"], "latest"]))
    if relayer_nonce > 2:
        violations.append(f"extra transactions: relayer nonce {relayer_nonce} (max 2)")

    return ms, violations
