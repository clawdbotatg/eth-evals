#!/usr/bin/env python3
"""Broken fixture: a correct but un-optimized Solidity loop.

Expected: compiles + correct + under_loose_cap pass; under_tight_cap fails.
Score 50.
"""
from pathlib import Path

NAIVE = r"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract Solution {
    function solve(uint256[] calldata xs) external pure returns (uint256 s) {
        unchecked {
            for (uint256 i = 0; i < xs.length; i++) {
                s += xs[i] * (i + 1);
            }
        }
    }
}
"""


def main():
    Path("src/Solution.sol").write_text(NAIVE)
    print("wrote naive Solution.sol")


if __name__ == "__main__":
    main()
