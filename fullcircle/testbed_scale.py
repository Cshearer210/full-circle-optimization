#!/usr/bin/env python3
# CALLED BY: the portfolio proof suite / CI (Chris's "hundreds of provable configs" bar).
# FIRES WHEN: proving catch rate and false-positive rate across MANY randomized systems.
"""Scale test (Chris, 2026-09-23: "hundreds of provable configs, 100% on the intended jobs").

testbed.py proves 7 classes on 3 FIXED systems. This generates HUNDREDS of RANDOMISED systems --
each plants a random subset of the 7 defect classes with random names, sizes and directory noise,
plus clean controls with random names -- and scores every finder against a per-config ground truth.

The bar: every planted defect caught (100% per class across all configs) and ZERO false positives
on the controls. Random names each run is also a continuous label-independence proof.
"""
from __future__ import annotations

import os
import random
import shutil
import string
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.expanduser("~/PureEuphoria/claimproof/src"))
try:
    from fullcircle import structural
    from fullcircle.finding import triangulate
except ImportError:
    import structural
    from finding import triangulate
from claimproof import multimethod, rag_index


def _tok(rng):
    return "".join(rng.choice(string.ascii_lowercase) for _ in range(6))


def _w(root, rel, body):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p) or root, exist_ok=True)
    open(p, "w", encoding="utf-8").write(body)


# each planter returns (defect_class, match_token); each writes a uniquely-named defect
def _p_dead_test(root, rng):
    t = _tok(rng)
    _w(root, "tests/test_%s.py" % t, "def test_%s():\n    assert True\n" % t)
    return ("test-cannot-fail", t)


def _p_swallow(root, rng):
    t = _tok(rng)
    _w(root, "sw_%s.py" % t,
       "def f_%s():\n    try:\n        risky()\n    except Exception:\n        return True\nf_%s()\n" % (t, t))
    return ("swallowed-exception", "sw_%s.py" % t)


def _p_gate(root, rng):
    t = _tok(rng)
    _w(root, "gate_%s.py" % t, "def check_%s(user):\n    return True\ncheck_%s(1)\n" % (t, t))
    return ("labeled-gate-that-cannot-fail", "check_%s" % t)


def _p_dup(root, rng):
    t = _tok(rng)
    body = "def blk_%s():\n    return 'unique duplicated payload %s worth keeping once'\nblk_%s()\n" % (t, t, t)
    _w(root, "a/dupA_%s.py" % t, body)
    _w(root, "b/dupB_%s.py" % t, body)
    return ("second-door-duplicate", "dup")


def _p_conflict(root, rng):
    t = _tok(rng).upper()                      # a shared constant is UPPER_CASE by convention
    _w(root, "cfgA_%s.py" % t, "K_%s = 30\n" % t)
    _w(root, "cfgB_%s.py" % t, "K_%s = 'thirty'\n" % t)
    return ("conflicting-definition", "K_%s" % t)


def _p_unwired(root, rng):
    t = _tok(rng)
    _w(root, "orphan_%s.py" % t, "def dead_%s():\n    return 1\n" % t)
    return ("function-unwired", "dead_%s" % t)


def _p_stub(root, rng):
    t = _tok(rng)
    _w(root, "stub_%s.py" % t, "def do_%s(x):\n    pass\ndo_%s(1)\n" % (t, t))
    return ("stub-implementation", "do_%s" % t)


PLANTERS = [_p_dead_test, _p_swallow, _p_gate, _p_dup, _p_conflict, _p_unwired, _p_stub]


def _controls(root, rng):
    """Clean things that must NOT be flagged. Returns their tokens (any finding touching one = FP)."""
    toks = []
    c = _tok(rng); toks.append(c)
    _w(root, "mod_%s.py" % c, "def go_%s():\n    return 1\n" % c)
    _w(root, "tests/test_ok_%s.py" % c,
       "from mod_%s import go_%s\ndef test_ok_%s():\n    assert go_%s() == 1\n" % (c, c, c, c))
    c = _tok(rng); toks.append(c)     # specific-except (idiomatic, not a swallow)
    _w(root, "io_%s.py" % c,
       "def r_%s():\n    try:\n        x()\n    except OSError:\n        return []\nr_%s()\n" % (c, c))
    c = _tok(rng); toks.append(c)     # a real gate that raises
    _w(root, "rg_%s.py" % c,
       "def validate_%s(t):\n    if not t:\n        raise ValueError('x')\n    return t\nvalidate_%s('a')\n" % (c, c))
    c = _tok(rng); toks.append(c)     # a lone constant (no conflict)
    _w(root, "const_%s.py" % c, "ONE_%s = 1\n" % c)
    return toks


