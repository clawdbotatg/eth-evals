// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

// A two-token Balancer-V2-style stable pool, reproducing the November 2025
// rounding vulnerability (CVE-class: rate-provider scaling + mulDown upscale).
//
// Token Y carries a rate-provider scaling factor fY > 1e18 (an LST-like rate).
// `_upscale` uses mulDown (floor) UNCONDITIONALLY, even for the token-in leg
// that should round up. In an EXACT_OUT swap the required input is solved from
// the FLOORED scaled amounts, so at low balances the pool under-charges the
// caller while its invariant guard (recomputed from the same floored balances)
// stays satisfied. Repeated tiny swaps drain the pool's value.

contract MockERC20 {
    uint8 public decimals = 18;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 a) external { balanceOf[to] += a; totalSupply += a; }
    function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; return true; }
    function transfer(address to, uint256 a) external returns (bool) {
        balanceOf[msg.sender] -= a; balanceOf[to] += a; return true;
    }
    function transferFrom(address f, address t, uint256 a) external returns (bool) {
        if (allowance[f][msg.sender] != type(uint256).max) allowance[f][msg.sender] -= a;
        balanceOf[f] -= a; balanceOf[t] += a; return true;
    }
}

contract StablePool {
    uint256 constant ONE = 1e18;
    MockERC20 public immutable x;
    MockERC20 public immutable y;
    uint256 public immutable A;     // amplification (already * n)
    uint256 public immutable fX;    // scaling factor X (1e18)
    uint256 public immutable fY;    // scaling factor Y (> 1e18, a rate provider)
    uint256 public bX;              // internal balances (donation-proof)
    uint256 public bY;

    constructor(address _x, address _y, uint256 _A, uint256 _fX, uint256 _fY,
                uint256 _bX, uint256 _bY) {
        x = MockERC20(_x); y = MockERC20(_y);
        A = _A; fX = _fX; fY = _fY; bX = _bX; bY = _bY;
    }

    function mulDown(uint256 a, uint256 b) internal pure returns (uint256) { return a * b / ONE; }
    function divDown(uint256 a, uint256 b) internal pure returns (uint256) { return a * ONE / b; }
    function upX(uint256 b) public view returns (uint256) { return mulDown(b, fX); }
    function upY(uint256 b) public view returns (uint256) { return mulDown(b, fY); }

    function computeD(uint256 xb, uint256 yb) public view returns (uint256 D) {
        uint256 S = xb + yb;
        if (S == 0) return 0;
        D = S;
        uint256 Ann = A * 2;
        for (uint256 i = 0; i < 255; i++) {
            uint256 D_P = D;
            D_P = D_P * D / (xb * 2);
            D_P = D_P * D / (yb * 2);
            uint256 Dp = D;
            D = (Ann * S / ONE + D_P * 2) * D / ((Ann - ONE) * D / ONE + 3 * D_P);
            if (D > Dp) { if (D - Dp <= 1) break; } else { if (Dp - D <= 1) break; }
        }
    }

    function getY(uint256 D, uint256 other) public view returns (uint256 yb) {
        uint256 Ann = A * 2;
        uint256 cc = D * D / (other * 2);
        cc = cc * ONE / (Ann * 2);
        cc = cc * D / ONE;
        uint256 b = other + D * ONE / (Ann * 2);
        yb = D;
        for (uint256 i = 0; i < 255; i++) {
            uint256 yp = yb;
            yb = (yb * yb + cc) / (2 * yb + b - D);
            if (yb > yp) { if (yb - yp <= 1) break; } else { if (yp - yb <= 1) break; }
        }
    }

    function poolD() public view returns (uint256) { return computeD(upX(bX), upY(bY)); }
    function trueValue() external view returns (uint256) { return bX * fX + bY * fY; }

    /// Query the input a swap would charge and whether it would satisfy the
    /// invariant guard, without changing state (a `queryBatchSwap` analog).
    function quoteExactOut(bool outIsY, uint256 outAmt)
        external view returns (uint256 inAmt, bool ok)
    {
        uint256 D0 = poolD();
        if (outIsY) {
            if (outAmt >= bY) return (0, false);
            uint256 sYnew = upY(bY) - upY(outAmt);
            if (sYnew == 0) return (0, false);
            uint256 g = getY(D0, sYnew);
            if (g <= upX(bX)) return (0, false);
            inAmt = divDown(g - upX(bX), fX);
            if (inAmt == 0) return (0, false);
            ok = computeD(upX(bX + inAmt), upY(bY - outAmt)) + 2 >= D0;
        } else {
            if (outAmt >= bX) return (0, false);
            uint256 sXnew = upX(bX) - upX(outAmt);
            if (sXnew == 0) return (0, false);
            uint256 g = getY(D0, sXnew);
            if (g <= upY(bY)) return (0, false);
            inAmt = divDown(g - upY(bY), fY);
            if (inAmt == 0) return (0, false);
            ok = computeD(upX(bX - outAmt), upY(bY + inAmt)) + 2 >= D0;
        }
    }

    /// Take exactly `outAmt` of the chosen token; pay the required amount of
    /// the other. Returns the input charged.
    function swapExactOut(bool outIsY, uint256 outAmt) external returns (uint256 inAmt) {
        uint256 D0 = poolD();
        if (outIsY) {
            require(outAmt < bY, "bal");
            uint256 sYnew = upY(bY) - upY(outAmt);
            require(sYnew > 0, "sY");
            inAmt = divDown(getY(D0, sYnew) - upX(bX), fX);
            require(inAmt > 0, "in");
            bX += inAmt; bY -= outAmt;
            require(x.transferFrom(msg.sender, address(this), inAmt), "pull");
            require(y.transfer(msg.sender, outAmt), "send");
        } else {
            require(outAmt < bX, "bal");
            uint256 sXnew = upX(bX) - upX(outAmt);
            require(sXnew > 0, "sX");
            inAmt = divDown(getY(D0, sXnew) - upY(bY), fY);
            require(inAmt > 0, "in");
            bY += inAmt; bX -= outAmt;
            require(y.transferFrom(msg.sender, address(this), inAmt), "pull");
            require(x.transfer(msg.sender, outAmt), "send");
        }
        require(poolD() + 2 >= D0, "D");   // invariant guard
    }
}
