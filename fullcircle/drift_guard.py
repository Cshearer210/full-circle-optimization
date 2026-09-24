#!/usr/bin/env python3
# CALLED BY: CI, and the full-circle-optimization test run.
# FIRES WHEN: checking that a companion checkout's copy of the shared contract has not drifted.
"""Companion-copy drift guard.

The shared contract file (finding.py) is meant to be byte-identical wherever it is used, so each
tool can stand alone. Two copies of one definition is the "count the doors" defect: a fix to one
copy that misses another makes them silently disagree. This guard fails if any PRESENT companion
copy differs from the canonical in-repo copy.

Companion checkout roots are supplied by the COMPANION_DIRS environment variable (a `os.pathsep`
separated list). None set -> nothing to compare -> exit 0. This repo therefore stands alone: the
guard only has an opinion once you point it at a companion checkout.

Canonical copy: fullcircle/finding.py. exit 0 = all present copies identical / none to check ·
1 = a copy drifted · 2 = canonical unreadable (cannot tell -- never reported as clean).
"""
from __future__ import annotations

import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# The shared-contract files whose companion copies (if any) must match the canonical in-repo copy.
SHARED_FILES = ["finding.py", "concepts.py"]


def _companion_dirs() -> list[str]:
    raw = os.environ.get("COMPANION_DIRS", "")
    return [d for d in raw.split(os.pathsep) if d]


def _rel_paths(fname: str, dirs: list[str]) -> list[str]:
    # a companion checkout may carry the shared file at its root; that is the copy we compare
    return [os.path.join(d, fname) for d in dirs]


CANON = os.path.join(HERE, "finding.py")            # kept for back-compat with older callers


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def check(dirs: list[str] | None = None) -> tuple[int, list[str]]:
    dirs = dirs if dirs is not None else _companion_dirs()
    msgs, drift, present = [], False, 0
    for fname in SHARED_FILES:
        canon_path = os.path.join(HERE, fname)
        if not os.path.exists(canon_path):
            return 2, ["canonical %s missing: %s" % (fname, canon_path)]
        canon = _sha(canon_path)
        for p in _rel_paths(fname, dirs):
            if not os.path.exists(p):
                continue
            present += 1
            if _sha(p) != canon:
                drift = True
                msgs.append("DRIFT: %s differs from canonical %s" % (p, fname))
            else:
                msgs.append("ok: %s identical" % p)
    msgs.insert(0, "%d shared file(s); %d companion copy(ies) present" % (len(SHARED_FILES), present))
    return (1 if drift else 0), msgs


def selftest() -> int:
    import tempfile, shutil
    ok = True
    d = tempfile.mkdtemp(prefix="drift_")
    try:
        # two companion checkouts: one carries an identical copy, one a drifted copy of finding.py
        good_dir = os.path.join(d, "companion_good")
        bad_dir = os.path.join(d, "companion_bad")
        os.makedirs(good_dir); os.makedirs(bad_dir)
        shutil.copyfile(os.path.join(HERE, "finding.py"), os.path.join(good_dir, "finding.py"))
        open(os.path.join(bad_dir, "finding.py"), "w").write("# drifted\n")
        code, msgs = check(dirs=[good_dir, bad_dir])
        if code != 1:
            print("FAIL: a drifted copy must return 1 ->", code, msgs); ok = False
        # drop the drifted checkout -> all present identical -> 0
        code2, _ = check(dirs=[good_dir])
        if code2 != 0:
            print("FAIL: all-identical must return 0 ->", code2); ok = False
        # no companions at all -> nothing to compare -> 0
        code3, _ = check(dirs=[])
        if code3 != 0:
            print("FAIL: no companions must return 0 ->", code3); ok = False
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    code, msgs = check()
    print("\n".join(msgs))
    sys.exit(code)
