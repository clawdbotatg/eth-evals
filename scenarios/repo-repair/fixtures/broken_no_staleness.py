#!/usr/bin/env python3
"""Broken fixture: everything fixed EXCEPT the oracle-staleness check.

Expected: only stale_reverts fails. Score 80.
"""
import importlib.util
from pathlib import Path

ref = importlib.util.spec_from_file_location("ref", Path(__file__).resolve().parent.parent / "reference.py")
rmod = importlib.util.module_from_spec(ref)
ref.loader.exec_module(rmod)


def main():
    src = rmod.FIXED.replace(
        '        require(block.timestamp - updatedAt <= maxAge, "stale price");\n', "")
    open("src/Sale.sol", "w").write(src)
    print("fixed all but staleness")


if __name__ == "__main__":
    main()
