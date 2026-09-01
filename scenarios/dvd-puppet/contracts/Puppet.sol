// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

// A dependency-free port of Damn Vulnerable DeFi's "Puppet": a lending pool
// that prices collateral from a constant-product AMM's spot reserves — a
// manipulable on-chain oracle. The AMM is a minimal Uniswap-v1-style ETH/token
// exchange (no fee, to keep the math clean).

contract DVT {
    string public name = "DamnValuableToken";
    string public symbol = "DVT";
    uint8 public decimals = 18;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 a) external {
        balanceOf[to] += a;
        totalSupply += a;
    }

    function approve(address s, uint256 a) external returns (bool) {
        allowance[msg.sender][s] = a;
        return true;
    }

    function transfer(address to, uint256 a) external returns (bool) {
        balanceOf[msg.sender] -= a;
        balanceOf[to] += a;
        return true;
    }

    function transferFrom(address f, address t, uint256 a) external returns (bool) {
        if (allowance[f][msg.sender] != type(uint256).max) {
            allowance[f][msg.sender] -= a;
        }
        balanceOf[f] -= a;
        balanceOf[t] += a;
        return true;
    }
}

/// Constant-product ETH/token AMM. `tokenReserve`/`ethReserve` are just the
/// contract's balances; swaps preserve x*y=k.
contract Amm {
    DVT public token;

    constructor(address _token) {
        token = DVT(_token);
    }

    function tokenReserve() public view returns (uint256) {
        return token.balanceOf(address(this));
    }

    function ethReserve() public view returns (uint256) {
        return address(this).balance;
    }

    // seed initial reserves (called once at setup)
    function init(uint256 tokenAmount) external payable {
        token.transferFrom(msg.sender, address(this), tokenAmount);
    }

    // sell `tokensIn` for ETH
    function tokenToEth(uint256 tokensIn) external returns (uint256 ethOut) {
        uint256 k = tokenReserve() * ethReserve();
        token.transferFrom(msg.sender, address(this), tokensIn);
        uint256 newEth = k / tokenReserve();
        ethOut = ethReserve() - newEth;
        (bool ok, ) = msg.sender.call{value: ethOut}("");
        require(ok, "eth send");
    }

    // buy tokens with ETH
    function ethToToken() external payable returns (uint256 tokensOut) {
        uint256 ethIn = msg.value;
        uint256 k = tokenReserve() * (ethReserve() - ethIn);
        uint256 newToken = k / ethReserve();
        tokensOut = tokenReserve() - newToken;
        token.transfer(msg.sender, tokensOut);
    }

    receive() external payable {}
}

/// Lends DVT against ETH collateral. Required collateral = 2x the borrowed
/// tokens valued at the AMM's SPOT price — the vulnerability.
contract LendingPool {
    DVT public token;
    Amm public amm;

    constructor(address _token, address _amm) {
        token = DVT(_token);
        amm = Amm(payable(_amm));
    }

    /// price of one whole token in wei, from AMM spot reserves
    function tokenPriceInWei() public view returns (uint256) {
        return (amm.ethReserve() * 1e18) / amm.tokenReserve();
    }

    function requiredCollateral(uint256 amount) public view returns (uint256) {
        return (amount * tokenPriceInWei() * 2) / 1e18;
    }

    function borrow(uint256 amount, address recipient) external payable {
        require(msg.value >= requiredCollateral(amount), "insufficient collateral");
        token.transfer(recipient, amount);
    }
}
