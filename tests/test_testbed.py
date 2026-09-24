"""Real behavioural tests for the fixed test bed: it plants known defects + clean controls, scores
catch rate against ground truth, and repeats with every symbol renamed (the label-independence
proof). Assertions hold whether or not the optional companion is installed -- silent classes are
either caught (companion present) or skipped (absent), never counted as a real miss.
"""
from __future__ import annotations

import os

from fullcircle import testbed
from fullcircle.testbed import (
    _CONTROL_MARKERS,
    _rename_everything,
    gen_system,
    get_findings,
    run_levels,
    score,
)

# structural classes must be caught regardless of the companion.
STRUCTURAL = {"second-door-duplicate", "conflicting-definition", "function-unwired",
              "stub-implementation"}


def test_gen_system_plants_expected_ground_truth(tmp_path):
    ground = gen_system(str(tmp_path), "basic")
    classes = {c for c, _ in ground}
    for c in ("test-cannot-fail", "second-door-duplicate", "conflicting-definition",
              "function-unwired", "labeled-gate-that-cannot-fail", "swallowed-exception",
              "stub-implementation"):
        assert c in classes
    # it actually wrote files
    assert os.path.exists(os.path.join(str(tmp_path), "pkg", "orphan.py"))


def test_score_catches_structural_classes_with_no_false_positives(tmp_path):
    root = str(tmp_path)
    ground = gen_system(root, "basic")
    sc = score(root, ground)
    caught_classes = {c for c, _ in sc["caught"]}
    assert STRUCTURAL <= caught_classes
    assert sc["false_positives"] == []


def test_get_findings_returns_triangulated(tmp_path):
    root = str(tmp_path)
    gen_system(root, "basic")
    tri = get_findings(root)
    assert isinstance(tri, list)
    assert all(hasattr(t, "trust") for t in tri)


def test_rename_holds_the_catch_rate(tmp_path):
    root = str(tmp_path)
    ground = gen_system(root, "basic")
    ground = _rename_everything(root, ground)
    sc = score(root, ground)
    got = {c for c, _ in sc["caught"]}
    # the two symbol-renamed classes must still be caught (behaviour, not names)
    assert "second-door-duplicate" in got
    assert "function-unwired" in got
    # and the orphan marker was updated to the new name
    assert ("function-unwired", "wpZeta") in ground


def test_rename_everything_returns_none_when_ground_is_none(tmp_path):
    root = str(tmp_path)
    gen_system(root, "basic")
    assert _rename_everything(root, None) is None


def test_run_levels_all_levels_clean(tmp_path, monkeypatch):
    # keep it to the basic level for speed but exercise both rename directions.
    rep = run_levels(levels=("basic",))
    assert set(rep) == {"basic", "basic+renamed"}
    for key, r in rep.items():
        assert r["missed"] == [], "%s missed %s" % (key, r["missed"])
        assert r["false_positives"] == [], "%s FP %s" % (key, r["false_positives"])
        assert r["caught"] >= len(STRUCTURAL)


def test_control_markers_include_the_clean_fixtures():
    for m in ("test_good", "validate_token", "helper", "compute"):
        assert m in _CONTROL_MARKERS


def test_module_selftest_passes():
    assert testbed.selftest() == 0
