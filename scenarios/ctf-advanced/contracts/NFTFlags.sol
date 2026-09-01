//SPDX-License-Identifier: MIT
pragma solidity >=0.8.0 <0.9.0;

/// Minimal reproduction of the BuidlGuidl CTF flag registry — the
/// load-bearing behavior only (allow-list, enable gate, team-first gate,
/// no double-mint, a real tokenIdCounter, the FlagMinted event). The ERC-721
/// / SVG / gold-token parts of the original are cosmetic and dropped;
/// grading reads `hasMinted`.
contract NFTFlags {
    address public owner;
    mapping(address => bool) public allowedMinters;
    uint256 public tokenIdCounter;
    mapping(uint256 => uint256) public tokenIdToChallengeId;
    mapping(address => mapping(uint256 => bool)) public hasMinted;
    bool public enabled;

    event FlagMinted(address indexed minter, uint256 indexed tokenId, uint256 indexed challengeId);

    constructor(address _owner) {
        owner = _owner;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    function mint(address _recipient, uint256 _challengeId) external {
        require(allowedMinters[msg.sender], "Not allowed to mint");
        require(enabled, "Minting is not enabled");
        require(_challengeId == 1 || hasMinted[_recipient][1], "Team address is not registered");
        require(!hasMinted[_recipient][_challengeId], "Team address has already minted for this challenge");

        tokenIdCounter++;
        tokenIdToChallengeId[tokenIdCounter] = _challengeId;
        hasMinted[_recipient][_challengeId] = true;
        emit FlagMinted(_recipient, tokenIdCounter, _challengeId);
    }

    function addAllowedMinter(address minter) external onlyOwner {
        allowedMinters[minter] = true;
    }

    function enable() external onlyOwner {
        enabled = true;
    }
}
