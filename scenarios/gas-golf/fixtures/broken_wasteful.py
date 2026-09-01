#!/usr/bin/env python3
"""Broken fixture: correct, but deliberately wasteful — copies the calldata to
a memory array and hashes each element into a running accumulator it discards,
blowing well past even the loose cap.

Expected: compiles + correct pass; under_loose_cap and under_tight_cap fail.
Score 30.
"""
from pathlib import Path

WASTEFUL = r"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract Solution {
    function solve(uint256[] calldata xs) external pure returns (uint256 s) {
        uint256[] memory m = xs;                 // full memory copy
        uint256 waste;
        unchecked {
            for (uint256 i = 0; i < m.length; i++) {
                waste = uint256(keccak256(abi.encode(m[i], i)));   // burn gas
                s += m[i] * (i + 1) + (waste - waste);
            }
        }
    }
}
"""


def main():
    Path("src/Solution.sol").write_text(WASTEFUL)
    print("wrote wasteful Solution.sol")


if __name__ == "__main__":
    main()
