#!/usr/bin/env python3
"""eth-evals live/agentic track: can an AGENT do real Ethereum work?

Unlike run_eval.py (vanilla model, closed book), this track runs a tool-using
agent CLI (claude -p, codex, ...) against tasks whose answers live on mainnet
RIGHT NOW. Grading is execution-based with zero LLM judge: for every task the
harness computes the ground truth itself — via `cast` against the same RPC, at
grade time — and compares within a declared tolerance (prices drift, block
numbers advance; exact facts stay exact).

Requires: foundry's `cast` on PATH, RPC_URL env var (an authenticated
endpoint, e.g. Alchemy — set it in .env, never commit it).

Examples:
  RPC_URL=... python3 run_live_eval.py --self-test          # truth cmds resolve
  RPC_URL=... python3 run_live_eval.py --name claude-haiku \
      --cmd 'claude -p --model haiku'
"""
import argparse
import concurrent.futures
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from run_eval import CmdTarget, ans_line, extract_bigints, harness_commit, norm

HERE = Path(__file__).resolve().parent
TASKS_DIR = HERE / "tasks-live"
RESULTS_DIR = HERE / "results-live"

PROMPT_PREFIX = (
    "You are an agent with shell access. Foundry's `cast` is installed and the "
    "environment variable RPC_URL holds an Ethereum mainnet RPC endpoint. Use "
    "any tools you need to answer with live data.\n\n"
)
PROMPT_SUFFIX = "\n\nEnd your reply with a line of the form \"Answer: <value>\"."

# --- closed-book (calibration) mode -------------------------------------
# The agent track asks "can it look this up". This one asks the opposite:
# what does the model BELIEVE, with no tools? Ethereum's world-state moved
# hard (mainnet gas is now sub-gwei) and training data did not, so a model
# will answer confidently and be wrong by an order of magnitude. Same live
# ground truth, no tools, no prefix telling it to go and check.
CLOSED_PREFIX = (
    "Answer from your own knowledge. You have no tools and no network access. "
    "Give your best single estimate anyway - do not refuse, and do not answer "
    "with a range.\n\n"
)
NOTOOLS_FLAGS = (
    "--strict-mcp-config --mcp-config '{\"mcpServers\":{}}' "
    "--disallowedTools Bash Read Write Edit Glob Grep Task Workflow Agent "
    "WebSearch WebFetch NotebookEdit"
)


def load_env_file():
    p = HERE / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def truth_value(task):
    """Compute ground truth NOW via the task's shell command."""
    out = subprocess.run(task["truth"]["cmd"], shell=True, capture_output=True,
                        text=True, timeout=60, env=os.environ)
    if out.returncode != 0:
        raise RuntimeError(f"truth cmd failed: {out.stderr.strip()[:150]}")
    return out.stdout.strip().splitlines()[-1].strip()


_FLOAT_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")

def _floats(text):
    """Every number in `text` as a float, commas and $ stripped."""
    out = []
    for m in _FLOAT_RE.finditer((text or "").replace("$", "")):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return out


def grade_live(task, resp, truth):
    t = task["truth"]["type"]
    a = ans_line(resp)
    if t == "exact":
        # addresses are case-insensitive (EIP-55 checksums differ by case) and
        # may arrive inside a sentence, so match anywhere in the answer line
        if truth.startswith("0x") and len(truth) == 42:
            hay = (a + " " + resp).lower()
            ok = truth.lower() in hay
            got = re.search(r"0x[0-9a-fA-F]{40}", a) or re.search(r"0x[0-9a-fA-F]{40}", resp)
            return ok, f"truth {truth} got {got.group(0) if got else 'no address'}"
        ok = norm(truth) in (norm(a), norm(resp.strip().splitlines()[-1] if resp.strip() else ""))
        return ok, f"truth {truth!r} got {a[:60]!r}"
    exp_nums = extract_bigints(truth)
    got_nums = extract_bigints(a) or extract_bigints(resp)
    if not exp_nums:
        return False, f"truth not numeric: {truth[:60]!r}"
    if not got_nums:
        return False, f"no number in answer {a[:60]!r}"
    exp, got = exp_nums[0], got_nums[0]
    if t == "abs":
        ok = abs(got - exp) <= task["truth"]["tol"]
    elif t == "ratio":
        # integers-only extraction turns "$0.0317" into 0 and 317 - parse floats
        exp_f = _floats(truth)
        got_f = _floats(a) or _floats(resp)
        if not exp_f or not got_f:
            return False, f"truth {truth[:40]!r} got {a[:50]!r}"
        exp, got = exp_f[0], got_f[0]
        # calibration answers are estimates, so grade on ORDER OF MAGNITUDE:
        # pass if within a factor of tol either way. Generous on purpose - a
        # model that still fails this is not imprecise, it is out of date.
        if exp == 0 or got <= 0:
            return False, f"truth {exp} got {got}"
        f = max(got / exp, exp / got)
        return f <= task["truth"]["tol"], f"truth {exp} got {got} ({f:.1f}x off)"
    else:  # rel
        ok = exp != 0 and abs(got - exp) / abs(exp) <= task["truth"]["tol"]
    return ok, f"truth {exp} got {got}"


