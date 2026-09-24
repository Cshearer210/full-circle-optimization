"""Real behavioural tests for the structural finder: one section per defect class, each asserting
the detector fires on a known-bad tree AND stays quiet on a known-good one, plus the corroboration
logic (two independent methods collapsing to one finding) that is the product's whole point.
"""
from __future__ import annotations

import os

import pytest

from fullcircle import structural
from fullcircle.structural import (
    DETECTORS,
    _literal_repr,
    raw_findings,
    scan,
)
from fullcircle.finding import Finding, Triangulated


def classes(tri):
    return {t.defect_class for t in tri}


def by_idkey(tri, defect_class):
    return {t.findings[0].extra.get("id_key"): t for t in tri if t.defect_class == defect_class}


# ---------------------------------------------------------------- second-door duplicate
def test_content_copy_is_a_duplicate(make_repo):
    body = "def compute(x):\n    return x * 2 + 1  # a real block worth keeping once\n"
    root = make_repo({"app/calc.py": body, "lib/calc_copy.py": body})
    dups = [t for t in scan(root) if t.defect_class == "second-door-duplicate"]
    assert dups
    assert any("calc_copy.py" in f.location for t in dups for f in t.findings)


def test_hardlink_is_corroborated(make_repo):
    body = "def compute(x):\n    return x * 2 + 1  # worth keeping exactly once here\n"
    root = make_repo({"app/calc.py": body})
    try:
        os.link(os.path.join(root, "app/calc.py"), os.path.join(root, "hardlinked.py"))
    except OSError:
        pytest.skip("hardlinks unsupported on this filesystem")
    dups = [t for t in scan(root) if t.defect_class == "second-door-duplicate"]
    assert any(t.corroboration >= 2 for t in dups)


def test_trivial_short_files_are_not_duplicates(make_repo):
    root = make_repo({"a.py": "x = 1\n", "b.py": "x = 1\n"})  # < 40 bytes stripped -> ignored
    assert not [t for t in scan(root) if t.defect_class == "second-door-duplicate"]


def test_unique_files_are_not_duplicates(make_repo):
    root = make_repo({
        "a.py": "def one():\n    return 'aaaaaaaaaaaaaaaaaaaaaaaaaaaa distinct'\none()\n",
        "b.py": "def two():\n    return 'bbbbbbbbbbbbbbbbbbbbbbbbbbbb distinct'\ntwo()\n",
    })
    assert not [t for t in scan(root) if t.defect_class == "second-door-duplicate"]


def test_symlinked_file_is_not_double_counted(make_repo):
    body = "def compute(x):\n    return x * 2 + 1  # a real block worth keeping once here\n"
    root = make_repo({"app/calc.py": body})
    try:
        os.symlink(os.path.join(root, "app/calc.py"), os.path.join(root, "mirror.py"))
    except OSError:
        pytest.skip("symlinks unsupported")
    # _walk dedupes by realpath -> the symlink is not seen as a second file -> no duplicate finding
    assert not [t for t in scan(root) if t.defect_class == "second-door-duplicate"]


# ---------------------------------------------------------------- conflicting definition
def test_conflicting_constant_of_different_types_corroborates(make_repo):
    root = make_repo({"a.py": "TIMEOUT = 30\n", "b.py": "TIMEOUT = 'sixty'\n"})
    conf = by_idkey(scan(root), "conflicting-definition")
    assert "conflict:TIMEOUT" in conf
    assert conf["conflict:TIMEOUT"].corroboration == 2  # constant-conflict + value-type-mismatch


def test_same_value_is_not_a_conflict(make_repo):
    root = make_repo({"a.py": "SHARED = 'ok'\n", "b.py": "SHARED = 'ok'\n"})
    assert "conflict:SHARED" not in by_idkey(scan(root), "conflicting-definition")


def test_constant_in_one_file_is_not_a_conflict(make_repo):
    root = make_repo({"a.py": "ONLY_HERE = 1\ndef u():\n    return ONLY_HERE\nu()\n"})
    assert "conflict:ONLY_HERE" not in by_idkey(scan(root), "conflicting-definition")


def test_lowercase_name_is_not_a_constant_conflict(make_repo):
    root = make_repo({"a.py": "lc = 1\n", "b.py": "lc = 2\n"})
    assert "conflict:lc" not in by_idkey(scan(root), "conflicting-definition")


def test_annotated_constant_conflict_is_detected(make_repo):
    root = make_repo({"a.py": "PORT: int = 8080\n", "b.py": "PORT: int = 9090\n"})
    assert "conflict:PORT" in by_idkey(scan(root), "conflicting-definition")


def test_dict_order_does_not_create_a_false_conflict(make_repo):
    root = make_repo({"a.py": "CFG = {'a': 1, 'b': 2}\n", "b.py": "CFG = {'b': 2, 'a': 1}\n"})
    assert "conflict:CFG" not in by_idkey(scan(root), "conflicting-definition")


