#!/usr/bin/env python3
"""eth-evals: how much Ethereum does an LLM actually know?

An evaluation suite that interrogates a vanilla LLM (no docs, no tools, no
retrieval) on the working knowledge an Ethereum builder needs — the same
knowledge ethskills.com packages for agents. Scores tell you (a) which model
knows Ethereum best and (b) which ethskills content is already inside the
models and could be trimmed.

Targets:
  --base-url URL --model NAME [--api-key-env VAR] [--auth bearer|xapikey]
      any OpenAI-compatible endpoint (bankr gateway, openrouter, ollama, ...)
  --cmd 'claude -p --model haiku'
      any CLI harness; prompt goes to stdin, response read from stdout.
      CLAUDECODE / CLAUDE_CODE_* / ANTHROPIC_API_KEY are scrubbed from the
      child env (nested-claude embedded-mode trap).
  --self-test
      grade every task's bundled reference answer (zero tokens; must be 100%).

Examples:
  python3 run_eval.py --self-test
  python3 run_eval.py --name qwen3-coder --base-url https://llm.bankr.bot/v1 \
      --model qwen3-coder --api-key-env BANKR_API_KEY --auth xapikey
  python3 run_eval.py --name haiku --cmd 'claude -p --model haiku' --concurrency 4
"""
import argparse
import concurrent.futures
import hashlib
import inspect
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS_DIR = HERE / "tasks"
RESULTS_DIR = HERE / "results"

# --track tools: tasks whose answers require computing a keccak hash — fair
# for a tool-using agent (cast on PATH), impossible closed-book.
TOOLS_TASKS_DIR = HERE / "tasks-tools"
TOOLS_RESULTS_DIR = HERE / "results-tools"
TOOL_PREFIX = ("You are an agent with shell access. Foundry's `cast` is installed. "
               "Use any tools you need.\n\n")

# ---------------------------------------------------------------- helpers

def norm(t, casefold=True):
    """Normalize a short answer: collapse whitespace, strip fences/quotes/trailing dot."""
    t = (t or "").strip()
    t = t.strip("`").strip()
    t = re.sub(r"\s+", " ", t)
    t = t.strip().rstrip(".").strip()
    t = t.strip("\"'").strip()
    return t.casefold() if casefold else t

def lines(r):
    return [l.strip() for l in (r or "").strip().splitlines() if l.strip()]

def ans_line(r):
    """Content after the last 'Answer:' marker, else the last non-empty line."""
    found = None
    for l in (r or "").strip().splitlines():
        m = re.match(r"\s*[*#>\s]*answer\s*[:=]\s*(.+?)\s*$", l, re.I)
        if m:
            found = m.group(1)
    if found is None:
        m = re.search(r"answer\s*[:=]\s*(.+?)\s*$", r or "", re.I | re.M)
        if m:
            found = m.group(1)
    if found is not None:
        return found.strip().strip("*").strip()
    ls = lines(r)
    return ls[-1] if ls else ""

def extract_num(r):
    a = ans_line(r)
    for scope in (a, r or ""):
        nums = re.findall(r"-?\$?\d[\d,]*\.?\d*(?:e[+-]?\d+)?", scope, re.I)
        if nums:
            pick = nums[0] if scope is a else nums[-1]
            return float(pick.replace("$", "").replace(",", ""))
    return None

# minus sign only counts when it isn't glued to a word (EIP-4844 must parse as
# 4844, not -4844)
_INT_RE = re.compile(r"(?:0x[0-9a-fA-F][0-9a-fA-F_]*|(?<![\w-])-\d[\d_,]*|\d[\d_,]*)")

def extract_bigints(r):
    """All integers (decimal with separators, or 0x hex) in a string, as ints."""
    out = []
    for m in _INT_RE.finditer(r or ""):
        s = m.group(0).replace("_", "").replace(",", "")
        try:
            out.append(int(s, 16) if s.lower().startswith("0x") else int(s))
        except ValueError:
            pass
    return out

def jload(r):
    r = (r or "").strip()
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", r, re.S)
    for c in ([fenced[-1]] if fenced else []) + [r]:
        c = c.strip()
        try:
            return json.loads(c)
        except Exception:
            pass
        for op, cl in (("{", "}"), ("[", "]")):
            i, j = c.find(op), c.rfind(cl)
            if 0 <= i < j:
                try:
                    return json.loads(c[i : j + 1])
                except Exception:
                    pass
    raise ValueError("no JSON found in response")

