"""repo-repair: generation + hidden grading.

Agent-in-workspace Building task. The workspace is a Foundry project whose
`src/Sale.sol` has five planted defects: a compile error, a decimal-scaling
bug, a missing oracle-staleness check, missing proceeds accounting, and a
missing owner check. The agent must make it build and satisfy SPEC.md.

Grading builds a throwaway project OUTSIDE the workspace (agent's src + a
hidden functional suite) and runs `forge test`. Each behavioral test is a
milestone; the EVM decides. No forge-std — tests declare `Vm` inline.
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
WS = HERE / "workspace"
HID = HERE / "hidden"

FOUNDRY_TOML = (
    "[profile.default]\n"
    'src = "src"\ntest = "test"\nout = "out"\n'
    'solc = "0.8.28"\nevm_version = "cancun"\noptimizer = true\n'
)

# hidden-test function -> (milestone, points)
TEST_MILESTONES = {
    "test_cost_correct": ("cost_correct", 25),
    "test_stale_reverts": ("stale_reverts", 20),
    "test_proceeds": ("proceeds_accounting", 20),
    "test_owner_only": ("owner_only_withdraw", 20),
}


def generate(seed):
    rng = random.Random(f"repo-repair-{seed}")
    inst = {
        "seed": seed,
        "chain_id": 34_000_000 + rng.randrange(1_000_000),
        "base_fee_wei": 10**9,
        "price": rng.randrange(500, 4000) * 10**8,          # 8-dec USD, whole dollars
        "amt": (rng.randrange(1, 20) * 10**18) | 1,          # 18-dec product units
        "max_age": rng.choice([600, 1800, 3600]),
    }
    return inst


def setup_chain(inst, rpc_url):
    return


def workspace_files(inst, rpc_url):
    return {
        "prompt.md": (HERE / "prompt.md").read_text(),
        "SPEC.md": (WS / "SPEC.md").read_text(),
        "foundry.toml": FOUNDRY_TOML,
        "src/Sale.sol": (WS / "Sale.sol").read_text(),
        "src/Mocks.sol": (WS / "Mocks.sol").read_text(),
        "src/Registry.sol": (WS / "Registry.sol").read_text(),
    }


def _fill(text, inst):
    return (text.replace("__PRICE__", str(inst["price"]))
                .replace("__AMT__", str(inst["amt"]))
                .replace("__MAXAGE__", str(inst["max_age"])))


def _run_forge(sale_src, mocks_src, test_src):
    """Build {agent Sale, mocks, functional test} and run. Returns
    (compiled, {test_fn: passed})."""
    proj = Path(tempfile.mkdtemp(prefix="repo-repair-grade-"))
    try:
        (proj / "src").mkdir()
        (proj / "test").mkdir()
        (proj / "foundry.toml").write_text(FOUNDRY_TOML)
        (proj / "src" / "Sale.sol").write_text(sale_src)
        (proj / "src" / "Mocks.sol").write_text(mocks_src)
        (proj / "test" / "Functional.t.sol").write_text(test_src)
        out = subprocess.run(
            ["forge", "test", "--match-path", "test/Functional.t.sol", "--json"],
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
    violations = []

    def m(name, ok, detail=""):
        ms[name] = {"pass": bool(ok), "detail": detail}

    sale = Path(workspace) / "src" / "Sale.sol"
    if not sale.exists():
        m("builds", False, "src/Sale.sol missing")
        for _, (name, _pts) in TEST_MILESTONES.items():
            m(name, False, "no submission")
        return ms, violations

    mocks = (WS / "Mocks.sol").read_text()
    functional = _fill((HID / "Functional.t.sol").read_text(), inst)
    compiled, results = _run_forge(sale.read_text(), mocks, functional)

    m("builds", compiled, "src/Sale.sol did not compile against the hidden suite")
    for fn, (name, _pts) in TEST_MILESTONES.items():
        m(name, compiled and results.get(fn, False),
          "" if compiled else "did not compile")

    return ms, violations
