#!/usr/bin/env python3
"""Broken fixture: registers a team and stops.

Expected: flag1 only. Score 10.
"""
import json
import subprocess
import sys
from pathlib import Path


def cast(*a):
    p = subprocess.run(["cast", *a], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        sys.exit(f"cast failed: {p.stderr[:200]}")
    return p.stdout.strip()


def main():
    p = json.loads(Path("params.json").read_text())
    key = Path(p["key_file"]).read_text().strip()
    cast("send", "--rpc-url", p["rpc_url"], "--private-key", key,
         p["challenge1"], "registerTeam(string,uint8)", "team", "1")
    print("registered team only")


if __name__ == "__main__":
    main()
