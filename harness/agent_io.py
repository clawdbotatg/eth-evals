"""Run an agent CLI and keep its effort, not just its answer.

Every runner (closed-book, live, exec, arena) shells out to an agent with the
prompt on stdin and reads the answer from stdout. This is the one place that
does it, so every result row carries the same effort fields:

    turns              model round-trips (tool calls + 1), when the CLI reports it
    cost_usd           what the CLI says the attempt cost
    prompt_tokens      input tokens (fresh, excluding cache reads)
    completion_tokens  output tokens
    cache_read_tokens / cache_write_tokens
    api_s              seconds spent waiting on the model, not the tools

Only `claude -p` reports these today: when the command is a bare claude
invocation we append `--output-format json` and unwrap the result envelope,
so the caller still sees plain answer text. Any other command runs untouched
and gets an empty meta. Two scores that tie on correctness then split on
cost and turns, which is the second axis SRE-Bench reports and we did not.
"""
import json
import re
import subprocess

_BARE_CLAUDE = re.compile(r"^\s*claude\b")
_SHELL_META = re.compile(r"[;|&<>`$]")   # a pipeline or wrapper: leave it alone


class AgentRun:
    __slots__ = ("text", "meta", "stdout", "stderr", "returncode", "raw")

    def __init__(self, text, meta, stdout, stderr, returncode, raw=None):
        self.text, self.meta = text, meta
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode
        self.raw = raw   # the parsed JSON envelope, when there was one


def instrument(cmd):
    """Return the command to actually run. Bare `claude -p ...` gets JSON
    output so we can read turns and cost; everything else passes through."""
    if _BARE_CLAUDE.match(cmd) and " -p" in f" {cmd}" and "--output-format" not in cmd \
            and not _SHELL_META.search(cmd):
        return cmd + " --output-format json"
    return cmd


def parse_claude_json(stdout):
    """(text, meta, raw) from a `claude -p --output-format json` envelope, or
    (None, {}, None) when stdout is not one. Tolerates leading noise lines."""
    s = (stdout or "").strip()
    start = s.find("{")
    if start < 0:
        return None, {}, None
    try:
        data = json.loads(s[start:])
    except ValueError:
        return None, {}, None
    if not isinstance(data, dict) or data.get("type") != "result":
        return None, {}, None
    u = data.get("usage") or {}
    meta = {
        "turns": data.get("num_turns"),
        "cost_usd": data.get("total_cost_usd"),
        "prompt_tokens": u.get("input_tokens", 0),
        "completion_tokens": u.get("output_tokens", 0),
        "cache_read_tokens": u.get("cache_read_input_tokens", 0),
        "cache_write_tokens": u.get("cache_creation_input_tokens", 0),
        "api_s": round((data.get("duration_api_ms") or 0) / 1000, 1),
        "subtype": data.get("subtype"),
    }
    text = data.get("result")
    if not isinstance(text, str):
        text = ""
    return text, meta, data


def run_agent(cmd, prompt, *, cwd=None, env=None, timeout=900):
    real = instrument(cmd)
    p = subprocess.run(real, shell=True, input=prompt, capture_output=True, text=True,
                       timeout=timeout, env=env, cwd=cwd)
    text, meta, raw = (None, {}, None)
    if real != cmd:
        text, meta, raw = parse_claude_json(p.stdout)
    if text is None:
        text = (p.stdout or "").strip()
    return AgentRun(text, meta, p.stdout or "", p.stderr or "", p.returncode, raw)


def effort_summary(rows, key="usage"):
    """Totals across result rows for the run footer: turns, cost, tokens."""
    tot = {"turns": 0, "cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "n": 0}
    for r in rows:
        u = r.get(key) or {}
        if not u:
            continue
        tot["n"] += 1
        tot["turns"] += u.get("turns") or 0
        tot["cost_usd"] += u.get("cost_usd") or 0.0
        tot["prompt_tokens"] += u.get("prompt_tokens") or 0
        tot["completion_tokens"] += u.get("completion_tokens") or 0
    return tot