def gen_random_system(root, rng):
    # plant a random NON-EMPTY subset of the 7 classes
    k = rng.randint(1, len(PLANTERS))
    chosen = rng.sample(PLANTERS, k)
    ground = [p(root, rng) for p in chosen]
    control_toks = _controls(root, rng)
    # random clean noise modules (all functions called -> nothing flagged)
    for _ in range(rng.randint(0, 6)):
        n = _tok(rng)
        _w(root, "noise/n_%s.py" % n,
           "V_%s = %d\ndef fn_%s():\n    return %d\ndef cl_%s():\n    return fn_%s()\ncl_%s()\n"
           % (n, rng.randint(1, 9), n, rng.randint(1, 9), n, n, n))
        control_toks.append(n)
    return ground, control_toks


def get_findings(root):
    raw = structural.raw_findings(root) + multimethod.raw_findings(root) + rag_index.raw_findings(root)
    return triangulate(raw)


def _touches(t, token):
    if token in t.location:
        return True
    return any(token in (f.extra.get("id_key", "") + f.location + f.ignored_label) for f in t.findings)


def run(n_configs=300, seed=1):
    rng = random.Random(seed)
    per_class_planted, per_class_caught = {}, {}
    total_planted = fp = configs_clean = 0
    fp_examples = []
    for i in range(n_configs):
        d = tempfile.mkdtemp(prefix="scale_")
        try:
            ground, control_toks = gen_random_system(d, rng)
            tri = get_findings(d)
            ok = True
            for cls, tok in ground:
                per_class_planted[cls] = per_class_planted.get(cls, 0) + 1
                total_planted += 1
                if any(t.defect_class == cls and _touches(t, tok) for t in tri):
                    per_class_caught[cls] = per_class_caught.get(cls, 0) + 1
                else:
                    ok = False
            for t in tri:
                for ct in control_toks:
                    if _touches(t, ct):
                        fp += 1
                        if len(fp_examples) < 8:
                            fp_examples.append("%s -> %s" % (t.defect_class, t.location[:50]))
                        ok = False
                        break
            if ok:
                configs_clean += 1
        finally:
            shutil.rmtree(d, ignore_errors=True)
    return {"n_configs": n_configs, "total_planted": total_planted, "configs_clean": configs_clean,
            "per_class_planted": per_class_planted, "per_class_caught": per_class_caught,
            "false_positives": fp, "fp_examples": fp_examples}


GLOSS = {
    "test-cannot-fail": "a test that runs code but checks nothing (green forever)",
    "swallowed-exception": "a broad except that returns success and hides the error",
    "labeled-gate-that-cannot-fail": "named like a gate but its verdict ignores the input",
    "second-door-duplicate": "the same code at two paths; a fix to one misses the other",
    "conflicting-definition": "one constant, different values in two files",
    "function-unwired": "a function defined and complete that nothing calls",
    "stub-implementation": "a pass/NotImplementedError stub that other code already calls",
}


def _report(r) -> bool:
    print("=" * 68)
    print("SCALE TEST -- %d randomised systems, %d planted defects"
          % (r["n_configs"], r["total_planted"]))
    print("=" * 68)
    allok = True
    for cls in sorted(r["per_class_planted"]):
        p = r["per_class_planted"][cls]
        c = r["per_class_caught"].get(cls, 0)
        pct = 100.0 * c / p if p else 0.0
        flag = "" if c == p else "  <-- MISSES"
        if c != p:
            allok = False
        print("  %-30s %4d/%-4d  %5.1f%%%s" % (cls, c, p, pct, flag))
        print("        = %s" % GLOSS.get(cls, "?"))
    print("  false positives on controls: %d" % r["false_positives"])
    for e in r["fp_examples"]:
        print("      FP:", e)
    if r["false_positives"]:
        allok = False
    print("  clean configs: %d/%d" % (r["configs_clean"], r["n_configs"]))
    print("VERDICT:", "100%% catch, 0 false positives across all configs" if allok else "NOT CLEAN")
    return allok


def selftest() -> int:
    # a small run in the selftest so the suite stays fast; the CLI runs the full 300
    ok = _report(run(n_configs=40, seed=7))
    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    n = 300
    for a in sys.argv[1:]:
        if a.isdigit():
            n = int(a)
    sys.exit(0 if _report(run(n_configs=n)) else 1)
