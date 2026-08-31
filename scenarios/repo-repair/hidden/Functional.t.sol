// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Sale} from "../src/Sale.sol";
import {MockERC20, MockOracle} from "../src/Mocks.sol";

interface Vm {
    function prank(address) external;
    function warp(uint256) external;
}

/// Behavioral suite. Amounts seeded by the grader: __PRICE__ (8-dec USD),
/// __AMT__ (18-dec product units), __MAXAGE__ (seconds). Each test is an
/// independent milestone.
contract FunctionalTest {
    Vm constant vm = Vm(0x7109709ECfa91a80626fF3989D68f67F5b1DD12D);

    uint256 constant NOW = 1_000_000_000;
    address buyer = address(0xB);
    address other = address(0x0DD);

    function _setup() internal returns (MockERC20 pay, MockERC20 prod, MockOracle oracle, Sale sale) {
        vm.warp(NOW);
        pay = new MockERC20(6);
        prod = new MockERC20(18);
        oracle = new MockOracle();
        oracle.set(int256(uint256(__PRICE__)), NOW);
        sale = new Sale(address(pay), address(prod), address(oracle), __MAXAGE__);
        prod.mint(address(sale), 1_000_000e18);
        // fund the buyer far beyond any cost so a stale-price revert can only
        // come from a real freshness check, never from an insufficient balance
        pay.mint(buyer, 1e30);
        vm.prank(buyer);
        pay.approve(address(sale), type(uint256).max);
    }

    function _expectedCost() internal pure returns (uint256) {
        uint256 amt = __AMT__;
        uint256 prc = __PRICE__;
        return amt * prc / 1e20;
    }

    // 1) decimal-correct pricing and delivery
    function test_cost_correct() external {
        (MockERC20 pay, MockERC20 prod,, Sale sale) = _setup();
        uint256 before = pay.balanceOf(buyer);
        vm.prank(buyer);
        sale.buy(__AMT__);
        uint256 paid = before - pay.balanceOf(buyer);
        require(paid == _expectedCost(), "wrong payment charged");
        require(prod.balanceOf(buyer) == __AMT__, "wrong product delivered");
    }

    // 2) stale oracle rejected
    function test_stale_reverts() external {
        (,, MockOracle oracle, Sale sale) = _setup();
        oracle.set(int256(uint256(__PRICE__)), NOW - __MAXAGE__ - 1);
        vm.prank(buyer);
        try sale.buy(__AMT__) {
            revert("stale price should have reverted");
        } catch {}
    }

    // 3) proceeds accounting + withdrawal
    function test_proceeds() external {
        (MockERC20 pay,,, Sale sale) = _setup();
        vm.prank(buyer);
        sale.buy(__AMT__);
        require(sale.totalProceeds() == _expectedCost(), "totalProceeds wrong");
        uint256 ob = pay.balanceOf(other);
        sale.withdrawProceeds(other);          // called by owner (this contract)
        require(pay.balanceOf(other) - ob == _expectedCost(), "withdraw sent wrong amount");
        require(sale.totalProceeds() == 0, "proceeds not reset");
    }

    // 4) only owner can withdraw
    function test_owner_only() external {
        (,,, Sale sale) = _setup();
        vm.prank(buyer);
        sale.buy(__AMT__);
        vm.prank(other);
        try sale.withdrawProceeds(other) {
            revert("non-owner withdraw should have reverted");
        } catch {}
    }
}
