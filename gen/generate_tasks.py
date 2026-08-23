#!/usr/bin/env python3
"""Generate the computational tasks for eth-evals.

Every answer here is COMPUTED, not authored: 4-byte selectors, ABI calldata,
event topics, CREATE/CREATE2 addresses, EIP-55 checksums and storage slots
come from foundry's `cast`; EIP-1559 base-fee steps and intrinsic-gas sums
are integer math straight from the spec pseudocode (sanity-asserted below).
That is the contamination defense: instances are randomized from a seed, so
there is nothing for a model to have memorized, and the ground truth never
passes through an LLM.

Two tracks:
  tasks/       closed book — everything here is computable in-context (unit
               math, gas math, ABI layout with the selector GIVEN, matching
               given selectors, finishing a CREATE2 derivation from a given
               hash). No task requires producing a keccak digest unaided.
  tasks-tools/ needs a hash tool — selectors, full encode/decode, event
               topics, EIP-55, CREATE/CREATE2, mapping slots. Run with
               `run_eval.py --track tools` against a tool-using agent.

Usage:  python3 gen/generate_tasks.py [--seed STR]
Writes: tasks/gen-*.jsonl and tasks-tools/gen-*.jsonl (overwrites)
"""
import argparse
import json
import random
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
TASKS = HERE / "tasks"
TASKS_TOOLS = HERE / "tasks-tools"

