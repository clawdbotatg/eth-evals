#!/usr/bin/env python3
"""Pass rates across saved exec-results bundles.

One run is a data point, not a pass rate. This groups every saved bundle by
(model, scenario) and prints runs / perfect runs / pass rate / mean score, so
a single 100 is never mistaken for "solved".

Usage:  python3 harness/exec_report.py [--name fable]
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
RESULTS = HERE / "exec-results"


def load():
    rows = []
    for f in sorted(RESULTS.glob("*/result.json")):
        try:
            rows.append(json.loads(f.read_text()))
        except (OSError, ValueError):
            continue
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", help="only this model name")
    args = ap.parse_args()

    groups = defaultdict(list)
    for r in load():
        if args.name and r.get("name") != args.name:
            continue
        groups[(r["name"], r["scenario"])].append(r)
    if not groups:
        print("no saved bundles in exec-results/")
        return
    print(f"{'model':<14}{'scenario':<28}{'runs':>5}{'perfect':>8}{'rate':>7}{'mean':>6}{'seeds':>10}")
    by_model = defaultdict(lambda: [0, 0])
    for (name, sc), rs in sorted(groups.items()):
        perfect = sum(1 for r in rs if r["score"] == r["max_score"] and not r["safety_violations"])
        mean = sum(r["score"] for r in rs) / len(rs)
        seeds = ",".join(str(s) for s in sorted({r["seed"] for r in rs}))
        by_model[name][0] += perfect
        by_model[name][1] += len(rs)
        print(f"{name:<14}{sc:<28}{len(rs):>5}{perfect:>8}{perfect/len(rs):>7.0%}{mean:>6.0f}{seeds:>10}")
    print()
    for name, (p, n) in sorted(by_model.items()):
        print(f"{name}: {p}/{n} perfect runs ({p/n:.0%})")


if __name__ == "__main__":
    main()
