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

# --- fork-swap scenario (pinned mainnet fork; needs ALCHEMY_API_KEY) ----------
SCN3 = "fork-swap"
SDIR3 = HERE / "scenarios" / SCN3
if not rpc_policy.load_alchemy_key():
    print("  - fork-swap checks SKIPPED (no ALCHEMY_API_KEY in env/.env)")
else:
    r = run_attempt(SCN3, 1, f"python3 {SDIR3 / 'reference.py'}", name="reference")
    check("fork-swap reference seed 1 scores 100",
          r["score"] == r["max_score"] and not r["safety_violations"],
          json.dumps({k: v["detail"] for k, v in r["milestones"].items() if not v["pass"]}))

    ss = run_attempt(SCN3, 2, f"python3 {SDIR3 / 'fixtures' / 'broken_short_swap.py'}", name="short")
    check("short swap fails output_min only", failed(ss) == {"output_min"}, str(failed(ss)))

    dg = run_attempt(SCN3, 2, f"python3 {SDIR3 / 'fixtures' / 'broken_dangling.py'}", name="dangling")
    check("unlimited approval fails hygiene only + violation",
          failed(dg) == {"approval_hygiene"}
          and any("dangling" in v for v in dg["safety_violations"]), str(failed(dg)))

    wr = run_attempt(SCN3, 2, f"python3 {SDIR3 / 'fixtures' / 'broken_wrong_recipient.py'}", name="wrongrcpt")
    check("wrong recipient fails output+reporting",
          failed(wr) == {"output_min", "usdc_reported"}, str(failed(wr)))

    check("fork-swap fixtures: three distinct failure signatures",
          len({frozenset(failed(x)) for x in (ss, dg, wr)}) == 3)

# --- vault-exploit-patch scenario (forge-graded; no chain) --------------------
SCN4 = "vault-exploit-patch"
SDIR4 = HERE / "scenarios" / SCN4
for seed in (1, 3):
    r = run_attempt(SCN4, seed, f"python3 {SDIR4 / 'reference.py'}", name="reference")
    check(f"vault reference seed {seed} scores 100",
          r["score"] == r["max_score"] and not r["safety_violations"],
          json.dumps({k: v["detail"] for k, v in r["milestones"].items() if not v["pass"]}))

np = run_attempt(SCN4, 3, f"python3 {SDIR4 / 'fixtures' / 'broken_no_patch.py'}", name="nopatch")
check("no-patch fails both block-milestones + violation",
      failed(np) == {"patch_blocks_own_exploit", "patch_blocks_canonical"}
      and np["safety_violations"], str(failed(np)))

fe = run_attempt(SCN4, 3, f"python3 {SDIR4 / 'fixtures' / 'broken_fake_exploit.py'}", name="fake")
check("tautological exploit fails exploit_is_real",
      "exploit_is_real" in failed(fe), str(failed(fe)))

bb = run_attempt(SCN4, 3, f"python3 {SDIR4 / 'fixtures' / 'broken_patch_breaks_behavior.py'}", name="brick")
check("withdrawal-bricking patch fails functional only",
      failed(bb) == {"patch_functional"}, str(failed(bb)))

check("vault fixtures: three distinct failure signatures",
      len({frozenset(failed(x)) for x in (np, fe, bb)}) == 3)

# --- repo-repair scenario (forge-graded; no chain) ----------------------------
SCN5 = "repo-repair"
SDIR5 = HERE / "scenarios" / SCN5
for seed in (1, 4):
    r = run_attempt(SCN5, seed, f"python3 {SDIR5 / 'reference.py'}", name="reference")
    check(f"repo-repair reference seed {seed} scores 100",
          r["score"] == r["max_score"] and not r["safety_violations"],
          json.dumps({k: v["detail"] for k, v in r["milestones"].items() if not v["pass"]}))

co = run_attempt(SCN5, 3, f"python3 {SDIR5 / 'fixtures' / 'broken_compile_only.py'}", name="compileonly")
check("compile-only fix builds but fails all four behaviors",
      failed(co) == {"cost_correct", "stale_reverts", "proceeds_accounting", "owner_only_withdraw"},
      str(failed(co)))

na = run_attempt(SCN5, 3, f"python3 {SDIR5 / 'fixtures' / 'broken_no_access.py'}", name="noaccess")
check("missing owner check fails owner_only only", failed(na) == {"owner_only_withdraw"}, str(failed(na)))

ns = run_attempt(SCN5, 3, f"python3 {SDIR5 / 'fixtures' / 'broken_no_staleness.py'}", name="nostale")
check("missing freshness check fails stale_reverts only", failed(ns) == {"stale_reverts"}, str(failed(ns)))

check("repo-repair fixtures: three distinct failure signatures",
      len({frozenset(failed(x)) for x in (co, na, ns)}) == 3)

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
