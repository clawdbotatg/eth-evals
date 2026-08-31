// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transfer(address, uint256) external returns (bool);
    function transferFrom(address, address, uint256) external returns (bool);
    function balanceOf(address) external view returns (uint256);
}

interface IPriceOracle {
    // Chainlink-style: (roundId, answer, startedAt, updatedAt, answeredInRound)
    function latestRoundData()
        external view returns (uint80, int256, uint256, uint256, uint80);
}

/// Sells a product token for a payment token, priced by an oracle.
///
///   payment token: 6 decimals   (USDC-like)
///   product token: 18 decimals
///   oracle answer: 8 decimals    (USD per whole product token)
///
/// This contract does not currently work. It does not compile, and it has
/// several behavioral bugs. See SPEC.md.
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
        int256 answer = oracle.latestAnswer();
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
