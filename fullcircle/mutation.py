#!/usr/bin/env python3
# CALLED BY: the portfolio quality gate (each repo's own suite is mutation-tested) and, as a 3rd
#            detection method, claimproof's test-cannot-fail.
# FIRES WHEN: proving a test suite can ACTUALLY FAIL -- the deadcanary idea, in-system, for Python.
"""Mutation testing (Chris's decision 2026-09-23: part of the 4-repo system, applied to all four).

The deadcanary principle generalised from dbt to Python: change the code, and the tests MUST go red.
A mutation the suite does NOT catch ("survives") is proof the tests do not cover that line -- the
strongest possible signal that a green suite is protecting nothing.

Two uses:
  1. SELF-QUALITY: run each of the 4 repos' own suites against mutations of their own source, so we
     prove OUR tests can fail (dogfooding).
  2. DETECTION: as claimproof's 3rd method for test-cannot-fail -- a whole test file whose removal
     changes no other test's outcome, or a target whose mutation nothing catches.

It works on an ISOLATED COPY of the repo (never the original), runs the given test command per
mutant with a timeout, and reports the mutation score (killed / total) + the surviving mutations.
No third-party deps (uses ast + subprocess); pytest not required -- any command that exits non-zero
on failure works.
"""
from __future__ import annotations

import ast
import copy
import os
import shutil
import subprocess
import tempfile


def _swap_compare(op):
    m = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt,
         ast.Gt: ast.LtE, ast.LtE: ast.Gt, ast.Is: ast.IsNot, ast.IsNot: ast.Is}
    t = m.get(type(op))
    return t() if t else None


def _is_main_guard(node) -> bool:
    t = getattr(node, "test", None)
    return (isinstance(node, ast.If) and isinstance(t, ast.Compare)
            and isinstance(t.left, ast.Name) and t.left.id == "__name__")