def jmatch(exp, got):
    """expected-vs-got JSON: numbers ~equal, '~str' = substring, dicts allow extra keys."""
    if isinstance(exp, bool):
        return isinstance(got, bool) and exp == got
    if isinstance(exp, (int, float)):
        if isinstance(got, str):
            try:
                got = int(got, 16) if got.lower().startswith("0x") else float(got)
            except ValueError:
                return False
        return isinstance(got, (int, float)) and not isinstance(got, bool) and abs(exp - got) < 1e-6
    if isinstance(exp, str):
        if not isinstance(got, str):
            return False
        if exp.startswith("~"):
            return exp[1:].casefold() in got.casefold()
        return norm(exp) == norm(got)
    if isinstance(exp, list):
        return isinstance(got, list) and len(exp) == len(got) and all(jmatch(e, g) for e, g in zip(exp, got))
    if isinstance(exp, dict):
        return isinstance(got, dict) and all(k in got and jmatch(v, got[k]) for k, v in exp.items())
    if exp is None:
        return got is None
    return exp == got

# ---------------------------------------------------------------- graders

# A grader match means the expected token APPEARED — not that the answer
# asserted it. "Answer: not 12" contains 12; "Answer: not Chainlink" contains
# Chainlink. Any pass whose answer line is negated is flipped to a fail,
# unless the task's own reference is negated (honesty tasks answer "cannot").
_NEG_RE = re.compile(
    r"(?i)(?<![\w-])(not|isn'?t|aren'?t|doesn'?t|don'?t|won'?t|wasn'?t|weren'?t|"
    r"never|cannot|can'?t|neither|nor|rather than|instead of|no longer|wrong|incorrect)"
    r"(?![\w-])|!=|≠")

def _grade_one(g, resp):
    t = g["type"]
    if t == "numeric":
        v = extract_num(resp)
        ok = v is not None and abs(v - g["expect"]) <= g.get("tol", 1e-6)
        return ok, f"got {v}"
    if t == "bigint":
        # exact integer compare; expect may be int or "0x..." string.
        exp = g["expect"]
        if isinstance(exp, str):
            exp = int(exp, 16) if exp.lower().startswith("0x") else int(exp)
        # the Answer line's FIRST integer is the answer — "13, though 12 is
        # expected" must fail. Without an Answer line, take the response's
        # last integer (models conclude with the result).
        a_ints = extract_bigints(ans_line(resp))
        if a_ints:
            # an integer answer must commit to ONE value: "12 or 13",
            # "12-13", "12 (i.e. 12000 ms)" are hedges, not answers.
            if len(set(a_ints)) > 1:
                return False, f"ambiguous: multiple integers {sorted(set(a_ints))[:4]}"
            ok, got = a_ints[0] == exp, a_ints[0]
        else:
            r_ints = extract_bigints(resp)
            ok, got = bool(r_ints) and r_ints[-1] == exp, (r_ints[-1] if r_ints else None)
        return ok, f"got {got}"
    if t == "exact":
        cf = not g.get("case_sensitive", False)
        cands = [norm(resp, cf)]
        ls = lines(resp)
        if ls:
            cands.append(norm(ls[-1], cf))
        cands.append(norm(ans_line(resp), cf))
        exp = norm(g["expect"], cf)
        return exp in cands, f"got {cands[-1][:80]!r}"
    if t == "regex":
        scope = ans_line(resp) if g.get("on", "answer") == "answer" else resp
        flags = 0 if g.get("case_sensitive") else re.I
        return bool(re.search(g["pattern"], scope, flags)), f"answer {scope[:80]!r}"
    if t == "regex_all":
        scope = ans_line(resp) if g.get("on", "answer") == "answer" else resp
        flags = 0 if g.get("case_sensitive") else re.I
        misses = [p for p in g["patterns"] if not re.search(p, scope, flags)]
        return not misses, f"missing {misses[:3]}" if misses else ""
    if t == "json":
        got = jload(resp)
        ok = jmatch(g["expect"], got)
        return ok, "" if ok else f"got {json.dumps(got)[:120]}"
    if t == "any_of":
        details = []
        for sub in g["options"]:
            ok, d = _grade_one(sub, resp)
            if ok:
                return True, ""
            details.append(d)
        return False, ("; ".join(details))[:140]
    raise ValueError(f"unknown grader type {t}")

