"""Real behavioural tests for the companion-copy drift guard, including the three honest exit codes
(identical/none -> 0, drifted -> 1, canonical unreadable -> 2 which must never read as clean).
"""
from __future__ import annotations

import os
import shutil

from fullcircle import drift_guard
from fullcircle.drift_guard import SHARED_FILES, _companion_dirs, _rel_paths, check


def test_no_companions_is_clean():
    code, msgs = check(dirs=[])
    assert code == 0
    assert "0 companion" in msgs[0]


def test_identical_copy_is_clean(tmp_path):
    good = str(tmp_path / "good")
    os.makedirs(good)
    for fn in SHARED_FILES:
        shutil.copyfile(os.path.join(drift_guard.HERE, fn), os.path.join(good, fn))
    code, msgs = check(dirs=[good])
    assert code == 0
    assert any("identical" in m for m in msgs)


def test_drifted_copy_is_a_finding(tmp_path):
    bad = str(tmp_path / "bad")
    os.makedirs(bad)
    with open(os.path.join(bad, "finding.py"), "w") as fh:
        fh.write("# drifted\n")
    code, msgs = check(dirs=[bad])
    assert code == 1
    assert any("DRIFT" in m for m in msgs)


def test_canonical_missing_returns_unknown_not_clean(tmp_path, monkeypatch):
    # point HERE at an empty dir so the canonical copy is missing -> exit 2 (cannot tell), never 0.
    monkeypatch.setattr(drift_guard, "HERE", str(tmp_path))
    code, msgs = check(dirs=[])
    assert code == 2
    assert any("canonical" in m for m in msgs)


def test_companion_dirs_parses_env(monkeypatch):
    monkeypatch.setenv("COMPANION_DIRS", os.pathsep.join(["/a", "/b", ""]))
    assert _companion_dirs() == ["/a", "/b"]


def test_companion_dirs_empty_env(monkeypatch):
    monkeypatch.delenv("COMPANION_DIRS", raising=False)
    assert _companion_dirs() == []


def test_rel_paths_joins_filename_onto_each_dir():
    assert _rel_paths("finding.py", ["/x", "/y"]) == ["/x/finding.py", "/y/finding.py"]


def test_shared_files_lists_both_contract_files():
    assert "finding.py" in SHARED_FILES
    assert "concepts.py" in SHARED_FILES


def test_mixed_good_and_bad_reports_drift(tmp_path):
    good, bad = str(tmp_path / "g"), str(tmp_path / "b")
    os.makedirs(good)
    os.makedirs(bad)
    shutil.copyfile(os.path.join(drift_guard.HERE, "finding.py"), os.path.join(good, "finding.py"))
    with open(os.path.join(bad, "finding.py"), "w") as fh:
        fh.write("# drifted\n")
    code, _ = check(dirs=[good, bad])
    assert code == 1


def test_module_selftest_passes():
    assert drift_guard.selftest() == 0
