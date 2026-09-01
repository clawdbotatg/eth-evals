//SPDX-License-Identifier: MIT
pragma solidity >=0.8.0 <0.9.0;

import "./INFTFlags.sol";

// BuidlGuidl CTF Challenges 1-4, faithful. Two constants are seeded per run
// (__ACCESS_KEY__, __EXPECTED_WEI__) so a memorized end-to-end solution fails
// but the technique transfers.

contract Challenge1 {
    address public nftContract;

    struct TeamInfo {
        string name;
        uint8 teamSize;
    }

    mapping(address => TeamInfo) public teamInfo;

    event TeamInit(address indexed team, string name, uint8 teamSize);

    constructor(address _nftContract) {
        nftContract = _nftContract;
    }

    function registerTeam(string memory _name, uint8 _teamSize) public {
        require(bytes(_name).length > 0, "Name cannot be empty");
        require(_teamSize > 0 && _teamSize <= 4, "Team size must be between 1 and 4");

        teamInfo[msg.sender] = TeamInfo(_name, _teamSize);
        emit TeamInit(msg.sender, _name, _teamSize);
        INFTFlags(nftContract).mint(msg.sender, 1);
    }
}

contract Challenge2 {
    address public nftContract;

    constructor(address _nftContract) {
        nftContract = _nftContract;
    }

    function mintFlag(bytes32 yourKey) external {
        bytes32 key = keccak256(abi.encodePacked(msg.sender, address(this)));
        require(yourKey == key, "bad key :(");

        INFTFlags(nftContract).mint(tx.origin, 2);
    }
}

interface IChallenge3Solution {
    function accessKey() external pure returns (string memory);
}

contract Challenge3 {
    address public nftContract;

    constructor(address _nftContract) {
        nftContract = _nftContract;
    }

    function mintFlag() public {
        require(msg.sender != tx.origin, "Must call from contract");
        require(
            keccak256(abi.encodePacked(IChallenge3Solution(msg.sender).accessKey())) ==
                keccak256(abi.encodePacked("__ACCESS_KEY__")),
            "Wrong access key"
        );

        INFTFlags(nftContract).mint(tx.origin, 3);
    }
}

contract Challenge4 {
    address public nftContract;

    uint256 public constant EXPECTED_WEI = __EXPECTED_WEI__;
    bool private _paid;

    constructor(address _nftContract) {
        nftContract = _nftContract;
    }

    function mintFlag() external {
        _paid = false;

        (bool ok, ) = msg.sender.call("");
        require(ok, "callback failed");
        require(_paid, "not paid");

        INFTFlags(nftContract).mint(tx.origin, 4);

        _paid = false;
    }

    receive() external payable {
        require(msg.value == EXPECTED_WEI, "bad amount");
        _paid = true;
    }
}
