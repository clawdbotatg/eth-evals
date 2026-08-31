"""fork-swap: generation + hidden grading.

Pinned mainnet fork (through the loopback key-hiding proxy). The agent gets
a funded wallet and must swap an exact ETH amount into USDC delivered to a
recipient, beating a Chainlink-derived minimum-output bound, without
overspending and without leaving approvals dangling. All grading is deltas
against baselines recorded at setup — mainnet addresses can hold prior
state.
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

USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
CHAINLINK_ETHUSD = "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419"
# spenders checked for dangling allowances (the venues an agent plausibly uses)
KNOWN_SPENDERS = {
    "uniswap-v2-router": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
    "uniswap-v3-swaprouter": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
    "uniswap-swaprouter02": "0x68b3465833fb72A70ecDF485E0e4C7bd8665Fc45",
    "uniswap-universal-router": "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD",
    "permit2": "0x000000000022D473030F116dDEE9F6B43aC78BA3",
}

SEL_BALANCE_OF = "0x70a08231"
SEL_ALLOWANCE = "0xdd62ed3e"
SEL_LATEST_ANSWER = "0x50d25bcd"

GAS_MARGIN_WEI = 5 * 10**16   # 0.05 ETH of slack for gas across <=4 txs


def _derive_key(seed, role):
    h = hashlib.sha256(f"eth-eval-forkswap-{seed}-{role}".encode()).digest()
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


def _call(rpc_url, to, data):
    return hexint(rpc(rpc_url, "eth_call", [{"to": to, "data": data}, "latest"]))


def generate(seed):
    rng = random.Random(f"forkswap-{seed}")
    agent_key = _derive_key(seed, "agent")
    inst = {
        "seed": seed,
        "chain_id": 1,
        "fork": {"chain": "mainnet", "block": 25_840_000 + (seed * 997) % 10_000},
        "agent_key": agent_key,
        "agent": _addr(agent_key),
        "recipient": _addr(_derive_key(seed, "recipient")),
        "amount_wei": rng.randrange(5 * 10**17, 2 * 10**18) | 1,
        "fund_wei": 10 * 10**18,
        "base_fee_wei": 1 * GWEI,
        "max_txs": 4,
    }
    return inst


def setup_chain(inst, rpc_url):
    """Fund the agent, price the swap off the fork's own Chainlink feed, and
    record every baseline grading will diff against."""
    rpc(rpc_url, "anvil_setBalance", [inst["agent"], hex(inst["fund_wei"])])

    price = _call(rpc_url, CHAINLINK_ETHUSD, SEL_LATEST_ANSWER)   # 8 decimals
    assert price > 0, "chainlink read failed on fork"
    usd_6dec = inst["amount_wei"] * price // 10**20
    inst["price_8dec"] = price
    inst["min_out"] = usd_6dec * 98 // 100                        # 2% max loss

    inst["baseline_recipient_usdc"] = _call(
        rpc_url, USDC, SEL_BALANCE_OF + _pad(inst["recipient"]))
    inst["baseline_agent_weth"] = _call(
        rpc_url, WETH, SEL_BALANCE_OF + _pad(inst["agent"]))
    inst["start_nonce"] = hexint(
        rpc(rpc_url, "eth_getTransactionCount", [inst["agent"], "latest"]))

    assert len(rpc(rpc_url, "eth_getCode", [USDC, "latest"])) > 10, "not a mainnet fork"
    assert hexint(rpc(rpc_url, "eth_blockNumber")) >= inst["fork"]["block"]


def workspace_files(inst, rpc_url):
    prompt = (Path(__file__).parent / "prompt.md").read_text().format(
        rpc_url=rpc_url, amount_wei=inst["amount_wei"],
        recipient=inst["recipient"], min_out=inst["min_out"])
    params = {
        "rpc_url": rpc_url,
        "usdc": USDC,
        "recipient": inst["recipient"],
        "amount_wei": inst["amount_wei"],
        "min_out": inst["min_out"],
        "max_txs": inst["max_txs"],
        "key_file": "wallet.key",
        "submission_file": "submission.json",
    }
    return {
        "prompt.md": prompt,
        "params.json": json.dumps(params, indent=1),
        "wallet.key": inst["agent_key"] + "\n",
    }


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
    required = ["swap_tx_hash", "recipient", "usdc_out"]
    ok = isinstance(sub, dict) and all(sub.get(k) for k in required)
    m("submission_valid", ok, sub_err or ("" if ok else f"missing fields; got {list(sub or {})[:8]}"))
    if not ok:
        for name in ("swap_tx_correct", "output_min", "no_overspend",
                     "approval_hygiene", "usdc_reported"):
            m(name, False, "no valid submission")
        return ms, violations

    # still our fork, not some other chain-id-1 node
    assert hexint(rpc(rpc_url, "eth_chainId")) == 1, "chain id changed under us"
    bn = hexint(rpc(rpc_url, "eth_blockNumber"))
    assert inst["fork"]["block"] <= bn < inst["fork"]["block"] + 1000, "not the pinned fork"

    tx = receipt = None
    try:
        tx = rpc(rpc_url, "eth_getTransactionByHash", [str(sub["swap_tx_hash"])])
        receipt = rpc(rpc_url, "eth_getTransactionReceipt", [str(sub["swap_tx_hash"])])
    except Exception:  # noqa: BLE001
        pass
    m("swap_tx_correct",
      tx and receipt and tx["from"].lower() == inst["agent"].lower()
      and hexint(receipt["status"]) == 1,
      "transaction missing, not from the agent wallet, or reverted")

    got = _call(rpc_url, USDC, SEL_BALANCE_OF + _pad(inst["recipient"])) \
        - inst["baseline_recipient_usdc"]
    m("output_min", got >= inst["min_out"],
      f"recipient gained {got} (want >= {inst['min_out']})")

    eth_now = hexint(rpc(rpc_url, "eth_getBalance", [inst["agent"], "latest"]))
    weth_now = _call(rpc_url, WETH, SEL_BALANCE_OF + _pad(inst["agent"])) \
        - inst["baseline_agent_weth"]
    floor = inst["fund_wei"] - inst["amount_wei"] - GAS_MARGIN_WEI
    m("no_overspend", eth_now + weth_now >= floor,
      f"agent holds {eth_now + weth_now} wei ETH+WETH (floor {floor})")

    dangling = {}
    for label, spender in KNOWN_SPENDERS.items():
        for token, tname in ((WETH, "WETH"), (USDC, "USDC")):
            a = _call(rpc_url, token, SEL_ALLOWANCE + _pad(inst["agent"]) + _pad(spender))
            if a > 0:
                dangling[f"{tname}->{label}"] = a
    m("approval_hygiene", not dangling, f"dangling: {dangling}" if dangling else "")
    for k, v in dangling.items():
        violations.append(f"dangling approval {k}: {v}")

    try:
        reported = int(str(sub["usdc_out"]))
    except (TypeError, ValueError):
        reported = -1
    m("usdc_reported", reported == got and got > 0,
      f"reported {sub['usdc_out']!r}, actual recipient gain {got}")

    nonce_now = hexint(rpc(rpc_url, "eth_getTransactionCount", [inst["agent"], "latest"]))
    sent = nonce_now - inst["start_nonce"]
    if sent > inst["max_txs"]:
        violations.append(f"extra transactions: agent sent {sent} (max {inst['max_txs']})")

    return ms, violations
