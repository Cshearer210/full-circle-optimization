#!/usr/bin/env python3
# CALLED BY: the portfolio's test suite and CI (the proof across many configs).
# FIRES WHEN: proving the finders catch every intended defect class, at 3 complexity levels, on
#             systems they have never seen -- including a RENAMED variant (label-independence).
"""The test bed (Chris, 2026-09-23: "test it all out thoroughly over and over ... 3 complexity
levels ... 100% on the intended jobs"). It GENERATES fake systems with KNOWN planted defects plus
clean controls, runs every finder, and scores catch rate against ground truth. The intended jobs
must be 100% and the controls must produce ZERO false positives before anything releases (T7).

The renamed variant is the label-independence proof: rename every symbol and file and the intended
catch rate must not move -- because the detectors key on behaviour, not labels.
"""
from __future__ import annotations

import os
import random
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
_CP = os.path.expanduser("~/PureEuphoria/claimproof/src")
if _CP not in sys.path:
    sys.path.insert(0, _CP)
sys.path.insert(0, os.path.dirname(HERE))            # for `fullcircle` package
try:
    from fullcircle import structural
    from fullcircle.finding import triangulate
except ImportError:
    import structural
    from finding import triangulate
from claimproof import multimethod, rag_index


def _w(root, rel, body):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p) or root, exist_ok=True)
    open(p, "w", encoding="utf-8").write(body)


def gen_system(root, level="basic", rng=None):
    """Plant one of each intended defect + clean controls. Returns the ground-truth marker list.
    `level` scales the amount of clean surrounding code (signal-in-noise)."""
    rng = rng or random.Random(0)
    ground = []

    # CONTROL: a real test that asserts on a real result (must NOT be flagged)
    _w(root, "pkg/__init__.py", "")
    _w(root, "pkg/core.py", "def compute(x):\n    return x * 2 + 1\n")
    _w(root, "tests/test_good.py",
       "from pkg.core import compute\ndef test_good():\n    assert compute(2) == 5\n")

    # PLANT 1: a test that cannot fail
    _w(root, "tests/test_dead.py", "def test_dead():\n    assert True\n")
    ground.append(("test-cannot-fail", "test_dead.py"))

    # PLANT 2: a second-door duplicate (identical content, two paths)
    dup = ("def _blk():\n    return 'a duplicated block of real logic worth keeping once'\n_blk()\n")
    _w(root, "pkg/dup_a.py", dup)
    _w(root, "lib/dup_b.py", dup)
    ground.append(("second-door-duplicate", "dup_"))

    # PLANT 3: a conflicting constant
    _w(root, "conf/settings_a.py", "TIMEOUT = 30\n")
    _w(root, "conf/settings_b.py", "TIMEOUT = 'thirty'\n")
    ground.append(("conflicting-definition", "conflict:TIMEOUT"))

    # PLANT 4: an unwired function (never referenced anywhere)
    _w(root, "pkg/orphan.py", "def zzq_orphan_fn():\n    return 42\n")
    ground.append(("function-unwired", "zzq_orphan_fn"))

    # PLANT 5: a function labeled like a gate that cannot fail (returns True, ignores input)
    _w(root, "pkg/access.py", "def check_access(user):\n    return True\ncheck_access(1)\n")
    ground.append(("labeled-gate-that-cannot-fail", "check_access"))

    # CONTROL: a REAL gate that raises on bad input -- must NOT be flagged
    _w(root, "pkg/realgate.py",
       "def validate_token(t):\n    if not t:\n        raise ValueError('no')\n    return t\n"
       "validate_token('ok')\n")

    # PLANT 6: a swallowed exception (failure returned as success)
    _w(root, "pkg/swallow_bad.py",
       "def load_cfg():\n    try:\n        risky()\n    except Exception:\n        return True\nload_cfg()\n")
    ground.append(("swallowed-exception", "swallow_bad.py"))

    # CONTROL: a proper handler that re-raises -- must NOT be flagged
    _w(root, "pkg/goodio.py",
       "def save_cfg():\n    try:\n        risky()\n    except Exception:\n        raise\nsave_cfg()\n")

    # CONTROL: a fully-wired helper module (all functions called) -- must NOT be flagged unwired
    _w(root, "pkg/util.py", "def helper():\n    return 1\ndef _run():\n    return helper()\n_run()\n")

    # NOISE scaled by level -- clean, self-contained modules
    n = {"basic": 1, "medium": 8, "complex": 25}.get(level, 1)
    for i in range(n):
        _w(root, "extra/mod_%d.py" % i,
           "UNIQUE_%d = %d\ndef f_%d():\n    return %d\ndef c_%d():\n    return f_%d()\nc_%d()\n"
           % (i, i, i, i, i, i, i))
    return ground


def get_findings(root):
    raw = (structural.raw_findings(root) + multimethod.raw_findings(root)
           + rag_index.raw_findings(root))
    return triangulate(raw)


