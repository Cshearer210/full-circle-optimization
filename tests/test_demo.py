"""Real behavioural tests for the runnable example. `demo.main()` builds a throwaway target, runs
the REAL pipeline over it (nothing mocked), writes SARIF, and returns 0. We assert the planted
defects are actually found and the control is left alone.
"""
from __future__ import annotations

import os

# import the example module by file path (examples/ is not a package)
import importlib.util

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "fco_demo", os.path.join(REPO_ROOT, "examples", "demo.py"))
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)


def test_build_target_plants_the_documented_defects(tmp_path):
    root = str(tmp_path)
    demo.build_target(root)
    assert os.path.exists(os.path.join(root, "core", "handler_a.py"))
    assert os.path.exists(os.path.join(root, "legacy", "handler_b.py"))
    assert os.path.exists(os.path.join(root, "conf", "a.py"))
    assert os.path.exists(os.path.join(root, "core", "orphan.py"))
    assert os.path.exists(os.path.join(root, "core", "pay.py"))
    assert os.path.exists(os.path.join(root, "core", "util.py"))


def test_built_target_yields_the_expected_findings(tmp_path):
    from fullcircle import orchestrator
    root = str(tmp_path)
    demo.build_target(root)
    rep = orchestrator.run(root, orchestrator._wire_real_finders())
    got = {t.defect_class for t in rep["findings"]}
    assert "function-unwired" in got
    assert "stub-implementation" in got
    assert "conflicting-definition" in got
    assert "second-door-duplicate" in got
    # the clean control util.py must not be flagged unwired
    assert not any("util.py" in t.location and t.defect_class == "function-unwired"
                   for t in rep["findings"])


def test_demo_main_runs_and_returns_zero(capsys):
    rc = demo.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "full-circle-optimization demo" in out
    assert "SARIF" in out


def test_demo_writer_helper(tmp_path):
    demo._w(str(tmp_path), "a/b/c.py", "x = 1\n")
    p = os.path.join(str(tmp_path), "a", "b", "c.py")
    assert os.path.exists(p)
    assert open(p).read() == "x = 1\n"