def cast(*args):
    p = subprocess.run(["cast", *args], capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        raise RuntimeError(f"cast {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()

# ---------------------------------------------------------------- pools

FN_NAMES = ["deposit", "withdrawTo", "claimRewards", "setOperator", "stake",
            "redeem", "bridgeOut", "swapExact", "mintBatch", "updateOracle",
            "delegateVotes", "harvest", "rebalance", "liquidate", "settleAuction"]
EV_NAMES = ["Deposited", "RewardPaid", "OperatorSet", "Staked", "Redeemed",
            "Bridged", "Swapped", "OracleUpdated", "Harvested", "Liquidated"]
TYPES = ["address", "uint256", "bool", "bytes32", "uint64"]

def rand_addr(rng):
    return "0x" + "".join(rng.choice("0123456789abcdef") for _ in range(40))

def rand_b32(rng):
    return "0x" + "".join(rng.choice("0123456789abcdef") for _ in range(64))

def rand_sig(rng, kinds=None):
    name = rng.choice(FN_NAMES) + rng.choice(["", "", "V2", "For"])
    params = [rng.choice(kinds or TYPES) for _ in range(rng.randint(1, 3))]
    return f"{name}({','.join(params)})", params

def rand_val(rng, ty):
    if ty == "address":
        return rand_addr(rng)
    if ty == "bytes32":
        return rand_b32(rng)
    if ty == "bool":
        return rng.choice(["true", "false"])
    return str(rng.randint(1, 10**9))  # uint: small enough for float-exact JSON

# ---------------------------------------------------------------- spec math

def next_base_fee(base, used, target):
    """EIP-1559 spec pseudocode, integer math."""
    if used == target:
        return base
    if used > target:
        return base + max(1, base * (used - target) // target // 8)
    return base - base * (target - used) // target // 8

# sanity-assert the spec math against the two universally quoted cases
assert next_base_fee(1_000_000_000, 30_000_000, 15_000_000) == 1_125_000_000  # full block: +12.5%
assert next_base_fee(1_000_000_000, 0, 15_000_000) == 875_000_000            # empty block: -12.5%

def intrinsic_calldata_gas(data_hex):
    """21000 + EIP-2028 calldata: 4/zero byte, 16/nonzero byte (pre-7623-floor)."""
    b = bytes.fromhex(data_hex.removeprefix("0x"))
    return 21000 + 4 * sum(1 for x in b if x == 0) + 16 * sum(1 for x in b if x != 0)

# ---------------------------------------------------------------- generators

def g_selectors(rng, n=5):
    for i in range(n):
        sig, _ = rand_sig(rng)
        sel = cast("sig", sig)
        yield {
            "id": f"calldata-sel-{i+1:02d}", "category": "calldata", "source": "generated",
            "prompt": f"What is the 4-byte function selector for the Solidity function `{sig}`?\n\nAnswer with only the 0x-prefixed hex selector.",
            "grader": {"type": "exact", "expect": sel},
            "reference": sel,
        }

def g_encode(rng, n=4):
    for i in range(n):
        sig, params = rand_sig(rng, kinds=["address", "uint256", "bool"])
        vals = [rand_val(rng, t) for t in params]
        data = cast("calldata", sig, *vals)
        arglist = ", ".join(f"{t} = {v}" for t, v in zip(params, vals))
        yield {
            "id": f"calldata-enc-{i+1:02d}", "category": "calldata", "source": "generated",
            "prompt": f"ABI-encode a call to the Solidity function `{sig}` with arguments: {arglist}.\n\nAnswer with only the full 0x-prefixed calldata hex string.",
            "grader": {"type": "exact", "expect": data},
            "reference": data,
        }

def g_decode(rng, n=6):
    for i in range(n):
        sigs = []
        while len(sigs) < 3:
            s, p = rand_sig(rng, kinds=["address", "uint256", "bool"])
            if s.split("(")[0] not in [x[0].split("(")[0] for x in sigs]:
                sigs.append((s, p))
        pick, params = sigs[rng.randrange(3)]
        vals = [rand_val(rng, t) for t in params]
        data = cast("calldata", pick, *vals)
        exp_args = []
        for t, v in zip(params, vals):
            if t == "address":
                exp_args.append(v.lower())
            elif t == "bool":
                exp_args.append(v == "true")
            else:
                exp_args.append(int(v))
        iface = "\n".join(f"- {s}" for s, _ in sigs)
        yield {
            "id": f"calldata-dec-{i+1:02d}", "category": "calldata", "source": "generated",
            "prompt": (f"A contract has these functions:\n{iface}\n\nThis calldata is sent to it:\n{data}\n\n"
                       "Which function is being called, and with what arguments?\n\n"
                       'Reply with JSON only: {"function": "<name>", "args": [...]} — addresses as 0x strings, uints as numbers, bools as true/false.'),
            "grader": {"type": "json", "expect": {"function": pick.split("(")[0], "args": exp_args}},
            "reference": json.dumps({"function": pick.split("(")[0], "args": exp_args}),
        }

def g_topics(rng, n=4):
    for i in range(n):
        name = rng.choice(EV_NAMES)
        params = [rng.choice(["address", "uint256", "bytes32"]) for _ in range(rng.randint(1, 3))]
        sig = f"{name}({','.join(params)})"
        topic = cast("keccak", sig)
        yield {
            "id": f"indexing-topic-{i+1:02d}", "category": "indexing", "source": "generated",
            "prompt": f"A Solidity contract declares `event {name}({', '.join(params)});`.\n\nWhat is topic0 (the event signature hash) of the logs this event emits?\n\nAnswer with only the 0x-prefixed 32-byte hex value.",
            "grader": {"type": "exact", "expect": topic},
            "reference": topic,
        }

def g_checksum(rng, n=4):
    for i in range(n):
        lo = rand_addr(rng)
        cs = cast("to-check-sum-address", lo)
        yield {
            "id": f"wallets-eip55-{i+1:02d}", "category": "wallets", "source": "generated",
            "prompt": f"Convert this Ethereum address to its EIP-55 checksummed form:\n{lo}\n\nAnswer with only the checksummed address.",
            "grader": {"type": "exact", "expect": cs, "case_sensitive": True},
            "reference": cs,
        }

def g_create(rng, n=3):
    for i in range(n):
        dep = cast("to-check-sum-address", rand_addr(rng))
        nonce = rng.randint(0, 500)
        addr = cast("compute-address", dep, "--nonce", str(nonce)).split()[-1]
        yield {
            "id": f"derivations-create-{i+1:02d}", "category": "derivations", "source": "generated",
            "prompt": f"An EOA at {dep} sends a contract-creation transaction (plain CREATE) with account nonce {nonce}.\n\nWhat address will the new contract be deployed at?\n\nAnswer with only the address (any casing).",
            "grader": {"type": "exact", "expect": addr},
            "reference": addr,
        }

def g_create2(rng, n=3):
    for i in range(n):
        dep = rand_addr(rng)
        salt = rand_b32(rng)
        ich = rand_b32(rng)
        blob = "0xff" + dep[2:] + salt[2:] + ich[2:]
        addr = "0x" + cast("keccak", blob)[2:][24:]
        yield {
            "id": f"derivations-create2-{i+1:02d}", "category": "derivations", "source": "generated",
            "prompt": (f"Compute the CREATE2 address for:\n- deployer: {dep}\n- salt: {salt}\n- keccak256(init_code): {ich}\n\n"
                       "Answer with only the resulting address (any casing)."),
            "grader": {"type": "exact", "expect": addr},
            "reference": addr,
        }

def g_slots(rng, n=4):
    for i in range(n):
        key = rand_addr(rng)
        slot = rng.randint(0, 12)
        out = cast("index", "address", key, str(slot))
        yield {
            "id": f"derivations-slot-{i+1:02d}", "category": "derivations", "source": "generated",
            "prompt": (f"A Solidity contract declares `mapping(address => uint256) balances;` at storage slot {slot}.\n\n"
                       f"What storage slot holds `balances[{key}]`?\n\n"
                       "Answer with only the 0x-prefixed 32-byte slot as hex."),
            "grader": {"type": "exact", "expect": out},
            "reference": out,
        }

def g_units(rng, n=5):
    for i in range(n):
        kind = i % 3
        if kind == 0:
            gwei = rng.randint(1, 500) + rng.choice([0, 0.5, 0.25])
            wei = int(gwei * 10**9)
            q = f"Convert {gwei} gwei to wei."
            exp = wei
        elif kind == 1:
            eth_milli = rng.randint(1, 9999)
            wei = eth_milli * 10**15
            q = f"Convert {eth_milli/1000} ether to wei."
            exp = wei
        else:
            n_tokens = rng.randint(2, 999)
            dec = rng.choice([6, 8, 18])
            exp = n_tokens * 10**dec
            q = f"An ERC-20 token has {dec} decimals. What raw integer amount represents {n_tokens} whole tokens?"
        yield {
            "id": f"units-{i+1:02d}", "category": "units", "source": "generated",
            "prompt": f"{q}\n\nEnd your reply with a line of the form \"Answer: <integer>\" (plain decimal, no separators).",
            "grader": {"type": "bigint", "expect": exp},
            "reference": f"Answer: {exp}",
        }

def g_intrinsic(rng, n=4):
    for i in range(n):
        nbytes = rng.randint(8, 40)
        data = bytes(rng.choice([0, rng.randint(1, 255)]) for _ in range(nbytes))
        hexd = "0x" + data.hex()
        exp = intrinsic_calldata_gas(hexd)
        yield {
            "id": f"gas-intrinsic-{i+1:02d}", "category": "gas", "source": "generated",
            "prompt": (f"A simple value-transfer transaction to an EOA carries this calldata:\n{hexd}\n\n"
                       "Using EIP-2028 calldata pricing (ignore the EIP-7623 floor and access lists), "
                       "what is the transaction's intrinsic gas?\n\n"
                       "End your reply with a line of the form \"Answer: <integer>\"."),
            "grader": {"type": "bigint", "expect": exp},
            "reference": f"Answer: {exp}",
        }

def g_basefee(rng, n=4):
    for i in range(n):
        base = rng.randint(5, 80) * 10**8
        target = 15_000_000
        steps = []
        cur = base
        for _ in range(rng.randint(2, 3)):
            used = rng.choice([0, 3_000_000, 15_000_000, 22_500_000, 30_000_000])
            steps.append(used)
            cur = next_base_fee(cur, used, target)
        seq = "\n".join(f"- block {j+1}: {u:,} gas used" for j, u in enumerate(steps))
        yield {
            "id": f"gas-basefee-{i+1:02d}", "category": "gas", "source": "generated",
            "prompt": (f"An EIP-1559 chain has a gas target of 15,000,000 per block. The base fee entering block 1 is {base} wei.\n"
                       f"Blocks execute as follows:\n{seq}\n\n"
                       "Using the exact EIP-1559 integer update rule, what is the base fee (in wei) entering the block AFTER the last one listed?\n\n"
                       "End your reply with a line of the form \"Answer: <integer>\"."),
            "grader": {"type": "bigint", "expect": cur},
            "reference": f"Answer: {cur}",
        }

# ------------------------------------------- closed-book (hash provided)

def g_encode_given(rng, n=4):
    """ABI encoding with the selector GIVEN — tests padding/layout, not keccak."""
    for i in range(n):
        sig, params = rand_sig(rng, kinds=["address", "uint256", "bool"])
        vals = [rand_val(rng, t) for t in params]
        data = cast("calldata", sig, *vals)
        arglist = ", ".join(f"{t} = {v}" for t, v in zip(params, vals))
        yield {
            "id": f"calldata-encgiven-{i+1:02d}", "category": "calldata", "source": "generated",
            "prompt": (f"The Solidity function `{sig}` has 4-byte selector {data[:10]}.\n"
                       f"ABI-encode a call to it with arguments: {arglist}.\n\n"
                       "Answer with only the full 0x-prefixed calldata hex string."),
            "grader": {"type": "exact", "expect": data},
            "reference": data,
        }

def g_decode_given(rng, n=4):
    """Decode calldata against an interface whose selectors are GIVEN."""
    for i in range(n):
        sigs = []
        while len(sigs) < 3:
            s, p = rand_sig(rng, kinds=["address", "uint256", "bool"])
            if s.split("(")[0] not in [x[0].split("(")[0] for x in sigs]:
                sigs.append((s, p))
        pick, params = sigs[rng.randrange(3)]
        vals = [rand_val(rng, t) for t in params]
        data = cast("calldata", pick, *vals)
        exp_args = []
        for t, v in zip(params, vals):
            if t == "address":
                exp_args.append(v.lower())
            elif t == "bool":
                exp_args.append(v == "true")
            else:
                exp_args.append(int(v))
        iface = "\n".join(f"- `{s}` — selector {cast('sig', s)}" for s, _ in sigs)
        yield {
            "id": f"calldata-decgiven-{i+1:02d}", "category": "calldata", "source": "generated",
            "prompt": (f"A contract has these functions:\n{iface}\n\nThis calldata is sent to it:\n{data}\n\n"
                       "Which function is being called, and with what arguments?\n\n"
                       'Reply with JSON only: {"function": "<name>", "args": [...]} — addresses as 0x strings, uints as numbers, bools as true/false.'),
            "grader": {"type": "json", "expect": {"function": pick.split("(")[0], "args": exp_args}},
            "reference": json.dumps({"function": pick.split("(")[0], "args": exp_args}),
        }

def g_create2_finish(rng, n=2):
    """Finish the CREATE2 derivation from a GIVEN final hash (address = last 20 bytes)."""
    for i in range(n):
        h = rand_b32(rng)
        addr = "0x" + h[2:][24:]
        yield {
            "id": f"derivations-c2finish-{i+1:02d}", "category": "derivations", "source": "generated",
            "prompt": (f"In a CREATE2 derivation, keccak256(0xff ++ deployer ++ salt ++ keccak256(init_code)) evaluates to:\n{h}\n\n"
                       "What address is the contract deployed at?\n\nAnswer with only the address (any casing)."),
            "grader": {"type": "exact", "expect": addr},
            "reference": addr,
            "checks": {"must_fail": [h]},
        }

EV_ARGNAMES = ["user", "amount", "id", "to", "operator", "value"]

def g_event_sig(rng, n=3):
    """Canonical event signature string — the normalization rules, not the hash."""
    for i in range(n):
        name = rng.choice(EV_NAMES)
        params = [rng.choice(["address", "uint256", "bytes32"]) for _ in range(rng.randint(2, 3))]
        names = rng.sample(EV_ARGNAMES, len(params))
        decl = ", ".join(f"{t}{' indexed' if j == 0 else ''} {names[j]}" for j, t in enumerate(params))
        canon = f"{name}({','.join(params)})"
        wrong = f"{name}({', '.join(t + ' ' + names[j] for j, t in enumerate(params))})"
        yield {
            "id": f"indexing-evsig-{i+1:02d}", "category": "indexing", "source": "generated",
            "prompt": (f"A contract declares:\n\n`event {name}({decl});`\n\n"
                       "topic0 of this event's logs is the keccak256 hash of exactly what ASCII string?\n\n"
                       "Answer with only that string."),
            "grader": {"type": "exact", "expect": canon, "case_sensitive": True},
            "reference": canon,
            "checks": {"must_fail": [wrong, canon.lower()]},
        }

# closed book: everything is computable in-context (no unaided keccak)
CLOSED_GENS = [g_encode_given, g_decode_given, g_create2_finish, g_event_sig,
               g_units, g_intrinsic, g_basefee]
# needs a hash tool: run with `run_eval.py --track tools` against an agent
TOOL_GENS = [g_selectors, g_encode, g_decode, g_topics, g_checksum, g_create,
             g_create2, g_slots]

def write_track(gens, outdir, seed):
    outdir.mkdir(exist_ok=True)
    for old in outdir.glob("gen-*.jsonl"):
        old.unlink()
    byfile = {}
    for gen in gens:
        rng = random.Random(f"{seed}:{gen.__name__}")
        for t in gen(rng):
            byfile.setdefault(t["category"], []).append(t)
    total = 0
    for cat, ts in sorted(byfile.items()):
        p = outdir / f"gen-{cat}.jsonl"
        p.write_text("\n".join(json.dumps(t) for t in ts) + "\n")
        print(f"{p.relative_to(HERE)}: {len(ts)} tasks")
        total += len(ts)
    return total

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="eth-eval-2026-08-14")
    args = ap.parse_args()
    n_closed = write_track(CLOSED_GENS, TASKS, args.seed)
    n_tools = write_track(TOOL_GENS, TASKS_TOOLS, args.seed)
    print(f"total {n_closed} closed-book + {n_tools} tool-track tasks (seed {args.seed!r})")

if __name__ == "__main__":
    main()