def mutants(src: str, skip_funcs=("selftest",)):
    """Yield (description, mutated_source) -- each with exactly ONE node changed.

    Nodes inside a skip_funcs function (default the in-file `selftest`) or the `if __name__ ==
    '__main__'` guard are NOT mutated: their mutants are structurally unkillable when the test
    command IS that same file's selftest (a failure branch that never runs in a green baseline, or
    the guard that launches it), so counting them only depresses the score of every self-testing
    repo without measuring product-code coverage. Added 2026-09-23."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    skip_ids = set()
    for n in ast.walk(tree):
        if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in skip_funcs) \
                or _is_main_guard(n):
            for d in ast.walk(n):
                skip_ids.add(id(d))
    nodes = list(ast.walk(tree))
    for i, node in enumerate(nodes):
        if id(node) in skip_ids:
            continue
        variants = []
        if isinstance(node, ast.Compare) and node.ops:
            sw = _swap_compare(node.ops[0])
            if sw is not None:
                variants.append(("compare %s->%s" % (type(node.ops[0]).__name__, type(sw).__name__),
                                 "ops0", sw))
        elif isinstance(node, ast.BoolOp):
            variants.append(("bool %s->flip" % type(node.op).__name__, "boolop",
                             ast.Or() if isinstance(node.op, ast.And) else ast.And()))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            variants.append(("arith flip", "binop",
                             ast.Sub() if isinstance(node.op, ast.Add) else ast.Add()))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            variants.append(("bool const %s->%s" % (node.value, not node.value), "const",
                             not node.value))
        for desc, kind, payload in variants:
            newtree = copy.deepcopy(tree)
            tgt = list(ast.walk(newtree))[i]
            if kind == "ops0":
                tgt.ops[0] = payload
            elif kind == "boolop":
                tgt.op = payload
            elif kind == "binop":
                tgt.op = payload
            elif kind == "const":
                tgt.value = payload
            try:
                yield desc + " @L%d" % getattr(node, "lineno", 0), ast.unparse(ast.fix_missing_locations(newtree))
            except Exception:
                continue


# Files a mutation copy must NEVER try to read: unreadable secrets (.env*, sandbox-denied) that
# crash copytree, and heavy dirs that make the copy slow. Skipping them makes pytest-based mutation
# work on repos that keep a .env at the root (e.g. claimproof).
_MUT_IGNORE = shutil.ignore_patterns(".env", ".env.*", ".git", ".venv", "venv", "node_modules",
                                     "__pycache__", "*.pyc", ".pytest_cache", "*.egg-info")


def _test_env(copydir):
    """PYTHONPATH the copy's OWN tree first, so pytest imports the MUTATED copy -- not an
    editable install whose .pth still points at the original source (which makes every mutant
    invisible and reports a false 100%). Harmless for repos without a src/ layout."""
    env = dict(os.environ)
    ahead = [copydir, os.path.join(copydir, "src")]
    if env.get("PYTHONPATH"):
        ahead.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(ahead)
    return env


def run(repo: str, test_cmd, files, max_mutants=60, timeout=120) -> dict:
    """test_cmd: list argv run inside the repo copy. files: source files (rel to repo) to mutate."""
    # baseline: the suite must PASS on an unmutated copy, or the score is meaningless
    base = tempfile.mkdtemp(prefix="mut_base_")
    try:
        shutil.copytree(repo, os.path.join(base, "r"), ignore=_MUT_IGNORE)
        r = subprocess.run(test_cmd, cwd=os.path.join(base, "r"), capture_output=True,
                           timeout=timeout, env=_test_env(os.path.join(base, "r")))
        if r.returncode != 0:
            return {"error": "baseline suite does not pass; cannot mutation-test", "rc": r.returncode}
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"error": "baseline run failed: %s" % e}
    finally:
        shutil.rmtree(base, ignore_errors=True)

    killed, survived, total = 0, [], 0
    for rel in files:
        path = os.path.join(repo, rel)
        try:
            src = open(path, encoding="utf-8").read()
        except OSError:
            continue
        for desc, msrc in mutants(src):
            if total >= max_mutants:
                break
            total += 1
            d = tempfile.mkdtemp(prefix="mut_")
            try:
                dst = os.path.join(d, "r")
                shutil.copytree(repo, dst, ignore=_MUT_IGNORE)
                open(os.path.join(dst, rel), "w", encoding="utf-8").write(msrc)
                try:
                    r = subprocess.run(test_cmd, cwd=dst, capture_output=True, timeout=timeout,
                                       env=_test_env(dst))
                    if r.returncode != 0:
                        killed += 1                      # a test went red -> the mutation was caught
                    else:
                        survived.append("%s: %s" % (rel, desc))
                except subprocess.TimeoutExpired:
                    killed += 1                          # a hang is also "the suite noticed"
            finally:
                shutil.rmtree(d, ignore_errors=True)
    score = (killed / total) if total else 1.0
    return {"total": total, "killed": killed, "survived": survived,
            "score": score, "files": files}


def selftest() -> int:
    ok = True
    d = tempfile.mkdtemp(prefix="mut_self_")
    try:
        repo = os.path.join(d, "r")
        os.makedirs(repo)
        # add(a,b) is COVERED by the test; sub(a,b) is NOT tested at all
        open(os.path.join(repo, "calc.py"), "w").write(
            "def add(a, b):\n    return a + b\n"
            "def sub(a, b):\n    return a - b\n")
        open(os.path.join(repo, "runtests.py"), "w").write(
            "from calc import add\n"
            "assert add(2, 3) == 5\n"
            "print('ok')\n")
        import sys
        rep = run(repo, [sys.executable, "runtests.py"], ["calc.py"], max_mutants=40, timeout=30)
        if rep.get("error"):
            print("FAIL: baseline should pass ->", rep); ok = False
        else:
            # mutating add's + to - is COVERED -> killed. mutating sub's - to + is NOT -> survives.
            if not any("calc.py" in s and "arith" in s for s in rep["survived"]):
                print("FAIL: an uncovered mutation (sub) should SURVIVE ->", rep); ok = False
            if rep["killed"] < 1:
                print("FAIL: a covered mutation (add) should be KILLED ->", rep); ok = False
            if not (0.0 < rep["score"] < 1.0):
                print("FAIL: score should be between 0 and 1 (some killed, some survived) ->", rep["score"]); ok = False
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    # Self-invoke ONLY when --selftest is the sole argument (or none). A broad
    # `"--selftest" in sys.argv` misfired whenever the TEST COMMAND contained --selftest,
    # which is the standard test command in this system -- so mutation testing of any
    # selftest-driven suite silently ran mutation.py's own selftest instead. Caught 2026-09-23.
    if sys.argv[1:] == ["--selftest"] or len(sys.argv) == 1:
        sys.exit(selftest())
    # CLI: mutation.py <repo> <test-cmd...> --files a.py b.py
    argv = sys.argv[1:]
    repo = argv[0]
    files = []
    if "--files" in argv:
        i = argv.index("--files")
        cmd = argv[1:i]
        files = argv[i + 1:]
    else:
        cmd = argv[1:]
    rep = run(repo, cmd, files)
    if rep.get("error"):
        print("ERROR:", rep["error"]); sys.exit(2)
    print("mutation score: %d/%d killed (%.0f%%)" % (rep["killed"], rep["total"], 100 * rep["score"]))
    for s in rep["survived"]:
        print("  SURVIVED (uncovered):", s)
    sys.exit(0 if rep["score"] == 1.0 else 1)
