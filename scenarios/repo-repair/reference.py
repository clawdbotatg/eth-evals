#!/usr/bin/env python3
"""Reference solution — must score 100/100 on every seed (harness exit test).

Runs in the workspace like an agent: overwrites src/Sale.sol with a fixed
version (compiles, decimal-correct, staleness-checked, accounted,
owner-gated).
"""

FIXED = r"""// SPDX-License-Identifier: MIT
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
        (, int256 answer, , uint256 updatedAt, ) = oracle.latestRoundData();
        require(answer > 0, "bad price");
        require(block.timestamp - updatedAt <= maxAge, "stale price");
        return uint256(answer);
    }

    function buy(uint256 productAmount) external {
        uint256 p = price();
        // 18-dec product * 8-dec price -> 6-dec payment
        uint256 cost = productAmount * p / 1e20;
        require(cost > 0, "dust");
        require(payment.transferFrom(msg.sender, address(this), cost), "pay");
        totalProceeds += cost;
        require(product.transfer(msg.sender, productAmount), "send");
    }

    function withdrawProceeds(address to) external {
        require(msg.sender == owner, "not owner");
        uint256 amt = totalProceeds;
        totalProceeds = 0;
        require(payment.transfer(to, amt), "withdraw");
    }
}
"""


def main():
    open("src/Sale.sol", "w").write(FIXED)
    print("wrote fixed Sale.sol")


if __name__ == "__main__":
    main()
