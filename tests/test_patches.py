"""Real behavioural tests for the mechanical patch providers: the only auto-fix is removal of a
CORROBORATED-unwired function, it refuses single-method leads, and it degrades safely (returns
False) on unreadable files, missing names, and unregistered defect classes.
"""
from __future__ import annotations

import ast
import os

from fullcircle import patches, structural
from fullcircle.patches import PATCH_PROVIDERS, dispatch, remove_unwired


class _Fake:
    def __init__(self, trust, location, label):
        self.trust = trust
        self.location = location
        self.findings = [type("F", (), {"ignored_label": label})()]


def test_removes_corroborated_dead_function_keeping_live_code(make_repo):
    root = make_repo({"m.py": "def used():\n    return 1\ndef caller():\n    return used()\n"
                              "def zzq_dead():\n    return 99\ncaller()\n"})
    dead = [t for t in structural.scan(root)
            if t.defect_class == "function-unwired" and t.trust == "corroborated"]
    assert dead
    from fullcircle import fixer
    rep = fixer.apply_fixes(root, dead, dispatch, structural.scan, dry_run=False)
    assert len(rep["applied"]) == 1
    src = open(os.path.join(root, "m.py")).read()
    assert "zzq_dead" not in src
    assert "def used" in src and "def caller" in src
    ast.parse(src)  # still valid Python (line endings preserved)


def test_refuses_single_method_lead(make_repo):
    root = make_repo({"n.py": "def keep_me():\n    return 1\nHANDLERS = 'keep_me'\n"
                              "def c():\n    return 2\nc()\n"})
    leads = [t for t in structural.scan(root) if t.defect_class == "function-unwired"]
    for t in leads:
        assert remove_unwired(t, root) is False
    assert "def keep_me" in open(os.path.join(root, "n.py")).read()


def test_remove_unwired_refuses_non_corroborated_trust(make_repo):
    root = make_repo({"m.py": "def zz():\n    return 1\n"})
    assert remove_unwired(_Fake("single-method", "m.py:1", "zz"), root) is False


def test_remove_unwired_false_on_unreadable_file(make_repo):
    root = make_repo({"m.py": "def zz():\n    return 1\n"})
    assert remove_unwired(_Fake("corroborated", "does_not_exist.py:1", "zz"), root) is False


def test_remove_unwired_false_when_name_absent(make_repo):
    root = make_repo({"m.py": "def zz():\n    return 1\n"})
    assert remove_unwired(_Fake("corroborated", "m.py:1", "not_here"), root) is False


def test_remove_unwired_strips_decorators_too(make_repo):
    root = make_repo({"m.py": "import functools\n@functools.cache\n"
                              "def dead():\n    return 1\nkeep = 1\n"})
    ok = remove_unwired(_Fake("corroborated", "m.py:3", "dead"), root)
    assert ok is True
    src = open(os.path.join(root, "m.py")).read()
    assert "dead" not in src
    assert "@functools.cache" not in src
    ast.parse(src)


def test_dispatch_unknown_class_returns_false(make_repo):
    root = make_repo({"m.py": "x = 1\n"})
    assert dispatch(type("T", (), {"defect_class": "no-such-class"})(), root) is False


def test_dispatch_routes_registered_class(make_repo):
    root = make_repo({"m.py": "def used():\n    return 1\ndef caller():\n    return used()\n"
                              "def zzq_dead():\n    return 9\ncaller()\n"})
    dead = next(t for t in structural.scan(root)
                if t.defect_class == "function-unwired" and t.trust == "corroborated")
    assert dispatch(dead, root) is True
    assert "zzq_dead" not in open(os.path.join(root, "m.py")).read()


def test_registry_maps_the_unwired_class():
    assert PATCH_PROVIDERS["function-unwired"] is remove_unwired


def test_module_selftest_passes():
    assert patches.selftest() == 0
