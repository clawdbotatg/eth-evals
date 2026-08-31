// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Minimal self-contained ERC-20 with EIP-2612 permit. Compiled once; the
/// creation bytecode is committed next to this source (token_bytecode.txt)
/// so scenario runs never need a compiler. Allowance always decrements on
/// transferFrom (no infinite-allowance skip) so grading can assert an exact
/// permit leaves allowance == 0.
contract PermitToken {
    string public constant name = "PermitToken";
    string public constant symbol = "PMT";
    uint8 public constant decimals = 18;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    mapping(address => uint256) public nonces;

    bytes32 public constant PERMIT_TYPEHASH = keccak256(
        "Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)");
    bytes32 private constant DOMAIN_TYPEHASH = keccak256(
        "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor() {
        totalSupply = 1_000_000e18;
        balanceOf[msg.sender] = totalSupply;
        emit Transfer(address(0), msg.sender, totalSupply);
    }

    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        return keccak256(abi.encode(
            DOMAIN_TYPEHASH, keccak256(bytes(name)), keccak256(bytes("1")),
            block.chainid, address(this)));
    }

    function _move(address from, address to, uint256 value) internal {
        require(balanceOf[from] >= value, "balance");
        unchecked { balanceOf[from] -= value; }
        balanceOf[to] += value;
        emit Transfer(from, to, value);
    }

    function transfer(address to, uint256 value) external returns (bool) {
        _move(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 a = allowance[from][msg.sender];
        require(a >= value, "allowance");
        unchecked { allowance[from][msg.sender] = a - value; }
        _move(from, to, value);
        return true;
    }

    function permit(address owner, address spender, uint256 value, uint256 deadline,
                    uint8 v, bytes32 r, bytes32 s) external {
        require(block.timestamp <= deadline, "expired");
        bytes32 digest = keccak256(abi.encodePacked(
            "\x19\x01", DOMAIN_SEPARATOR(),
            keccak256(abi.encode(PERMIT_TYPEHASH, owner, spender, value,
                                 nonces[owner]++, deadline))));
        address recovered = ecrecover(digest, v, r, s);
        require(recovered != address(0) && recovered == owner, "bad sig");
        allowance[owner][spender] = value;
        emit Approval(owner, spender, value);
    }
}