def grade(task, resp):
    try:
        ok, detail = _grade_one(task["grader"], resp)
        if ok and _NEG_RE.search(ans_line(resp)) and not _NEG_RE.search(task.get("reference", "")):
            return False, f"negated answer line: {ans_line(resp)[:80]!r}"
        return ok, detail
    except Exception as e:  # noqa: BLE001 — a grading crash is a task failure
        return False, f"{type(e).__name__}: {e}"[:140]

# ---------------------------------------------------------------- targets

SCRUB = re.compile(r"^(CLAUDECODE$|CLAUDE_CODE_|ANTHROPIC_API_KEY$|CLAUDE_AGENT_)")

class OpenAITarget:
    def __init__(self, base_url, model, api_key, auth):
        u = base_url.rstrip("/")
        self.url = u if u.endswith("/chat/completions") else u + "/chat/completions"
        self.model = model
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            if auth == "xapikey":
                self.headers["X-API-Key"] = api_key
            else:
                self.headers["Authorization"] = f"Bearer {api_key}"
        self.desc = f"openai:{self.url}:{model}"

    def ask(self, prompt, max_tokens):
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": max_tokens,
        }).encode()
        last = None
        backoffs = [5, 10, 20, 40, 60]
        for attempt in range(len(backoffs) + 1):
            req = urllib.request.Request(self.url, data=body, headers=self.headers)
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    data = json.load(resp)
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                usage = data.get("usage") or {}
                if not content.strip():
                    # reasoning models can burn the whole budget thinking and
                    # return empty content — retry rather than score a blank
                    last = "empty content"
                    if attempt < len(backoffs):
                        time.sleep(backoffs[attempt])
                        continue
                    raise RuntimeError(last)
                return content, usage
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read()[:200]!r}"
                if e.code in (408, 429, 500, 502, 503, 504) and attempt < len(backoffs):
                    time.sleep(backoffs[attempt])
                    continue
                raise RuntimeError(last) from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = str(e)
                if attempt < len(backoffs):
                    time.sleep(backoffs[attempt])
                    continue
                raise RuntimeError(last) from None
        raise RuntimeError(last or "exhausted retries")

class CmdTarget:
    def __init__(self, cmd, timeout=900, cwd=None):
        self.cmd = cmd
        self.desc = f"cmd:{cmd}"
        self.timeout = timeout
        # An agent CLI runs with tools. If its cwd is this repo it can read the
        # graders and the answer keys, so the exec track passes a scratch dir.
        self.cwd = str(cwd) if cwd else str(HERE)
        self.env = {k: v for k, v in os.environ.items() if not SCRUB.match(k)}

    def ask(self, prompt, max_tokens):
        p = subprocess.run(
            self.cmd, shell=True, input=prompt, capture_output=True, text=True,
            timeout=self.timeout, env=self.env, cwd=self.cwd,
        )
        if p.returncode != 0:
            raise RuntimeError(f"cmd exit {p.returncode}: {(p.stderr or p.stdout)[:300]}")
        return p.stdout.strip(), {}

# ---------------------------------------------------------------- manifest

BENCH_VERSION = "1.1.0"  # closed-book track, hardened graders

def manifest_hash(tasks):
    """sha256 over every scored input: the full task corpus (prompts, graders,
    fixtures) plus the grading code itself. Results from different manifests
    are not comparable and the reporter refuses to rank them together."""
    graders_src = "".join(inspect.getsource(f) for f in (
        norm, lines, ans_line, extract_num, extract_bigints, jload, jmatch,
        _grade_one, grade)) + _NEG_RE.pattern
    blob = json.dumps(tasks, sort_keys=True, separators=(",", ":")) + graders_src
    return hashlib.sha256(blob.encode()).hexdigest()

def harness_commit():
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                             capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=HERE,
                               capture_output=True, text=True, timeout=10).stdout.strip()
        return sha + ("-dirty" if dirty else "") if sha else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"

# ---------------------------------------------------------------- run

