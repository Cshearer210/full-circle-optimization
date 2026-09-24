"""Real behavioural tests for the safe fix engine: isolated-clone dry run, verify-both-directions,
rollback on regression, single-writer conflict handling, and the conservative defaults (dry_run and
require_corroborated both default True -- the whole safety story).
"""
from __future__ import annotations

import os

import pytest

from fullcircle import fixer
from fullcircle.fixer import _diff, _snapshot, apply_fixes
from fullcircle.finding import Finding, triangulate


def marker_finder(root):
    """A finding = any file containing DEADCANARY, corroborated (two methods), keyed by path."""
    out = []
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__"}]
        for f in fs:
            p = os.path.join(dp, f)
            try:
                txt = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if "DEADCANARY" in txt:
                rel = os.path.relpath(p, root)
                for m in ("m1", "m2"):
                    out.append(Finding("test", "test-cannot-fail", rel, signal="marker",
                                       method=m, confidence=0.8, both_directions_proven=True,
                                       extra={"id_key": "dc:" + rel}))
    return triangulate(out)


def good_provider(t, work):
    p = os.path.join(work, t.location)
    open(p, "w").write(open(p).read().replace("DEADCANARY", "real_assert()"))
    return True


@pytest.fixture
def bad_repo(tmp_path):
    root = str(tmp_path / "r")
    os.makedirs(root)
    open(os.path.join(root, "bad.py"), "w").write("# DEADCANARY here\nx = 1\n")
    return root


# ---------------------------------------------------------------- _snapshot / _diff
def test_snapshot_reads_files_and_skips_vcs(tmp_path):
    root = str(tmp_path)
    open(os.path.join(root, "a.py"), "w").write("hello")
    os.makedirs(os.path.join(root, ".git"))
    open(os.path.join(root, ".git", "x"), "w").write("nope")
    snap = _snapshot(root)
    assert snap["a.py"] == b"hello"
    assert not any(".git" in k for k in snap)


def test_diff_reports_changed_added_and_deleted():
    before = {"keep.py": b"1", "gone.py": b"2", "edit.py": b"a"}
    after = {"keep.py": b"1", "edit.py": b"b", "new.py": b"z"}
    changed, deleted = _diff(before, after)
    assert changed == {"edit.py": b"b", "new.py": b"z"}
    assert deleted == ["gone.py"]


# ---------------------------------------------------------------- defaults (safety)
def test_dry_run_defaults_true_and_does_not_write(bad_repo):
    rep = apply_fixes(bad_repo, marker_finder(bad_repo), good_provider, marker_finder)  # no kwargs
    assert rep["dry_run"] is True
    assert "DEADCANARY" in open(os.path.join(bad_repo, "bad.py")).read()
    assert len(rep["verified"]) == 1


def test_require_corroborated_default_excludes_single_method(tmp_path):
    root = str(tmp_path / "r")
    os.makedirs(root)
    open(os.path.join(root, "bad.py"), "w").write("# DEADCANARY y\n")
    single = triangulate([Finding("test", "test-cannot-fail", "bad.py", signal="marker",
                                  method="only1", confidence=0.9, both_directions_proven=True,
                                  extra={"id_key": "dc:bad.py"})])
    assert single[0].trust == "single-method"
    rep = apply_fixes(root, single, good_provider, marker_finder, dry_run=True)
    assert rep["attempted"] == 0


def test_require_corroborated_default_excludes_multi_method(tmp_path):
    root = str(tmp_path / "r")
    os.makedirs(root)
    open(os.path.join(root, "bad.py"), "w").write("# DEADCANARY z\n")
    multi = triangulate([
        Finding("test", "test-cannot-fail", "bad.py", signal="m", method="m1",
                confidence=0.8, both_directions_proven=False, extra={"id_key": "dc:bad.py"}),
        Finding("test", "test-cannot-fail", "bad.py", signal="m", method="m2",
                confidence=0.8, both_directions_proven=False, extra={"id_key": "dc:bad.py"}),
    ])
    assert multi[0].trust == "multi-method"
    rep = apply_fixes(root, multi, good_provider, marker_finder, dry_run=True)
    assert rep["attempted"] == 0


def test_min_confidence_filters_low_confidence_findings(tmp_path):
    root = str(tmp_path / "r")
    os.makedirs(root)
    open(os.path.join(root, "bad.py"), "w").write("# DEADCANARY q\n")
    low = triangulate([
        Finding("test", "test-cannot-fail", "bad.py", signal="m", method="m1",
                confidence=0.3, both_directions_proven=True, extra={"id_key": "dc:bad.py"}),
        Finding("test", "test-cannot-fail", "bad.py", signal="m", method="m2",
                confidence=0.3, both_directions_proven=True, extra={"id_key": "dc:bad.py"}),
    ])
    rep = apply_fixes(root, low, good_provider, marker_finder, dry_run=True, min_confidence=0.6)
    assert rep["attempted"] == 0