def live_manifest_hash(tasks, mode):
    """sha256 over the tasks a run actually sees in this mode plus the grading
    code and prompt framing. Same rule as the closed-book track: runs whose
    manifests differ ran different tests and must never be compared. Live
    truth is computed at grade time, so the truth VALUES are not in the hash -
    only the commands that produce them."""
    seen = [t for t in tasks if mode != "closed" or t.get("closed_book", True)]
    src = "".join(inspect.getsource(f) for f in (
        grade_live, _floats, truth_value, run_one, ans_line, extract_bigints, norm))
    blob = (json.dumps(seen, sort_keys=True, separators=(",", ":")) + src
            + mode + PROMPT_PREFIX + CLOSED_PREFIX + PROMPT_SUFFIX)
    return hashlib.sha256(blob.encode()).hexdigest()


def report():
    """Group saved live runs by (mode, manifest). Only runs inside one group
    are comparable; anything on a stale manifest is listed as legacy."""
    tasks = load_tasks()
    current = {m: live_manifest_hash(tasks, m) for m in ("agent", "closed")}
    groups = {}
    for f in sorted(RESULTS_DIR.glob("*.json")):
        r = json.loads(f.read_text())
        key = (r.get("mode", "?"), r.get("manifest", "none"))
        groups.setdefault(key, []).append(r)
    for (mode, man), rs in sorted(groups.items()):
        cur = current.get(mode) == man
        tag = "CURRENT" if cur else "LEGACY (not comparable)"
        print(f"\n{mode} mode, manifest {man[:10]} - {tag}")
        for r in sorted(rs, key=lambda r: -r["passed"] / max(r["total"], 1)):
            print(f"  {r['name']:<18}{r['passed']:>4}/{r['total']:<4}"
                  f"{r['passed']/max(r['total'],1):>6.0%}   {r['timestamp']}")


def load_tasks():
    tasks = []
    for f in sorted(TASKS_DIR.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                tasks.append(json.loads(line))
    return tasks


def run_one(target, task, mode="agent"):
    t0 = time.time()
    if mode == "closed" and not task.get("closed_book", True):
        return None                      # task only makes sense for an agent
    prefix = CLOSED_PREFIX if mode == "closed" else PROMPT_PREFIX
    prompt = prefix + task["prompt"] + PROMPT_SUFFIX
    try:
        resp, _ = target.ask(prompt, 0)
        truth = truth_value(task)  # computed right after the agent answers
        ok, detail = grade_live(task, resp, truth)
        err = None
    except Exception as e:  # noqa: BLE001
        resp, ok, detail, err = "", False, f"ERROR: {str(e)[:150]}", True
    return {"id": task["id"], "category": task["category"], "pass": bool(ok),
            "detail": detail, "response": (resp or "")[:2000],
            "latency_s": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name")
    ap.add_argument("--cmd", help="agent CLI; prompt on stdin, answer on stdout")
    ap.add_argument("--self-test", action="store_true", help="run every truth cmd, print values")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--report", action="store_true",
                    help="group saved runs by manifest; only same-manifest runs compare")
    ap.add_argument("--mode", choices=["agent", "closed"], default="agent",
                    help="agent = tools + told to look it up; "
                         "closed = no tools, graded on what the model believes")
    args = ap.parse_args()

    if args.report:
        report()
        return
    load_env_file()
    if not os.environ.get("RPC_URL"):
        sys.exit("RPC_URL not set (put it in .env — an Alchemy URL, never a public RPC)")

    tasks = load_tasks()
    if args.self_test:
        bad = 0
        for t in tasks:
            try:
                v = truth_value(t)
                print(f"  ✓ {t['id']}: {v[:70]}")
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {t['id']}: {e}")
                bad += 1
        print(f"self-test: {len(tasks)-bad}/{len(tasks)} truth commands green")
        sys.exit(1 if bad else 0)

    if not (args.cmd and args.name):
        sys.exit("need --name and --cmd (or --self-test)")
    cmd = args.cmd
    if args.mode == "closed" and "--disallowedTools" not in cmd:
        cmd = cmd + " " + NOTOOLS_FLAGS
    target = CmdTarget(cmd)
    if args.mode == "agent":
        target.env["RPC_URL"] = os.environ["RPC_URL"]
    else:
        target.env.pop("RPC_URL", None)   # nothing to reach for

    print(f"running {len(tasks)} live tasks ({args.mode} mode) against {target.desc}")
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for r in ex.map(lambda t: run_one(target, t, args.mode), tasks):
            if r is None:
                continue                 # agent-only task skipped in closed mode
            rows.append(r)
            print(f"  {'✓' if r['pass'] else '✗'} {r['id']} ({r['latency_s']}s) {r['detail'][:100]}")

    passed = sum(r["pass"] for r in rows)
    print(f"\n{passed}/{len(rows)} live tasks passed")
    errs = [r['id'] for r in rows if r['detail'].startswith('ERROR')]
    if errs:
        # an outage is not a score - same rule as the other tracks
        sys.exit(f"refusing to save - never reached the target on: {', '.join(errs)}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = {"name": args.name, "target": target.desc, "mode": args.mode,
           "manifest": live_manifest_hash(tasks, args.mode),
           "harness_commit": harness_commit(),
           "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
           "passed": passed, "total": len(rows), "tasks": rows}
    (RESULTS_DIR / f"{args.name}.json").write_text(json.dumps(out, indent=1))
    print(f"saved results-live/{args.name}.json")


if __name__ == "__main__":
    main()
