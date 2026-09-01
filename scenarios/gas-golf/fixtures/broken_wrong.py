#!/usr/bin/env python3
"""Broken fixture: fast but WRONG — an unweighted sum (forgets the *(i+1)).

Expected: compiles passes; correct, under_loose_cap, under_tight_cap all fail
(the cap tests also require the right output). Score 10.
"""
from pathlib import Path

WRONG = r"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract Solution {
    function solve(uint256[] calldata xs) external pure returns (uint256 s) {
        assembly {
            let len := xs.length
            let ptr := xs.offset
            for { let i := 0 } lt(i, len) { i := add(i, 1) } {
                s := add(s, calldataload(ptr))    // missing the *(i+1) weight
                ptr := add(ptr, 0x20)
            }
        }
    }
}
"""


def main():
    Path("src/Solution.sol").write_text(WRONG)
    print("wrote wrong Solution.sol")


if __name__ == "__main__":
    main()