# ---------------------------------------------------------------- happy path
def test_wet_run_applies_the_fix(bad_repo):
    rep = apply_fixes(bad_repo, marker_finder(bad_repo), good_provider, marker_finder, dry_run=False)
    assert len(rep["applied"]) == 1
    assert "DEADCANARY" not in open(os.path.join(bad_repo, "bad.py")).read()
    assert marker_finder(bad_repo) == []


def test_dry_run_message_reports_verified_count(bad_repo):
    rep = apply_fixes(bad_repo, marker_finder(bad_repo), good_provider, marker_finder, dry_run=True)
    assert "1 verified fix" in rep["message"]


# ---------------------------------------------------------------- rollback
def test_fix_that_introduces_a_new_finding_is_rolled_back(tmp_path):
    root = str(tmp_path / "r")
    os.makedirs(root)
    open(os.path.join(root, "bad.py"), "w").write("# DEADCANARY one\n")

    def introduces(t, work):
        open(os.path.join(work, t.location), "w").write("x = 1\n")           # removes this one
        open(os.path.join(work, "new.py"), "w").write("# DEADCANARY two\n")  # ...adds another
        return True

    rep = apply_fixes(root, marker_finder(root), introduces, marker_finder, dry_run=False)
    assert len(rep["rolled_back"]) == 1
    assert rep["applied"] == []
    assert "DEADCANARY" in open(os.path.join(root, "bad.py")).read()
    assert not os.path.exists(os.path.join(root, "new.py"))


def test_fix_that_does_not_remove_the_finding_is_rolled_back(bad_repo):
    def noop(t, work):
        return True  # claims applied but changes nothing -> finding still present

    rep = apply_fixes(bad_repo, marker_finder(bad_repo), noop, marker_finder, dry_run=False)
    assert len(rep["rolled_back"]) == 1
    assert any(r[2] == "fix did not remove the finding" for r in rep["rolled_back"])


def test_provider_that_raises_is_recorded_as_patch_error(bad_repo):
    def boom(t, work):
        raise RuntimeError("kaboom")

    rep = apply_fixes(bad_repo, marker_finder(bad_repo), boom, marker_finder, dry_run=False)
    assert any(r[1] == "patch-error" for r in rep["results"])
    assert rep["applied"] == []


def test_provider_returning_false_is_no_patch(bad_repo):
    def nochange(t, work):
        return False

    rep = apply_fixes(bad_repo, marker_finder(bad_repo), nochange, marker_finder, dry_run=False)
    assert any(r[1] == "no-patch" for r in rep["results"])


# ---------------------------------------------------------------- single-writer merge
def test_conflicting_same_file_fixes_only_one_wins(tmp_path):
    root = str(tmp_path / "r")
    os.makedirs(root)
    open(os.path.join(root, "a.py"), "w").write("# DEADCANARY a\n")
    open(os.path.join(root, "b.py"), "w").write("# DEADCANARY b\n")

    def mk(loc, conf):
        return triangulate([
            Finding("test", "test-cannot-fail", loc, signal="m", method="m1",
                    confidence=conf, both_directions_proven=True, extra={"id_key": "dc:" + loc}),
            Finding("test", "test-cannot-fail", loc, signal="m", method="m2",
                    confidence=conf, both_directions_proven=True, extra={"id_key": "dc:" + loc}),
        ])[0]

    hi, lo = mk("a.py", 0.95), mk("b.py", 0.70)

    def provider(t, work):
        open(os.path.join(work, t.location), "w").write("clean\n")
        tag = "A" if t.location == "a.py" else "B"
        open(os.path.join(work, "shared.txt"), "w").write("shared-" + tag + "\n")  # different content
        return True

    rep = apply_fixes(root, [lo, hi], provider, marker_finder, dry_run=False)
    assert len(rep["applied"]) == 1
    assert hi.identity in rep["applied"]                       # higher confidence wins
    assert any(i == lo.identity for i, _ in rep["conflicts"])  # lower is held back


def test_fix_creating_a_nested_file_makes_parent_dir(bad_repo):
    def provider(t, work):
        good_provider(t, work)
        os.makedirs(os.path.join(work, "newdir"), exist_ok=True)
        open(os.path.join(work, "newdir", "created.py"), "w").write("# added\n")
        return True

    apply_fixes(bad_repo, marker_finder(bad_repo), provider, marker_finder, dry_run=False)
    assert os.path.exists(os.path.join(bad_repo, "newdir", "created.py"))


def test_report_counts_considered_and_attempted(bad_repo):
    findings = marker_finder(bad_repo)
    rep = apply_fixes(bad_repo, findings, good_provider, marker_finder, dry_run=True)
    assert rep["considered"] == len(findings)
    assert rep["attempted"] == 1


def test_module_selftest_passes():
    assert fixer.selftest() == 0
