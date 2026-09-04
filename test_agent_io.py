#!/usr/bin/env python3
"""Effort capture: turns / cost / tokens ride along with every agent answer.

No model runs. A fake `claude` on PATH emits the real `--output-format json`
envelope so the unwrap path is exercised end to end, including through
run_eval.CmdTarget. Also pins: pipelines and non-claude commands are never
rewritten, and a plain-text agent still answers normally with empty meta.
"""
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from harness.agent_io import instrument, parse_claude_json, run_agent, effort_summary  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# --- instrument: only a bare claude -p gets the flag --------------------------
check("bare claude -p gets json output",
      instrument("claude -p --model fable") == "claude -p --model fable --output-format json")
check("claude with flags after -p still instrumented",
      instrument("claude -p --model haiku --disallowedTools Bash").endswith("--output-format json"))
check("already-json claude untouched",
      instrument("claude -p --output-format json") == "claude -p --output-format json")
check("pipeline untouched",
      instrument("f=$(mktemp); codex exec -o \"$f\" -; cat \"$f\"") == "f=$(mktemp); codex exec -o \"$f\" -; cat \"$f\"")
check("claude in a pipeline untouched", instrument("claude -p | tee out") == "claude -p | tee out")
check("non-claude untouched", instrument("python3 ref.py") == "python3 ref.py")
check("claude without -p untouched", instrument("claude --version") == "claude --version")

# --- parse: the real envelope shape -----------------------------------------
ENV = {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 12345,
       "duration_api_ms": 9876, "num_turns": 7, "result": "Answer: 21000",
       "total_cost_usd": 0.0421, "session_id": "x",
       "usage": {"input_tokens": 12, "cache_creation_input_tokens": 3000,
                 "cache_read_input_tokens": 45000, "output_tokens": 800}}
text, meta, raw = parse_claude_json(json.dumps(ENV))
check("text is the result field", text == "Answer: 21000")
check("turns parsed", meta["turns"] == 7)
check("cost parsed", meta["cost_usd"] == 0.0421)
check("tokens parsed", (meta["prompt_tokens"], meta["completion_tokens"],
                        meta["cache_read_tokens"], meta["cache_write_tokens"]) == (12, 800, 45000, 3000))
check("api seconds parsed", meta["api_s"] == 9.9)
check("leading noise tolerated", parse_claude_json("warn: something\n" + json.dumps(ENV))[1]["turns"] == 7)
check("plain text is not an envelope", parse_claude_json("Answer: 21000") == (None, {}, None))
check("other json is not an envelope", parse_claude_json('{"a": 1}') == (None, {}, None))
err = dict(ENV, subtype="error_max_turns", result=None)
t, m, _ = parse_claude_json(json.dumps(err))
check("error envelope: empty text, meta kept", t == "" and m["subtype"] == "error_max_turns" and m["turns"] == 7)

# --- end to end through a fake claude on PATH --------------------------------
with tempfile.TemporaryDirectory() as td:
    fake = Path(td) / "claude"
    fake.write_text("#!/bin/sh\n"
                    "# fake claude: refuse unless asked for json, echo the prompt back inside the envelope\n"
                    "case \"$*\" in *'--output-format json'*) ;; *) echo 'no json flag' >&2; exit 3;; esac\n"
                    "p=$(cat)\n"
                    "printf '%s' \"{\\\"type\\\":\\\"result\\\",\\\"subtype\\\":\\\"success\\\",\\\"num_turns\\\":3,"
                    "\\\"total_cost_usd\\\":0.5,\\\"duration_api_ms\\\":1500,\\\"result\\\":\\\"echo: $p\\\","
                    "\\\"usage\\\":{\\\"input_tokens\\\":5,\\\"output_tokens\\\":9}}\"\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PATH=td + os.pathsep + os.environ.get("PATH", ""))
    r = run_agent("claude -p --model fable", "what is 2+2", cwd=td, env=env, timeout=30)
    check("fake claude unwrapped", r.text == "echo: what is 2+2" and r.returncode == 0, r.stderr)
    check("fake claude meta", r.meta["turns"] == 3 and r.meta["cost_usd"] == 0.5 and r.meta["prompt_tokens"] == 5)
    check("raw envelope kept", r.raw and r.raw["type"] == "result")

    import run_eval
    tgt = run_eval.CmdTarget("claude -p --model fable", cwd=td)
    tgt.env = env
    text, usage = tgt.ask("hi", 0)
    check("CmdTarget returns unwrapped text", text == "echo: hi")
    check("CmdTarget returns effort as usage", usage["turns"] == 3 and usage["completion_tokens"] == 9)

    r = run_agent("cat", "plain agent", cwd=td, env=env, timeout=30)
    check("plain agent: text through, meta empty", r.text == "plain agent" and r.meta == {} and r.raw is None)

# --- summary ---------------------------------------------------------------
rows = [{"usage": {"turns": 3, "cost_usd": 0.5, "prompt_tokens": 5, "completion_tokens": 9}},
        {"usage": {}}, {"usage": {"turns": 2, "cost_usd": 0.25, "prompt_tokens": 1, "completion_tokens": 1}}]
s = effort_summary(rows)
check("summary totals", (s["turns"], s["cost_usd"], s["prompt_tokens"], s["completion_tokens"], s["n"]) == (5, 0.75, 6, 10, 2))

print(f"\n{'FAIL ' + str(FAILS) if FAILS else 'all green'}")
sys.exit(1 if FAILS else 0)