# ---------------------------------------------------------------- function unwired
def test_truly_dead_function_is_corroborated(make_repo):
    root = make_repo({"mod.py": "def zzq_dead():\n    return 1\ndef used():\n    return 2\n"
                                 "def caller():\n    return used()\ncaller()\n"})
    uw = by_idkey(scan(root), "function-unwired")
    dead = uw.get("unwired:mod.py:zzq_dead")
    assert dead and dead.corroboration == 2


def test_string_dispatched_function_is_single_method_lead(make_repo):
    root = make_repo({"mod.py": "def dispatched():\n    return 2\n"
                                 "HANDLERS = 'dispatched'\ndef c():\n    return 1\nc()\n"})
    uw = by_idkey(scan(root), "function-unwired")
    disp = uw.get("unwired:mod.py:dispatched")
    assert disp and disp.corroboration == 1
    assert "no-call-edge" in disp.methods


def test_called_function_is_not_unwired(make_repo):
    root = make_repo({"mod.py": "def used():\n    return 1\ndef c():\n    return used()\nc()\n"})
    assert "unwired:mod.py:used" not in by_idkey(scan(root), "function-unwired")


def test_exported_decorated_and_ambiguous_functions_are_excluded(make_repo):
    root = make_repo({"ex.py":
                      "import functools\n__all__ = ['exp_fn']\n"
                      "@functools.cache\ndef decorated_fn():\n    return 1\n"
                      "def exp_fn():\n    return 2\n"
                      "def dup_fn():\n    return 3\ndef dup_fn():\n    return 4\n"})
    uw = {t.findings[0].extra["id_key"].rsplit(":", 1)[-1]
          for t in scan(root) if t.defect_class == "function-unwired"}
    for nm in ("exp_fn", "decorated_fn", "dup_fn"):
        assert nm not in uw


def test_conftest_functions_are_not_unwired(make_repo):
    # pytest fixtures are framework-wired by name, not called in source.
    root = make_repo({"conftest.py": "def a_fixture_zzz():\n    return 1\n"})
    assert "unwired:conftest.py:a_fixture_zzz" not in by_idkey(scan(root), "function-unwired")


def test_non_constant_all_element_does_not_crash_scan(make_repo):
    root = make_repo({"ba.py": "def kept():\n    return 1\n__all__ = ['a_str', kept]\n"})
    scan(root)  # must not raise


# ---------------------------------------------------------------- stub implementation
def test_called_stub_is_corroborated(make_repo):
    root = make_repo({"svc.py": "def process_payment(o):\n    raise NotImplementedError\n"
                                 "process_payment(1)\n"})
    stubs = by_idkey(scan(root), "stub-implementation")
    pp = stubs.get("stub:svc.py:process_payment")
    assert pp and pp.corroboration == 2


def test_module_level_ellipsis_stub_is_detected(make_repo):
    root = make_repo({"dots.py": "def stub_dots():\n    ...\nstub_dots()\n"})
    assert "stub:dots.py:stub_dots" in by_idkey(scan(root), "stub-implementation")


def test_abstractmethod_stub_is_not_flagged(make_repo):
    root = make_repo({"svc.py": "import abc\nclass B(abc.ABC):\n    @abc.abstractmethod\n"
                                 "    def do(self):\n        pass\n"})
    assert "stub:svc.py:do" not in by_idkey(scan(root), "stub-implementation")


def test_protocol_ellipsis_method_is_not_a_stub(make_repo):
    root = make_repo({"proto.py": "class P:\n    def method(self):\n        ...\n"})
    assert "stub:proto.py:method" not in by_idkey(scan(root), "stub-implementation")


def test_real_function_is_not_a_stub(make_repo):
    root = make_repo({"svc.py": "def real(x):\n    return x + 1\nreal(2)\n"})
    assert "stub:svc.py:real" not in by_idkey(scan(root), "stub-implementation")


# ---------------------------------------------------------------- dead code
def test_statement_after_return_is_dead(make_repo):
    root = make_repo({"dc.py": "def f():\n    y = 1\n    return y\n    x = 2\n"})
    dead = [t for t in scan(root) if t.defect_class == "dead-code"]
    assert any(t.location.endswith(":4") for t in dead)


def test_no_dead_code_in_clean_function(make_repo):
    root = make_repo({"ok.py": "def f():\n    y = 1\n    return y\nf()\n"})
    assert not [t for t in scan(root) if t.defect_class == "dead-code"]


