#!/usr/bin/env python3
# CALLED BY: SANDBOX-FAN-OUT's fixer as the patch_provider; the orchestrator's --fix path.
# FIRES WHEN: a corroborated, mechanically-fixable defect is being repaired on an isolated clone.
"""Mechanical patch providers -- the tier-1 of Chris's mechanical/reasoning split (refinement 5):
KNOWN class -> KNOWN patch, no model. Everything else is left to a model or to human review.

Only truly-safe mechanical fixes live here. The first is removing CORROBORATED DEAD CODE: a
function found unwired by BOTH methods (no call edge AND no reference of any kind) is referenced
nowhere, so deleting it cannot change behaviour -- and the fixer re-verifies both directions on the
clone regardless, rolling back if anything moves. AST-based removal (keeps the rest of the file
intact); refuses anything not corroborated.
"""
from __future__ import annotations

import ast
import os


def remove_unwired(t, root) -> bool:
    """Delete a corroborated-unwired function definition. Refuses single-method leads (unsafe)."""
    if getattr(t, "trust", "") != "corroborated":
        return False
    rel, _, _ln = t.location.rpartition(":")
    name = t.findings[0].ignored_label
    path = os.path.join(root, rel)
    try:
        src = open(path, encoding="utf-8").read()
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return False
    target = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            target = node
            break
    if target is None or not getattr(target, "end_lineno", None):
        return False
    lines = src.splitlines(keepends=True)
    start = (target.decorator_list[0].lineno if target.decorator_list else target.lineno) - 1
    end = target.end_lineno                                # 1-based inclusive
    del lines[start:end]
    open(path, "w", encoding="utf-8").write("".join(lines))
    return True


PATCH_PROVIDERS = {
    "function-unwired": remove_unwired,
}


def dispatch(t, root) -> bool:
    """Mechanical patch if one is registered for this defect class; else no change (-> human/model)."""
    fn = PATCH_PROVIDERS.get(t.defect_class)
    return bool(fn(t, root)) if fn else False


def selftest() -> int:
    import tempfile, shutil, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from fullcircle import structural, fixer
    except ImportError:
        import structural, fixer  # type: ignore
    ok = True

    d = tempfile.mkdtemp(prefix="patch_")
    try:
        # a used function (must survive) + a corroborated-dead one (must be removed)
        open(os.path.join(d, "m.py"), "w").write(
            "def used():\n    return 1\n"
            "def caller():\n    return used()\n"
            "def zzq_dead():\n    return 99\n"          # referenced nowhere -> corroborated unwired
            "caller()\n")

        before = structural.scan(d)
        dead = [t for t in before if t.defect_class == "function-unwired" and t.trust == "corroborated"]
        if not dead:
            print("FAIL: setup -- expected a corroborated dead function ->", before); ok = False

        # run the REAL fixer with the REAL mechanical patch provider, wet, verifying both directions
        rep = fixer.apply_fixes(d, dead, dispatch, structural.scan, dry_run=False)
        if len(rep["applied"]) != 1:
            print("FAIL: the dead function was not fixed ->", rep); ok = False

        after_src = open(os.path.join(d, "m.py")).read()
        if "zzq_dead" in after_src:
            print("FAIL: dead function still present after fix"); ok = False
        if "def used" not in after_src or "def caller" not in after_src:
            print("FAIL: the fix removed live code!"); ok = False
        # and the finding is really gone, nothing new introduced
        # KILLS line 30 (False->True): unreadable file -> except (OSError, SyntaxError) -> must return False.
        class _FNoFile:
            ignored_label = "anything"
        class _TNoFile:
            trust = "corroborated"
            location = "does_not_exist_file_zzz.py:1"
            findings = [_FNoFile()]
        _res_nofile = remove_unwired(_TNoFile(), d)
        if _res_nofile is not False:
            print("FAIL: remove_unwired must return False when the file cannot be read ->", _res_nofile); ok = False

        # KILLS line 37 (False->True): name not present in the file -> target is None -> must return False.
        class _FMissing:
            ignored_label = "does_not_exist_zzz"
        class _TMissing:
            trust = "corroborated"
            location = "m.py:1"
            findings = [_FMissing()]
        _res_missing = remove_unwired(_TMissing(), d)
        if _res_missing is not False:
            print("FAIL: remove_unwired must return False when the function name is not found ->", _res_missing); ok = False

        # KILLS line 38 (keepends True->False): dropping line-endings mashes the file into one broken line;
        # substring checks miss it, so assert the rewritten file still parses as valid Python.
        try:
            ast.parse(after_src)
        except SyntaxError as _e:
            print("FAIL: fixed file is not valid Python (line endings lost during removal) ->", _e); ok = False

        # KILLS line 54 (else False->True): unregistered defect class -> no provider -> must return False.
        class _TUnknown:
            defect_class = "no-such-registered-class"
        _res_dispatch = dispatch(_TUnknown(), d)
        if _res_dispatch is not False:
            print("FAIL: dispatch must return False for an unregistered defect class ->", _res_dispatch); ok = False

        after = structural.scan(d)
        if any(t.defect_class == "function-unwired" and "zzq_dead" in
               (t.findings[0].ignored_label) for t in after):
            print("FAIL: unwired finding survived the fix"); ok = False

        # refusal: a single-method (uncorroborated) unwired lead must NOT be auto-removed
        d2 = tempfile.mkdtemp(prefix="patch2_")
        try:
            # a function referenced only as a string -> single-method lead, must be left alone
            open(os.path.join(d2, "n.py"), "w").write(
                "def keep_me():\n    return 1\n"
                "HANDLERS = 'keep_me'\ndef c():\n    return 2\nc()\n")
            leads = [t for t in structural.scan(d2) if t.defect_class == "function-unwired"]
            for t in leads:
                if remove_unwired(t, d2):
                    print("FAIL: a single-method lead was auto-removed (unsafe)"); ok = False
            if "def keep_me" not in open(os.path.join(d2, "n.py")).read():
                print("FAIL: string-referenced function was wrongly removed"); ok = False
        finally:
            shutil.rmtree(d2, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
