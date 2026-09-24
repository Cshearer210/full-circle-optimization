"""Real behavioural tests for the mutation-testing module: the mutation operators, the skip rules
(selftest body + __main__ guard), the isolated-copy runner, and the honest baseline/score contract.
A covered mutation must be KILLED and an uncovered one must SURVIVE -- that gap is the whole signal.
"""
from __future__ import annotations

import ast
import os
import sys

import pytest

from fullcircle import mutation
from fullcircle.mutation import (
    _is_main_guard,
    _swap_compare,
    _test_env,
    mutants,
    run,
)


def descs(src, **kw):
    return [d for d, _ in mutants(src, **kw)]


# ---------------------------------------------------------------- _swap_compare
def test_swap_compare_inverts_operators():
    assert isinstance(_swap_compare(ast.Eq()), ast.NotEq)
    assert isinstance(_swap_compare(ast.Lt()), ast.GtE)
    assert isinstance(_swap_compare(ast.Is()), ast.IsNot)


def test_swap_compare_unknown_operator_is_none():
    assert _swap_compare(ast.In()) is None


# ---------------------------------------------------------------- _is_main_guard
def test_is_main_guard_true():
    node = ast.parse("if __name__ == '__main__':\n    pass\n").body[0]
    assert _is_main_guard(node) is True


def test_is_main_guard_false_for_other_if():
    node = ast.parse("if x == 1:\n    pass\n").body[0]
    assert _is_main_guard(node) is False


# ---------------------------------------------------------------- mutants()
def test_mutants_produces_compare_mutation():
    assert any("compare" in d for d in descs("def f(a):\n    return a == 1\n"))


def test_mutants_produces_boolop_mutation():
    assert any("bool" in d and "flip" in d for d in descs("def f(a, b):\n    return a and b\n"))


def test_mutants_produces_arith_mutation():
    assert any("arith" in d for d in descs("def f(a, b):\n    return a + b\n"))


def test_mutants_produces_bool_constant_mutation():
    assert any("bool const" in d for d in descs("def f():\n    return True\n"))


def test_mutants_skip_selftest_body_by_default():
    src = "def selftest():\n    return 1 + 2\ndef prod(a, b):\n    return a + b\n"
    ds = descs(src)
    # the arith mutation must come from prod, not from selftest
    assert any("arith" in d for d in ds)
    # exactly one arith mutant (prod's), selftest's is skipped
    assert sum("arith" in d for d in ds) == 1


def test_mutants_skip_main_guard():
    src = ("def prod(a):\n    return a == 1\n"
           "if __name__ == '__main__':\n    prod(2 == 2)\n")
    # only prod's compare is mutated; the guard's __name__=='__main__' and the 2==2 arg are skipped
    assert sum("compare" in d for d in descs(src)) == 1


def test_mutants_on_syntax_error_yields_nothing():
    assert descs("def (:\n") == []


def test_mutants_each_change_is_valid_python():
    for _, msrc in mutants("def f(a, b):\n    return a + b == 3\n"):
        ast.parse(msrc)  # every emitted mutant must parse


# ---------------------------------------------------------------- _test_env
def test_test_env_puts_copydir_first_on_pythonpath():
    env = _test_env("/tmp/copyX")
    parts = env["PYTHONPATH"].split(os.pathsep)
    assert parts[0] == "/tmp/copyX"


def test_test_env_appends_existing_pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/pre/existing")
    env = _test_env("/tmp/copyY")
    assert "/pre/existing" in env["PYTHONPATH"].split(os.pathsep)


# ---------------------------------------------------------------- run()
@pytest.fixture
def calc_repo(tmp_path):
    root = str(tmp_path / "r")
    os.makedirs(root)
    open(os.path.join(root, "calc.py"), "w").write(
        "def add(a, b):\n    return a + b\n"
        "def sub(a, b):\n    return a - b\n")
    open(os.path.join(root, "runtests.py"), "w").write(
        "from calc import add\nassert add(2, 3) == 5\nprint('ok')\n")
    return root


def test_run_kills_covered_and_survives_uncovered(calc_repo):
    rep = run(calc_repo, [sys.executable, "runtests.py"], ["calc.py"], max_mutants=40, timeout=30)
    assert "error" not in rep
    assert rep["killed"] >= 1                                   # add's + is covered -> killed
    assert any("calc.py" in s and "arith" in s for s in rep["survived"])  # sub's - uncovered
    assert 0.0 < rep["score"] < 1.0


def test_run_reports_baseline_failure(tmp_path):
    root = str(tmp_path / "r")
    os.makedirs(root)
    open(os.path.join(root, "calc.py"), "w").write("def add(a, b):\n    return a + b\n")
    open(os.path.join(root, "runtests.py"), "w").write("assert False\n")  # baseline fails
    rep = run(root, [sys.executable, "runtests.py"], ["calc.py"], max_mutants=5, timeout=30)
    assert "error" in rep


def test_run_respects_max_mutants(calc_repo):
    rep = run(calc_repo, [sys.executable, "runtests.py"], ["calc.py"], max_mutants=1, timeout=30)
    assert rep["total"] <= 1


def test_run_missing_file_yields_no_mutants(tmp_path):
    root = str(tmp_path / "r")
    os.makedirs(root)
    open(os.path.join(root, "runtests.py"), "w").write("print('ok')\n")
    rep = run(root, [sys.executable, "runtests.py"], ["does_not_exist.py"], timeout=30)
    assert rep["total"] == 0
    assert rep["score"] == 1.0  # no mutants -> vacuously perfect (documented behaviour)


def test_module_selftest_passes():
    assert mutation.selftest() == 0
