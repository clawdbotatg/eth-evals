#!/usr/bin/env python3
"""Reference solution — must score 100/100 (harness exit test).

Hand-optimized: read the calldata array directly in assembly, wrapping mul/add,
no bounds checks, no memory copy.
"""
from pathlib import Path

OPTIMIZED = r"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract Solution {
    function solve(uint256[] calldata xs) external pure returns (uint256 s) {
        assembly {
            let len := xs.length
            let ptr := xs.offset
            for { let i := 0 } lt(i, len) { i := add(i, 1) } {
                s := add(s, mul(calldataload(ptr), add(i, 1)))
                ptr := add(ptr, 0x20)
            }
        }
    }
}
"""


def main():
    Path("src/Solution.sol").write_text(OPTIMIZED)
    print("wrote optimized Solution.sol")


if __name__ == "__main__":
    main()