# ---------------------------------------------------------------- unused import
def test_unused_imports_are_flagged(make_repo):
    root = make_repo({"pkg/mod.py":
                      "from __future__ import annotations\nimport os\nimport sys\n"
                      "import json as j\nfrom os import getcwd\nfrom os import getpid as gp\n"
                      "print(sys.path)\n",
                      "pkg/__init__.py": "import collections\n"})
    ui = {f.ignored_label for t in scan(root)
          if t.defect_class == "unused-import" for f in t.findings}
    for want in ("os", "j", "getcwd", "gp"):
        assert want in ui
    assert "sys" not in ui                # used
    assert "annotations" not in ui        # future import
    assert "collections" not in ui        # inside __init__.py (skipped)


def test_wildcard_import_suppresses_unused_findings(make_repo):
    root = make_repo({"st.py": "from os import *\nimport json\nprint(getcwd())\n"})
    ui = {f.ignored_label for t in scan(root)
          if t.defect_class == "unused-import" for f in t.findings}
    assert "json" not in ui


# ---------------------------------------------------------------- mutable default arg
def test_mutable_default_is_flagged(make_repo):
    root = make_repo({"md.py": "def f(x=[]):\n    return x\nf()\n"})
    assert "mutable-default-arg" in classes(scan(root))


def test_none_default_is_not_flagged(make_repo):
    root = make_repo({"ok.py": "def f(x=None):\n    return x\nf()\n"})
    assert "mutable-default-arg" not in classes(scan(root))


# ---------------------------------------------------------------- bare except
def test_bare_except_is_flagged_typed_is_not(make_repo):
    root = make_repo({"be.py":
                      "def risky():\n    try:\n        return 1\n    except:\n        return 2\n"
                      "def safe():\n    try:\n        return 3\n    except ValueError:\n        return 4\n"})
    be = [t for t in scan(root) if t.defect_class == "bare-except"]
    assert any(t.location.endswith(":4") for t in be)
    assert not any(t.location.endswith(":9") for t in be)


# ---------------------------------------------------------------- resource leak
def test_bare_open_statement_is_a_leak(make_repo):
    root = make_repo({"lk.py": "def f():\n    open('x')\n    return 1\nf()\n"})
    assert "resource-leak" in classes(scan(root))


def test_with_open_is_not_a_leak(make_repo):
    root = make_repo({"ok.py": "def f():\n    with open('x') as fh:\n        return fh.read()\nf()\n"})
    assert "resource-leak" not in classes(scan(root))


# ---------------------------------------------------------------- shadowed builtin
def test_module_level_shadowed_builtin_is_flagged(make_repo):
    root = make_repo({"sh.py": "list = [1, 2, 3]\nUSE = list\n"})
    assert "shadowed-builtin" in classes(scan(root))


def test_local_shadowing_is_not_flagged(make_repo):
    root = make_repo({"ok.py": "def f():\n    list = [1]\n    return list\nf()\n"})
    assert "shadowed-builtin" not in classes(scan(root))


# ---------------------------------------------------------------- clean repo & structure
def test_clean_repo_produces_no_findings(make_repo):
    root = make_repo({
        "a.py": "def helper():\n    return 'aaaaaaaaaaaaaaaaaaaaaaaaa distinct'\n"
                "def entry():\n    return helper()\nentry()\n",
        "b.py": "def worker():\n    return 'bbbbbbbbbbbbbbbbbbbbbbbbb distinct'\nworker()\n",
    })
    assert scan(root) == []


def test_raw_findings_returns_finding_objects(make_repo):
    root = make_repo({"md.py": "def f(x=[]):\n    return x\nf()\n"})
    raw = raw_findings(root)
    assert raw and all(isinstance(f, Finding) for f in raw)


def test_scan_returns_triangulated(make_repo):
    root = make_repo({"md.py": "def f(x=[]):\n    return x\nf()\n"})
    assert all(isinstance(t, Triangulated) for t in scan(root))


def test_detectors_registry_covers_ten_classes():
    assert len(DETECTORS) == 10
    assert "second-door-duplicate" in DETECTORS


def test_unparsable_file_is_skipped_not_crashed(make_repo):
    root = make_repo({"broken.py": "def (:\n", "md.py": "def f(x=[]):\n    return x\nf()\n"})
    assert "mutable-default-arg" in classes(scan(root))  # good file still scanned, no crash


# ---------------------------------------------------------------- _literal_repr unit
def test_literal_repr_canonicalises_dict_and_set_order():
    assert _literal_repr(_expr("{'b': 2, 'a': 1}")) == _literal_repr(_expr("{'a': 1, 'b': 2}"))
    assert _literal_repr(_expr("{3, 2, 1}")) == _literal_repr(_expr("{1, 2, 3}"))


def test_literal_repr_returns_none_for_non_literal():
    assert _literal_repr(_expr("some_call()")) is None


def test_literal_repr_represents_dict_unpack():
    assert "**" in (_literal_repr(_expr("{**BASE, 'y': 2}")) or "")


def _expr(src):
    import ast
    return ast.parse(src, mode="eval").body


def test_module_selftest_passes():
    assert structural.selftest() == 0
