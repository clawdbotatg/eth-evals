#!/usr/bin/env python3
"""Broken fixture: fixes only the compile error (latestAnswer ->
latestRoundData). All four behavioral bugs remain.

Expected: builds passes; cost_correct, stale_reverts, proceeds_accounting,
owner_only_withdraw all fail. Score 15.
"""

COMPILES_BUT_BUGGY = r"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transfer(address, uint256) external returns (bool);
    function transferFrom(address, address, uint256) external returns (bool);
    function balanceOf(address) external view returns (uint256);
}

interface IPriceOracle {
    function latestRoundData()
        external view returns (uint80, int256, uint256, uint256, uint80);
}

contract Sale {
    address public owner;
    IERC20 public payment;
    IERC20 public product;
    IPriceOracle public oracle;
    uint256 public maxAge;
    uint256 public totalProceeds;

    constructor(address _payment, address _product, address _oracle, uint256 _maxAge) {
        owner = msg.sender;
        payment = IERC20(_payment);
        product = IERC20(_product);
        oracle = IPriceOracle(_oracle);
        maxAge = _maxAge;
    }

    function price() public view returns (uint256) {
        (, int256 answer, , , ) = oracle.latestRoundData();
        require(answer > 0, "bad price");
        return uint256(answer);
    }

    function buy(uint256 productAmount) external {
        uint256 p = price();
        uint256 cost = productAmount * p / 1e8;
        payment.transferFrom(msg.sender, address(this), cost);
        product.transfer(msg.sender, productAmount);
    }

    function withdrawProceeds(address to) external {
        payment.transfer(to, totalProceeds);
    }
}
"""


def main():
    open("src/Sale.sol", "w").write(COMPILES_BUT_BUGGY)
    print("fixed compile only")


if __name__ == "__main__":
    main()
