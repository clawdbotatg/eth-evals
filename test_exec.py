#!/usr/bin/env python3
"""Execution-harness exit criteria (Phase 1 vertical slice).

Asserts, end to end against real anvil instances:
  - the reference solution scores 100/100 on a normal and a nonzero-nonce seed
  - three intentionally broken solutions fail for DISTINCT reasons
  - upstream policy rejects public RPCs and unknown hosts
  - the agent env is scrubbed of harness credentials

Needs anvil + cast on PATH. No model is invoked; ~15s wall time.
Run: python3 test_exec.py
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from harness import rpc_policy  # noqa: E402
from harness.run_scenario import run_attempt  # noqa: E402

SCN = "tx-eip1559-transfer"
SDIR = HERE / "scenarios" / SCN
FAILS = []


def check(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def failed(res):
    return {k for k, v in res["milestones"].items() if not v["pass"]}


# --- rpc policy (no network) ------------------------------------------------
for bad in ("https://eth.llamarpc.com", "https://mainnet.base.org/",
            "https://my-random-node.example.com/rpc"):
    try:
        rpc_policy.assert_upstream_allowed(bad)
        check(f"policy rejects {bad}", False)
    except ValueError:
        check(f"policy rejects {bad}", True)
rpc_policy.assert_upstream_allowed("http://127.0.0.1:8545")
check("policy allows local anvil", True)
check("redact masks a secret",
      "sk123" not in rpc_policy.redact("url/v2/sk123", extra_secrets=["sk123"]))

# --- reference passes every supported seed ----------------------------------
for seed in (1, 3):  # seed 3 = nonzero starting nonce variant
    r = run_attempt(SCN, seed, f"python3 {SDIR / 'reference.py'}", name="reference")
    check(f"reference seed {seed} scores 100",
          r["score"] == r["max_score"] and not r["safety_violations"],
          json.dumps({k: v["detail"] for k, v in r["milestones"].items() if not v["pass"]}))

# --- broken solutions fail for distinct reasons -------------------------------
u = run_attempt(SCN, 2, f"python3 {SDIR / 'fixtures' / 'broken_unsigned.py'}", name="unsigned")
check("unsigned tx never lands", failed(u) >= {"raw_type2", "receipt_success", "state_correct"}
      and u["score"] <= 10, str(failed(u)))

l = run_attempt(SCN, 2, f"python3 {SDIR / 'fixtures' / 'broken_legacy.py'}", name="legacy")
check("legacy tx fails type checks only",
      failed(l) == {"raw_type2", "fields_correct"}, str(failed(l)))

w = run_attempt(SCN, 2, f"python3 {SDIR / 'fixtures' / 'broken_wrong_value.py'}", name="wrongval")
check("wrong value fails fields+state only",
      failed(w) == {"fields_correct", "state_correct"}, str(failed(w)))

check("three distinct failure signatures",
      len({frozenset(failed(x)) for x in (u, l, w)}) == 3)

# --- erc2612-permit scenario --------------------------------------------------
SCN2 = "erc2612-permit"
SDIR2 = HERE / "scenarios" / SCN2
for seed in (1, 3):
    r = run_attempt(SCN2, seed, f"python3 {SDIR2 / 'reference.py'}", name="reference")
    check(f"permit reference seed {seed} scores 100",
          r["score"] == r["max_score"] and not r["safety_violations"],
          json.dumps({k: v["detail"] for k, v in r["milestones"].items() if not v["pass"]}))

ul = run_attempt(SCN2, 2, f"python3 {SDIR2 / 'fixtures' / 'broken_unlimited.py'}", name="unlimited")
check("unlimited permit fails exact_allowance only + dangling violation",
      failed(ul) == {"exact_allowance"}
      and any("dangling" in v for v in ul["safety_violations"]), str(failed(ul)))

wv = run_attempt(SCN2, 2, f"python3 {SDIR2 / 'fixtures' / 'broken_wrong_value.py'}", name="wrongval")
check("wrong transfer value fails allowance+moved only",
      failed(wv) == {"exact_allowance", "tokens_moved"}, str(failed(wv)))

wc = run_attempt(SCN2, 2, f"python3 {SDIR2 / 'fixtures' / 'broken_wrong_chainid.py'}", name="wrongchain")
check("wrong-chainid domain reverts everything on-chain",
      failed(wc) == {"permit_tx_correct", "transfer_tx_correct", "permit_consumed",
                     "exact_allowance", "tokens_moved"}
      and wc["score"] == 20, str(failed(wc)))

check("permit fixtures: three distinct failure signatures",
      len({frozenset(failed(x)) for x in (ul, wv, wc)}) == 3)

# --- agent env is scrubbed ----------------------------------------------------
import os
os.environ["ALCHEMY_API_KEY"] = "supersecret-test-key"
os.environ["ANTHROPIC_API_KEY"] = "supersecret-test-key2"
leak = run_attempt(SCN, 1, "env > envdump.txt; "
                   "python3 -c \"import json,os;json.dump(dict(os.environ),open('submission.json','w'))\"",
                   name="envprobe")
env_seen = json.dumps(leak["milestones"])  # graded off submission = the env dump
check("scrubbed env reaches the agent", "supersecret" not in env_seen)
check("env-dump agent scores ~0", leak["score"] <= 10)
del os.environ["ALCHEMY_API_KEY"], os.environ["ANTHROPIC_API_KEY"]

n = len(FAILS)
print(f"\ntest_exec: {'ALL GREEN' if not n else str(n) + ' FAILURES: ' + ', '.join(FAILS)}")
sys.exit(1 if n else 0)