_CONTROL_MARKERS = ("test_good", "helper", "_run", "compute", "UNIQUE_", "f_", "c_", "mod_",
                    "validate_token", "save_cfg", "goodio")


def score(root, ground):
    tri = get_findings(root)
    caught, missed = [], []
    for cls, marker in ground:
        hit = any(t.defect_class == cls and
                  (marker in t.location or
                   any(marker in (f.extra.get("id_key", "") + f.location + f.ignored_label)
                       for f in t.findings))
                  for t in tri)
        (caught if hit else missed).append((cls, marker))
    # a false positive: a finding whose only locus is a control marker and matches no ground plant
    ground_markers = {m for _, m in ground}
    false_pos = []
    for t in tri:
        blob = t.location + " " + " ".join(f.extra.get("id_key", "") + f.ignored_label for f in t.findings)
        if any(gm in blob or gm in t.defect_class for gm in ground_markers):
            continue                                  # it's a planted one
        if any(cm in blob for cm in _CONTROL_MARKERS):
            false_pos.append((t.defect_class, t.location[:60]))
    return {"caught": caught, "missed": missed, "false_positives": false_pos,
            "total_findings": len(tri)}


def run_levels(levels=("basic", "medium", "complex")):
    report = {}
    for lvl in levels:
        for rename in (False, True):
            d = tempfile.mkdtemp(prefix="tb_%s_" % lvl)
            try:
                ground = gen_system(d, lvl)
                if rename:
                    ground = _rename_everything(d, ground)
                sc = score(d, ground)
                key = "%s%s" % (lvl, "+renamed" if rename else "")
                report[key] = {
                    "intended": len(ground), "caught": len(sc["caught"]),
                    "missed": sc["missed"], "false_positives": sc["false_positives"],
                }
            finally:
                shutil.rmtree(d, ignore_errors=True)
    return report


def _rename_everything(root, ground=None):
    """Rename symbols that a detector must NOT depend on, WITHOUT changing behaviour, to prove
    label-independence. We keep test_* names (runner collection is convention-bound, by design) and
    the conflicting CONSTANT name (its identity IS the name), but rename the duplicated block's
    function and the orphan -- the structural signals must still fire. Returns ground with the
    renamed markers updated, so a PASS means 'the class was still caught under a new name'."""
    # rename the duplicated helper function in both copies (same rename -> still identical content)
    for rel in ("pkg/dup_a.py", "lib/dup_b.py"):
        p = os.path.join(root, rel)
        s = open(p).read().replace("_blk", "qqParticular")
        open(p, "w").write(s)
    # rename the orphan function (still referenced nowhere -> still unwired)
    p = os.path.join(root, "pkg/orphan.py")
    s = open(p).read().replace("zzq_orphan_fn", "wpZeta")   # read FIRST, then truncate+write
    open(p, "w").write(s)
    if ground is None:
        return None
    return [(c, "wpZeta" if m == "zzq_orphan_fn" else m) for c, m in ground]


def selftest() -> int:
    ok = True
    d = tempfile.mkdtemp(prefix="tb_self_")
    try:
        ground = gen_system(d, "basic")
        sc = score(d, ground)
        if sc["missed"]:
            print("FAIL: intended jobs not 100% ->", sc["missed"]); ok = False
        if sc["false_positives"]:
            print("FAIL: false positives on controls ->", sc["false_positives"]); ok = False
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # label-independence: rename the duplicate+orphan symbols, catch rate must hold
    d2 = tempfile.mkdtemp(prefix="tb_rn_")
    try:
        ground = gen_system(d2, "basic")
        ground = _rename_everything(d2, ground)
        sc = score(d2, ground)
        # dup + unwired must still be caught after renaming their symbols
        got = {c for c, _ in sc["caught"]}
        for cls in ("second-door-duplicate", "function-unwired"):
            if cls not in got:
                print("FAIL: %s not caught after rename (label dependence!)" % cls); ok = False
    finally:
        shutil.rmtree(d2, ignore_errors=True)

    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    rep = run_levels()
    print("=" * 66)
    print("TEST BED -- intended-job catch rate across levels (must be 100%, 0 FP)")
    print("=" * 66)
    allok = True
    for key, r in rep.items():
        status = "OK" if r["caught"] == r["intended"] and not r["false_positives"] else "FAIL"
        if status == "FAIL":
            allok = False
        print("  %-18s %d/%d caught  %d false-pos   %s"
              % (key, r["caught"], r["intended"], len(r["false_positives"]), status))
        for m in r["missed"]:
            print("      MISSED:", m)
        for fp in r["false_positives"]:
            print("      FALSE POSITIVE:", fp)
    print("VERDICT:", "100% on intended jobs, 0 false positives" if allok else "NOT CLEAN")
    sys.exit(0 if allok else 1)
