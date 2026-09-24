"""Real end-to-end tests of the command-line entry points, run as subprocesses exactly as a user
would. These exercise the `__main__` blocks: the selftest dispatch, running a finder over a target,
SARIF output to a file, and the aggregate run_all_tests.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cli(*args, cwd=REPO_ROOT):
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True,
                          env=env, timeout=300)


@pytest.fixture
def planted(tmp_path):
    root = str(tmp_path / "target")
    os.makedirs(root)
    open(os.path.join(root, "orphan.py"), "w").write("def zzq_dead():\n    return 1\n")
    open(os.path.join(root, "pay.py"), "w").write(
        "def settle(x):\n    raise NotImplementedError\nsettle(1)\n")
    return root


# ---------------------------------------------------------------- selftest dispatch
@pytest.mark.parametrize("mod", [
    "fullcircle/finding.py",
    "fullcircle/concepts.py",
    "fullcircle/structural.py",
    "fullcircle/drift_guard.py",
    "fullcircle/fixer.py",
    "fullcircle/patches.py",
    "fullcircle/orchestrator.py",
    "fullcircle/_optional.py",
])
def test_module_selftest_cli_exits_zero(mod):
    r = cli(mod, "--selftest")
    assert r.returncode == 0, r.stdout + r.stderr


def test_orchestrator_no_args_runs_selftest():
    # `python orchestrator.py` with no target runs the selftest (exit 0).
    r = cli("fullcircle/orchestrator.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "selftest" in r.stdout


# ---------------------------------------------------------------- structural finder CLI
def test_structural_cli_reports_findings_on_a_target(planted):
    r = cli("fullcircle/structural.py", planted)
    assert "finding(s)" in r.stdout
    assert r.returncode == 1  # findings present -> nonzero


def test_structural_cli_writes_sarif(planted, tmp_path):
    out = str(tmp_path / "findings.sarif")
    r = cli("fullcircle/structural.py", planted, "--sarif", out)
    assert "SARIF written" in r.stdout
    assert os.path.exists(out)
    doc = json.load(open(out))
    assert doc["version"] == "2.1.0"


# ---------------------------------------------------------------- orchestrator CLI
def test_orchestrator_cli_over_a_target(planted):
    r = cli("fullcircle/orchestrator.py", planted)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "round 1" in r.stdout


def test_orchestrator_cli_sarif_output(planted, tmp_path):
    out = str(tmp_path / "agg.sarif")
    r = cli("fullcircle/orchestrator.py", planted, "--sarif", out)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.exists(out)
    assert json.load(open(out))["version"] == "2.1.0"


# ---------------------------------------------------------------- demo + aggregate
def test_demo_cli_runs():
    r = cli("examples/demo.py")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "demo" in r.stdout.lower()


def test_run_all_tests_exits_zero():
    r = cli("run_all_tests.py")
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "REQUIRED selftests" in r.stdout
