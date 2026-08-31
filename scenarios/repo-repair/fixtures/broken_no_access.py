#!/usr/bin/env python3
"""Broken fixture: everything fixed EXCEPT the owner check on
withdrawProceeds.

Expected: only owner_only_withdraw fails. Score 80.
"""
import importlib.util
from pathlib import Path

ref = importlib.util.spec_from_file_location("ref", Path(__file__).resolve().parent.parent / "reference.py")
rmod = importlib.util.module_from_spec(ref)
ref.loader.exec_module(rmod)


def main():
    src = rmod.FIXED.replace('        require(msg.sender == owner, "not owner");\n', "")
    open("src/Sale.sol", "w").write(src)
    print("fixed all but access control")


if __name__ == "__main__":
    main()
