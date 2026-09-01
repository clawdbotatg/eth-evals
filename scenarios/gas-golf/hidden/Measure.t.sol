// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Solution} from "../src/Solution.sol";

interface ISolve {
    function solve(uint256[] calldata xs) external pure returns (uint256);
}

/// Grades the agent's Solution on three independent milestones: correctness,
/// under a loose gas cap (any working solution), and under a tight gas cap
/// (requires real optimization). Inputs are seeded (__SEED__); caps are
/// tuned to a fixed length-32 array so gas is comparable across solutions.
contract Measure {
    uint256 constant SEED = __SEED__;
    uint256 constant LOOSE = __LOOSE__;
    uint256 constant TIGHT = __TIGHT__;

    function _xs(uint256 salt) internal pure returns (uint256[] memory a) {
        a = new uint256[](32);
        for (uint256 i = 0; i < 32; i++) {
            a[i] = uint256(keccak256(abi.encode(SEED, salt, i)));
        }
    }

    function _expected(uint256[] memory a) internal pure returns (uint256 s) {
        unchecked {
            for (uint256 i = 0; i < a.length; i++) {
                s += a[i] * (i + 1);
            }
        }
    }

    function test_correct() external {
        Solution sol = new Solution();
        for (uint256 k = 0; k < 4; k++) {
            uint256[] memory a = _xs(k);
            require(ISolve(address(sol)).solve(a) == _expected(a), "wrong output");
        }
    }

    function test_under_loose_cap() external {
        Solution sol = new Solution();
        uint256[] memory a = _xs(0);
        uint256 g = gasleft();
        uint256 r = ISolve(address(sol)).solve(a);
        g -= gasleft();
        require(r == _expected(a), "wrong output");
        require(g <= LOOSE, "over loose cap");
    }

    function test_under_tight_cap() external {
        Solution sol = new Solution();
        uint256[] memory a = _xs(0);
        uint256 g = gasleft();
        uint256 r = ISolve(address(sol)).solve(a);
        g -= gasleft();
        require(r == _expected(a), "wrong output");
        require(g <= TIGHT, "over tight cap");
    }
}
