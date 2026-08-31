// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// A small name registry used elsewhere in the system. It is correct and
/// unrelated to the Sale bug — do not waste time here.
contract Registry {
    mapping(bytes32 => address) private _addrs;
    address public admin;

    constructor() {
        admin = msg.sender;
    }

    function setAddress(bytes32 key, address value) external {
        require(msg.sender == admin, "not admin");
        _addrs[key] = value;
    }

    function get(bytes32 key) external view returns (address) {
        return _addrs[key];
    }
}
