"""gas-golf: generation + hidden grading.

A quality-graded task, not a puzzle: implement `solve` correctly AND under a
gas budget. Correctness plus a loose cap is easy; the tight cap requires real
EVM optimization (calldata assembly, no bounds checks). No tool computes the
optimal implementation, so difficulty comes from skill, not obscurity, and
inputs are seeded so the answer can't be precomputed.

Grading compiles the agent's Solution against a hidden measurement suite
OUTSIDE the workspace and runs `forge test`; each milestone is one test.
"""
import json
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

HERE = Path(__file__).resolve().parent
HID = HERE / "hidden"

# caps tuned to a length-32 array under this toolchain (optimizer on, 200 runs):
# an unchecked naive Solidity loop measures ~7926 gas, hand-optimized calldata
# assembly ~6664. The optimizer already closes most of the language gap, so the
# tight cap sits just below the naive number — clearing it needs real assembly.
LOOSE_CAP = 16000     # catches only egregiously wasteful solutions
TIGHT_CAP = 7300      # naive Solidity (~7926) misses; tuned assembly (~6664) clears

FOUNDRY_TOML = (
    "[profile.default]\n"
    'src = "src"\ntest = "test"\nout = "out"\n'
    'solc = "0.8.28"\nevm_version = "cancun"\noptimizer = true\noptimizer_runs = 200\n'
)


def generate(seed):
    rng = random.Random(f"gas-golf-{seed}")
    return {
        "seed": seed,
        "chain_id": 37_000_000 + rng.randrange(1_000_000),
        "base_fee_wei": 10**9,
        "test_seed": rng.randrange(2**64),
        "loose_cap": LOOSE_CAP,
        "tight_cap": TIGHT_CAP,
    }


def setup_chain(inst, rpc_url):
    return


def workspace_files(inst, rpc_url):
    return {
        "prompt.md": (HERE / "prompt.md").read_text(),
        "SPEC.md": (HERE / "SPEC.md").read_text(),
        "foundry.toml": FOUNDRY_TOML,
        "src/Solution.sol": (HERE / "starter" / "Solution.sol").read_text(),
    }


def _measure_test(inst):
    return ((HID / "Measure.t.sol").read_text()
            .replace("__SEED__", str(inst["test_seed"]))
            .replace("__LOOSE__", str(inst["loose_cap"]))
            .replace("__TIGHT__", str(inst["tight_cap"])))


def _run_forge(solution_src, test_src):
    proj = Path(tempfile.mkdtemp(prefix="gas-golf-grade-"))
    try:
        (proj / "src").mkdir()
        (proj / "test").mkdir()
        (proj / "foundry.toml").write_text(FOUNDRY_TOML)
        (proj / "src" / "Solution.sol").write_text(solution_src)
        (proj / "test" / "Measure.t.sol").write_text(test_src)
        out = subprocess.run(
            ["forge", "test", "--match-path", "test/Measure.t.sol", "--json"],
            cwd=proj, capture_output=True, text=True, timeout=180)
        try:
            data = json.loads(out.stdout)
        except (json.JSONDecodeError, ValueError):
            return False, {}
        results = {}
        for suite in data.values():
            for fn, res in suite.get("test_results", {}).items():
                results[fn.split("(")[0]] = res.get("status") == "Success"
        return True, results
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def grade(inst, workspace, rpc_url):
    ms = {}
    sol = Path(workspace) / "src" / "Solution.sol"
    if not sol.exists():
        for n in ("compiles", "correct", "under_loose_cap", "under_tight_cap"):
            ms[n] = {"pass": False, "detail": "src/Solution.sol missing"}
        return ms, []

    compiled, res = _run_forge(sol.read_text(), _measure_test(inst))
    ms["compiles"] = {"pass": compiled,
                      "detail": "" if compiled else "Solution did not compile"}
    mapping = {
        "correct": "test_correct",
        "under_loose_cap": "test_under_loose_cap",
        "under_tight_cap": "test_under_tight_cap",
    }
    for name, fn in mapping.items():
        ok = compiled and res.get(fn, False)
        ms[name] = {"pass": ok, "detail": "" if ok else "failed or did not compile"}
    return ms, []