def load_tasks(category=None, limit=None, tasks_dir=TASKS_DIR):
    tasks, seen = [], set()
    for f in sorted(tasks_dir.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            if t["id"] in seen:
                sys.exit(f"duplicate task id {t['id']} in {f.name}")
            seen.add(t["id"])
            tasks.append(t)
    if category:
        tasks = [t for t in tasks if t["category"] == category]
    if limit:
        tasks = tasks[:limit]
    return tasks

def bootstrap_ci(rows, n=2000):
    bycat = {}
    for r in rows:
        bycat.setdefault(r["category"], []).append(1.0 if r["pass"] else 0.0)
    rng = random.Random(42)
    means = []
    for _ in range(n):
        cms = []
        for vals in bycat.values():
            cms.append(sum(vals[rng.randrange(len(vals))] for _ in vals) / len(vals))
        means.append(100 * sum(cms) / len(cms))
    means.sort()
    return means[int(0.025 * n)], means[int(0.975 * n)]

def run_one(target, task, max_tokens):
    t0 = time.time()
    try:
        resp, usage = target.ask(task["prompt"], max_tokens)
        err = None
    except Exception as e:  # noqa: BLE001
        resp, usage, err = "", {}, str(e)[:200]
    dt = time.time() - t0
    base = {"id": task["id"], "category": task["category"],
            "source": task.get("source", ""), "latency_s": round(dt, 1), "usage": usage}
    if err:
        return {**base, "pass": False, "detail": f"TARGET ERROR: {err}", "response": ""}
    ok, detail = grade(task, resp)
    return {**base, "pass": ok, "detail": detail, "response": resp[:2000]}

def summarize(rows, key="category"):
    by = {}
    for r in rows:
        by.setdefault(r.get(key) or "?", []).append(r["pass"])
    return {c: {"passed": sum(v), "total": len(v), "pct": round(100 * sum(v) / len(v), 1)}
            for c, v in sorted(by.items())}

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", help="label for this run (results/<name>.json)")
    ap.add_argument("--base-url")
    ap.add_argument("--model")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY")
    ap.add_argument("--auth", choices=["bearer", "xapikey"], default="bearer")
    ap.add_argument("--cmd")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--track", choices=["closed", "tools"], default="closed",
                    help="closed = vanilla model, no tools; tools = keccak tasks for a tool-using agent")
    ap.add_argument("--category")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--save-partial", action="store_true",
                    help="save even if tasks never reached the target (score will understate)")
    ap.add_argument("--abort-after", type=int, default=10,
                    help="stop the run after this many consecutive target errors (0 = never)")
    args = ap.parse_args()

    tools = args.track == "tools"
    tasks = load_tasks(args.category, args.limit,
                       TOOLS_TASKS_DIR if tools else TASKS_DIR)
    if not tasks:
        sys.exit("no tasks found")
    if tools and not args.self_test:
        for t in tasks:
            t["prompt"] = TOOL_PREFIX + t["prompt"]

    if args.self_test:
        # reference must pass, every checks.must_pass must pass, every
        # checks.must_fail must fail — the fixtures are what catch a grader
        # that accepts wrong answers or rejects right ones; the reference
        # alone was written to fit the grader and proves little.
        rows, n_fix = [], 0
        for t in tasks:
            ok, detail = grade(t, t["reference"])
            probs = [] if ok else [f"reference: {detail}"]
            checks = t.get("checks", {})
            for s in checks.get("must_pass", []):
                p, d = grade(t, s)
                n_fix += 1
                if not p:
                    probs.append(f"must_pass rejected {s[:60]!r}: {d}")
            # shared adversarial fixtures, synthesized for EVERY task: a
            # response that names the reference answer while denying it must
            # never pass. Skipped when the reference itself is negated
            # (honesty tasks) — double negation is ambiguous there.
            ref_ans = ans_line(t["reference"])
            auto_neg = []
            if ref_ans and not _NEG_RE.search(t["reference"]) and not checks.get("no_auto_negation"):
                auto_neg = [f"Answer: not {ref_ans}",
                            f"Answer: definitely not {ref_ans}",
                            f"The correct answer is not {ref_ans}"]
            for s in checks.get("must_fail", []) + auto_neg:
                p, _ = grade(t, s)
                n_fix += 1
                if p:
                    probs.append(f"must_fail accepted {s[:60]!r}")
            rows.append({"id": t["id"], "category": t["category"], "pass": not probs})
            for pr in probs:
                print(f"SELF-TEST FAIL {t['id']}: {pr}")
        cats = summarize(rows)
        n_ok = sum(r["pass"] for r in rows)
        print(f"\nself-test: {n_ok}/{len(rows)} tasks green ({n_fix} fixtures) across {len(cats)} categories")
        sys.exit(0 if n_ok == len(rows) else 1)

    if args.cmd:
        target = CmdTarget(args.cmd)
    elif args.base_url and args.model:
        key = os.environ.get(args.api_key_env, "")
        target = OpenAITarget(args.base_url, args.model, key, args.auth)
    else:
        sys.exit("need --self-test, --cmd, or --base-url + --model")

    if not args.name:
        sys.exit("--name is required for a real run")

    work = tasks * args.runs
    print(f"running {len(work)} tasks against {target.desc} (concurrency {args.concurrency})")
    t0 = time.time()
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(run_one, target, t, args.max_tokens): t for t in work}
        done, streak, aborted = 0, 0, False
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            rows.append(r)
            done += 1
            mark = "✓" if r["pass"] else "✗"
            if args.verbose or not r["pass"]:
                print(f"  {mark} {r['id']} ({r['latency_s']}s) {r['detail'][:110]}")
            elif done % 10 == 0:
                print(f"  … {done}/{len(work)}")
            # a dead target (rate limit, bad key, wrong model name) otherwise
            # grinds through every task and saves a score that is really an
            # outage. Bail once it is clearly the target and not one hiccup.
            streak = streak + 1 if r["detail"].startswith("TARGET ERROR") else 0
            if args.abort_after and streak >= args.abort_after:
                aborted = True
                print(f"\nABORTED: {streak} target errors in a row — the target is down, "
                      f"not the model.\n  last: {r['detail'][:200]}")
                ex.shutdown(wait=False, cancel_futures=True)
                break
    if aborted:
        sys.exit(2)
    # network hiccups must not poison scores: re-run TARGET ERROR rows (gently)
    for sweep in range(2):
        errs = [i for i, r in enumerate(rows) if r["detail"].startswith("TARGET ERROR")]
        if not errs:
            break
        byid = {t["id"]: t for t in work}
        print(f"retry sweep {sweep+1}: {len(errs)} target errors")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futs = {ex.submit(run_one, target, byid[rows[i]["id"]], args.max_tokens): i for i in errs}
            for fut in concurrent.futures.as_completed(futs):
                rows[futs[fut]] = fut.result()
    elapsed = time.time() - t0

    left = sum(1 for r in rows if r["detail"].startswith("TARGET ERROR"))
    if left:
        print(f"WARNING: {left}/{len(rows)} tasks never reached the target — "
              f"they are scored as failures, so this is an outage, not a score.")
        if not args.save_partial:
            sys.exit("refusing to save a poisoned run (--save-partial to override)")
    rows.sort(key=lambda r: r["id"])
    cats = summarize(rows)
    skills = summarize(rows, key="source")
    overall = round(sum(c["pct"] for c in cats.values()) / len(cats), 1) if cats else 0.0
    lo, hi = bootstrap_ci(rows)
    tok_in = sum(r["usage"].get("prompt_tokens", 0) for r in rows)
    tok_out = sum(r["usage"].get("completion_tokens", 0) for r in rows)

    print(f"\n{'category':<16}{'score':>7}   passed")
    for c, s in cats.items():
        print(f"{c:<16}{s['pct']:>7}   {s['passed']}/{s['total']}")
    print(f"{'OVERALL':<16}{overall:>7}   (95% CI {lo:.1f}–{hi:.1f})")
    tok_note = f" · tokens in {tok_in:,} out {tok_out:,}" if tok_in else ""
    print(f"{len(rows)} tasks in {elapsed:.0f}s{tok_note}")

    results_dir = TOOLS_RESULTS_DIR if tools else RESULTS_DIR
    results_dir.mkdir(exist_ok=True)
    # manifest covers the FULL track corpus; a --category/--limit run is a
    # subset and is flagged so the reporter never ranks it.
    full = load_tasks(tasks_dir=TOOLS_TASKS_DIR if tools else TASKS_DIR)
    out = {
        "name": args.name, "target": target.desc, "track": args.track,
        "benchmark": {
            "version": BENCH_VERSION,
            "manifest_sha256": manifest_hash(full),
            "task_count": len(full),
            "harness_commit": harness_commit(),
            "subset": bool(args.category or args.limit),
        },
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "overall": overall, "ci95": [round(lo, 1), round(hi, 1)],
        "categories": cats, "skills": skills, "elapsed_s": round(elapsed, 1),
        "tokens": {"in": tok_in, "out": tok_out},
        "runs": args.runs, "temperature": 0, "tasks": rows,
    }
    path = results_dir / f"{args.name}.json"
    path.write_text(json.dumps(out, indent=1))
    print(f"saved {path.relative_to(HERE)}")

if __name__ == "__main__":
    main()
