#!/usr/bin/env python3
"""Isolated execution-scenario runner: generate -> anvil -> agent -> grade.

Every attempt gets a fresh temporary workspace and a dedicated anvil on a
unique port and generated chain id. The agent sees only the workspace and the
local RPC; hidden grading runs from OUT HERE, against chain state. Upstream
secrets are scrubbed from the agent env, and redacted from anything saved.

Usage:
  python3 harness/run_scenario.py --scenario tx-eip1559-transfer --seed 1 --reference
  python3 harness/run_scenario.py --scenario tx-eip1559-transfer --seed 2 --fixture broken_legacy
  python3 harness/run_scenario.py --scenario tx-eip1559-transfer --seed 1 \
      --name fable --agent-cmd 'claude -p --model fable' --save
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from harness.ethrpc import rpc  # noqa: E402
from harness.rpc_policy import redact  # noqa: E402

SCENARIOS = HERE / "scenarios"
RESULTS = HERE / "exec-results"

# the agent must not inherit harness credentials or nested-claude flags
SCRUB = re.compile(r"^(CLAUDECODE$|CLAUDE_CODE_|ANTHROPIC_API_KEY$|CLAUDE_AGENT_|"
                   r"ALCHEMY_API_KEY$|BANKR_API_KEY$|OPENAI_API_KEY$)")


def load_scenario(name):
    sdir = SCENARIOS / name
    spec = json.loads((sdir / "scenario.json").read_text())
    modspec = importlib.util.spec_from_file_location(f"scenario_{name}", sdir / "scenario.py")
    mod = importlib.util.module_from_spec(modspec)
    modspec.loader.exec_module(mod)
    return sdir, spec, mod


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_anvil(chain_id, base_fee, fork=None):
    """fork = {"chain": "mainnet", "block": N} pins a mainnet fork. The
    upstream URL (with its key) lives only inside a loopback proxy — anvil's
    argv, visible to the agent via ps, sees 127.0.0.1."""
    proxy = None
    args = ["--chain-id", str(chain_id)]
    if not fork:
        # forks keep the pinned block's real base fee; forcing one makes
        # anvil advertise a price the pending block doesn't honor
        args += ["--block-base-fee-per-gas", str(base_fee)]
    if fork:
        from harness.fork_proxy import start_proxy
        from harness.rpc_policy import alchemy_url, assert_upstream_allowed
        upstream = alchemy_url(fork.get("chain", "mainnet"))
        assert_upstream_allowed(upstream)
        proxy, local = start_proxy(upstream)
        args += ["--fork-url", local, "--fork-block-number", str(fork["block"])]
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        ["anvil", "--port", str(port), *args, "--silent"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(240 if fork else 60):
        try:
            got = int(rpc(url, "eth_chainId", timeout=2), 16)
            if got != chain_id:
                proc.terminate()
                raise RuntimeError(f"anvil came up with chain id {got}, wanted {chain_id}")
            return proc, url, proxy
        except (OSError, RuntimeError, ValueError):
            if proc.poll() is not None:
                if proxy:
                    proxy.shutdown()
                raise RuntimeError("anvil exited during startup") from None
            time.sleep(0.25)
    proc.terminate()
    if proxy:
        proxy.shutdown()
    raise RuntimeError("anvil never became ready")


def run_attempt(scenario, seed, agent_cmd, name="", save=False, timeout=None, rep=0):
    sdir, spec, mod = load_scenario(scenario)
    inst = mod.generate(seed)
    timeout = timeout or spec.get("timeout_seconds", 900)

    workspace = Path(tempfile.mkdtemp(prefix=f"eth-evals-{scenario}-s{seed}-"))
    anvil = proxy = None
    t0 = time.time()
    try:
        anvil, rpc_url, proxy = start_anvil(inst["chain_id"], inst.get("base_fee_wei", 10**9),
                                            fork=inst.get("fork"))
        mod.setup_chain(inst, rpc_url)
        files = mod.workspace_files(inst, rpc_url)
        for fname, content in files.items():
            dest = workspace / fname
            dest.parent.mkdir(parents=True, exist_ok=True)   # nested files (src/, test/)
            dest.write_text(content)

        env = {k: v for k, v in os.environ.items() if not SCRUB.match(k)}
        prompt = files.get("prompt.md", "")
        agent = subprocess.run(agent_cmd, shell=True, cwd=str(workspace),
                               input=prompt, capture_output=True, text=True,
                               timeout=timeout, env=env)
        agent_meta = {"cmd": agent_cmd, "exit": agent.returncode,
                      "elapsed_s": round(time.time() - t0, 1)}

        milestones, violations = mod.grade(inst, workspace, rpc_url)
        points = spec["grading"]["milestones"]
        score = sum(points[k] for k, v in milestones.items() if v["pass"])
        max_score = sum(points.values())
        for k in milestones:
            milestones[k]["points"] = points[k] if milestones[k]["pass"] else 0
            milestones[k]["max"] = points[k]

        result = {
            "scenario": scenario, "seed": seed, "name": name or "unnamed",
            "score": score, "max_score": max_score,
            "milestones": milestones, "safety_violations": violations,
            "agent": agent_meta, "rep": rep,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if save:
            RESULTS.mkdir(exist_ok=True)
            bundle = RESULTS / (f"{name or 'unnamed'}-{scenario}-seed{seed}"
                                + (f"-r{rep}" if rep else ""))
            bundle.mkdir(parents=True, exist_ok=True)
            (bundle / "result.json").write_text(redact(json.dumps(result, indent=1)))
            (bundle / "agent.stdout").write_text(redact(agent.stdout or ""))
            (bundle / "agent.stderr").write_text(redact(agent.stderr or ""))
            sub = workspace / "submission.json"
            if sub.exists():
                (bundle / "submission.json").write_text(redact(sub.read_text()))
            result["bundle"] = str(bundle.relative_to(HERE))
        return result
    finally:
        if anvil:
            anvil.terminate()
            try:
                anvil.wait(timeout=10)
            except subprocess.TimeoutExpired:
                anvil.kill()
        if proxy:
            proxy.shutdown()
        shutil.rmtree(workspace, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seeds", help="comma list, e.g. 1,2,3 (overrides --seed)")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run each seed N times; one score is not a pass rate")
    ap.add_argument("--name", default="")
    ap.add_argument("--agent-cmd")
    ap.add_argument("--reference", action="store_true",
                    help="run the scenario's bundled reference solution")
    ap.add_argument("--fixture", help="run a bundled broken-solution fixture by name")
    ap.add_argument("--save", action="store_true", help="save a redacted result bundle")
    args = ap.parse_args()

    sdir = SCENARIOS / args.scenario
    if args.reference:
        cmd, name = f"python3 {sdir / 'reference.py'}", args.name or "reference"
    elif args.fixture:
        cmd = f"python3 {sdir / 'fixtures' / (args.fixture + '.py')}"
        name = args.name or args.fixture
    elif args.agent_cmd:
        cmd, name = args.agent_cmd, args.name
        if not name:
            sys.exit("--name is required with --agent-cmd")
    else:
        sys.exit("need --agent-cmd, --reference, or --fixture")

    seeds = [int(x) for x in args.seeds.split(",")] if args.seeds else [args.seed]
    runs = []
    for seed in seeds:
        for i in range(args.repeat):
            rep = i + 1 if args.repeat > 1 else 0
            r = run_attempt(args.scenario, seed, cmd, name=name, save=args.save, rep=rep)
            runs.append(r)
            if len(seeds) * args.repeat == 1:
                print(json.dumps(r, indent=1))
            print(f"\n{r['name']} on {r['scenario']} seed {r['seed']}"
                  + (f" rep {rep}" if rep else "") + f": {r['score']}/{r['max_score']}"
                  + (f"  SAFETY VIOLATIONS: {r['safety_violations']}" if r["safety_violations"] else ""),
                  flush=True)
    perfect = [r for r in runs if r["score"] == r["max_score"] and not r["safety_violations"]]
    if len(runs) > 1:
        mean = sum(r["score"] for r in runs) / len(runs)
        print(f"\n{name} on {args.scenario}: {len(perfect)}/{len(runs)} perfect "
              f"(pass rate {len(perfect)/len(runs):.0%}, mean score {mean:.0f})")
    return 0 if len(perfect) == len(runs) else 1


if __name__ == "__main__":
    sys.exit(main())
