#!/usr/bin/env python3
"""Regenerate REVIEW.md — every task in every track, human-readable.

Usage: python3 gen/make_review.py   (overwrites REVIEW.md)
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent

out = ["# eth-evals — all tasks for review", ""]
counts = {}
for d, label in [("tasks", "closed book"), ("tasks-tools", "tool track — agent has cast"),
                 ("tasks-live", "live track — graded against mainnet at run time")]:
    files = sorted((HERE / d).glob("*.jsonl"))
    if not files:
        continue
    for f in files:
        out += ["", f"## {d}/{f.name}  ({label})", ""]
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            t = json.loads(line)
            counts[d] = counts.get(d, 0) + 1
            kind = t.get("kind", "computed" if t.get("source") == "generated" else "live")
            out.append(f"### {t['id']}  ({kind})")
            out.append("**Q:** " + t["prompt"])
            out.append("")
            if "grader" in t:
                out.append(f"**Grader:** `{json.dumps(t['grader'])}`")
            if "truth" in t:
                out.append(f"**Truth (computed at grade time):** `{json.dumps(t['truth'])}`")
            if "reference" in t:
                out.append(f"**Reference:** {t['reference']}")
            sq = t.get("source_quote")
            if sq and sq != "self-contained":
                out.append(f"**Source quote:** {sq}")
            ch = t.get("checks")
            if ch:
                out.append(f"**Fixtures:** `{json.dumps(ch)}`")
            out.append("")

names = {"tasks": "closed-book", "tasks-tools": "tool-track", "tasks-live": "live"}
summary = " + ".join(f"{n} {names[d]}" for d, n in counts.items())
out.insert(1, f"\n{summary} tasks. Regenerate with `python3 gen/make_review.py`.\n")
(HERE / "REVIEW.md").write_text("\n".join(out) + "\n")
print(f"REVIEW.md: {summary}")
