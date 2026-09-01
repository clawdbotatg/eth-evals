"""ctf-challenge: generation + hidden grading.

A faithful port of BuidlGuidl CTF Challenges 1-4 into the agent-in-workspace
harness. The player must register a team (flag 1), then capture three flags
that each need a different EVM skill: a keccak-derived calldata key (2), a
helper contract exposing the right `accessKey` (3), and a payment-callback
contract (4). Two constants — the access-key string and the required wei —
are SEEDED per run, so a memorized end-to-end solution fails while the
technique transfers. Grading reads the flag registry's `hasMinted` on-chain.
"""
import json
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.ethrpc import rpc, hexint  # noqa: E402

HERE = Path(__file__).resolve().parent
CONTRACTS = HERE / "contracts"
ANVIL0 = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"   # unlocked dev deployer/owner
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

SEL_HAS_MINTED = "0xf8f1147d"          # hasMinted(address,uint256)
FLAG_POINTS = {1: 10, 2: 25, 3: 30, 4: 35}

FOUNDRY_TOML = (
    "[profile.default]\n"
    'src = "src"\nout = "out"\nsolc = "0.8.28"\nevm_version = "cancun"\n'
)


def _derive_key(seed, role):
    import hashlib
    h = hashlib.sha256(f"eth-eval-ctf-{seed}-{role}".encode()).digest()
    k = int.from_bytes(h) % (SECP256K1_N - 1) + 1
    return f"0x{k:064x}"


def _addr(privkey):
    out = subprocess.run(["cast", "wallet", "address", "--private-key", privkey],
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(f"cast wallet address failed: {out.stderr[:200]}")
    return out.stdout.strip()


def _pad(v):
    if isinstance(v, str) and v.startswith("0x"):
        v = int(v, 16)
    return f"{v:064x}"


def generate(seed):
    rng = random.Random(f"ctf-{seed}")
    player_key = _derive_key(seed, "player")
    inst = {
        "seed": seed,
        "chain_id": 35_000_000 + rng.randrange(1_000_000),
        "base_fee_wei": 10**9,
        "player_key": player_key,
        "player": _addr(player_key),
        "access_key": "OPEN_" + f"{rng.randrange(16**8):08x}",
        "expected_wei": rng.randrange(1000, 100000) | 1,
        "fund_wei": 5 * 10**18,
    }
    return inst


def _challenges_source(inst):
    src = (CONTRACTS / "Challenges.sol").read_text()
    return (src.replace("__ACCESS_KEY__", inst["access_key"])
               .replace("__EXPECTED_WEI__", str(inst["expected_wei"])))


def _compile(inst):
    """Compile the registry + seeded challenges; return {name: creation hex}."""
    proj = Path(tempfile.mkdtemp(prefix="ctf-compile-"))
    try:
        (proj / "src").mkdir()
        (proj / "foundry.toml").write_text(FOUNDRY_TOML)
        (proj / "src" / "INFTFlags.sol").write_text((CONTRACTS / "INFTFlags.sol").read_text())
        (proj / "src" / "NFTFlags.sol").write_text((CONTRACTS / "NFTFlags.sol").read_text())
        (proj / "src" / "Challenges.sol").write_text(_challenges_source(inst))
        out = subprocess.run(["forge", "build"], cwd=proj, capture_output=True,
                             text=True, timeout=180)
        if out.returncode != 0:
            raise RuntimeError(f"forge build failed: {out.stdout[-400:]}")
        def code(f, c):
            return json.loads((proj / "out" / f / f"{c}.json").read_text())["bytecode"]["object"]
        return {
            "NFTFlags": code("NFTFlags.sol", "NFTFlags"),
            "Challenge1": code("Challenges.sol", "Challenge1"),
            "Challenge2": code("Challenges.sol", "Challenge2"),
            "Challenge3": code("Challenges.sol", "Challenge3"),
            "Challenge4": code("Challenges.sol", "Challenge4"),
        }
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def _deploy(rpc_url, creation_hex):
    txh = rpc(rpc_url, "eth_sendTransaction", [{"from": ANVIL0, "data": creation_hex}])
    receipt = rpc(rpc_url, "eth_getTransactionReceipt", [txh])
    assert hexint(receipt["status"]) == 1, "deploy reverted"
    return receipt["contractAddress"]


def _send(rpc_url, to, data):
    txh = rpc(rpc_url, "eth_sendTransaction", [{"from": ANVIL0, "to": to, "data": data}])
    assert hexint(rpc(rpc_url, "eth_getTransactionReceipt", [txh])["status"]) == 1


def setup_chain(inst, rpc_url):
    codes = _compile(inst)
    reg = _deploy(rpc_url, codes["NFTFlags"] + _pad(ANVIL0))
    inst["registry"] = reg
    chals = {}
    for i in (1, 2, 3, 4):
        addr = _deploy(rpc_url, codes[f"Challenge{i}"] + _pad(reg))
        chals[i] = addr
        _send(rpc_url, reg, "0x488603df" + _pad(addr))       # addAllowedMinter(address)
    _send(rpc_url, reg, "0xa3907d71")                         # enable()
    inst["challenges"] = chals
    rpc(rpc_url, "anvil_setBalance", [inst["player"], hex(inst["fund_wei"])])
    assert hexint(rpc(rpc_url, "eth_chainId")) == inst["chain_id"]


def workspace_files(inst, rpc_url):
    c = inst["challenges"]
    prompt = (HERE / "prompt.md").read_text().format(
        rpc_url=rpc_url, registry=inst["registry"], player=inst["player"],
        c1=c[1], c2=c[2], c3=c[3], c4=c[4],
        access_key=inst["access_key"], expected_wei=inst["expected_wei"])
    params = {
        "rpc_url": rpc_url,
        "registry": inst["registry"],
        "challenge1": c[1], "challenge2": c[2], "challenge3": c[3], "challenge4": c[4],
        "player": inst["player"],
        "access_key": inst["access_key"],
        "expected_wei": inst["expected_wei"],
        "key_file": "wallet.key",
    }
    return {
        "prompt.md": prompt,
        "params.json": json.dumps(params, indent=1),
        "wallet.key": inst["player_key"] + "\n",
        "foundry.toml": FOUNDRY_TOML,
        "src/INFTFlags.sol": (CONTRACTS / "INFTFlags.sol").read_text(),
        "src/NFTFlags.sol": (CONTRACTS / "NFTFlags.sol").read_text(),
        "src/Challenges.sol": _challenges_source(inst),
    }


def _has_flag(rpc_url, inst, flag_id):
    data = SEL_HAS_MINTED + _pad(inst["player"]) + _pad(flag_id)
    res = rpc(rpc_url, "eth_call", [{"to": inst["registry"], "data": data}, "latest"])
    return hexint(res) == 1


def grade(inst, workspace, rpc_url):
    ms = {}
    violations = []
    assert hexint(rpc(rpc_url, "eth_chainId")) == inst["chain_id"], "chain id changed under us"

    names = {1: "flag1_team_registered", 2: "flag2_key_computed",
             3: "flag3_helper_contract", 4: "flag4_payment_callback"}
    for i in (1, 2, 3, 4):
        ok = _has_flag(rpc_url, inst, i)
        ms[names[i]] = {"pass": ok, "detail": "" if ok else f"flag {i} not captured for player"}
    return ms, violations
