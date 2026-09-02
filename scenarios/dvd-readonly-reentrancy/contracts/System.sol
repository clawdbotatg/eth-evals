// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

// A minimal reproduction of the read-only reentrancy class (dForce / Curve,
// 2023). The pool's LP price `get_virtual_price()` is a VIEW with no reentrancy
// guard. `remove_liquidity` burns LP (dropping totalSupply) and then makes an
// external ETH transfer BEFORE it reduces the reserves — so during that
// callback `get_virtual_price() = D/totalSupply` is transiently inflated. A
// lending market that reads that price as an LP-collateral oracle can be made
// to over-lend from inside the callback.

contract Token {
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    function mint(address t, uint256 a) external { balanceOf[t] += a; totalSupply += a; }
    function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; return true; }
    function transfer(address t, uint256 a) external returns (bool) { balanceOf[msg.sender] -= a; balanceOf[t] += a; return true; }
    function transferFrom(address f, address t, uint256 a) external returns (bool) {
        if (allowance[f][msg.sender] != type(uint256).max) allowance[f][msg.sender] -= a;
        balanceOf[f] -= a; balanceOf[t] += a; return true;
    }
}

contract LP {
    address public pool;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    constructor() { pool = msg.sender; }
    function mint(address t, uint256 a) external { require(msg.sender == pool); balanceOf[t] += a; totalSupply += a; }
    function burn(address f, uint256 a) external { require(msg.sender == pool); balanceOf[f] -= a; totalSupply -= a; }
    function approve(address s, uint256 a) external returns (bool) { allowance[msg.sender][s] = a; return true; }
    function transfer(address t, uint256 a) external returns (bool) { balanceOf[msg.sender] -= a; balanceOf[t] += a; return true; }
    function transferFrom(address f, address t, uint256 a) external returns (bool) {
        if (allowance[f][msg.sender] != type(uint256).max) allowance[f][msg.sender] -= a;
        balanceOf[f] -= a; balanceOf[t] += a; return true;
    }
}

contract Pool {
    Token public token;
    LP public lp;
    uint256 public ethReserve;
    uint256 public tokenReserve;

    constructor(address _t) { token = Token(_t); lp = new LP(); }

    function D() public view returns (uint256) { return ethReserve + tokenReserve; }
    function get_virtual_price() public view returns (uint256) {
        uint256 s = lp.totalSupply();
        return s == 0 ? 1e18 : D() * 1e18 / s;
    }

    function add_liquidity(uint256 tokenAmt) external payable returns (uint256 minted) {
        uint256 s = lp.totalSupply();
        minted = s == 0 ? msg.value + tokenAmt : s * msg.value / ethReserve;
        ethReserve += msg.value;
        tokenReserve += tokenAmt;
        lp.mint(msg.sender, minted);
        require(token.transferFrom(msg.sender, address(this), tokenAmt), "pull");
    }

    function remove_liquidity(uint256 amt) external {
        uint256 s = lp.totalSupply();
        uint256 ethOut = ethReserve * amt / s;
        uint256 tokenOut = tokenReserve * amt / s;
        lp.burn(msg.sender, amt);                          // supply drops first
        (bool ok, ) = msg.sender.call{value: ethOut}("");  // <-- reentrancy window: vp inflated
        require(ok, "eth");
        ethReserve -= ethOut;                              // reserves reduced only after the callback
        tokenReserve -= tokenOut;
        require(token.transfer(msg.sender, tokenOut), "send");
    }

    receive() external payable {}
}

contract LendingVault {
    Token public token;
    Pool public pool;
    LP public lp;
    uint256 public cf;   // collateral factor, 1e18
    mapping(address => uint256) public collateral;
    mapping(address => uint256) public debt;

    constructor(address _t, address _p, uint256 _cf) {
        token = Token(_t); pool = Pool(payable(_p)); lp = pool.lp(); cf = _cf;
    }

    function depositCollateral(uint256 amt) external {
        collateral[msg.sender] += amt;
        require(lp.transferFrom(msg.sender, address(this), amt), "pull");
    }

    function borrow(uint256 amt) external {
        debt[msg.sender] += amt;
        uint256 limit = collateral[msg.sender] * pool.get_virtual_price() / 1e18 * cf / 1e18;
        require(debt[msg.sender] <= limit, "undercollateralized");
        require(token.transfer(msg.sender, amt), "send");
    }
}
