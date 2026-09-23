#!/usr/bin/env python3
# CALLED BY: each repo's CI, and the FULL-CIRCLE-OPTIMIZATION test run (step D4).
# FIRES WHEN: checking that the shared contract copied into each repo has not drifted.
"""The 4 portfolio repos each carry a byte-identical copy of finding.py so each stands alone for a
recruiter to run. Two copies of one definition is Chris's "count the doors" defect
(nothing-ships-unwired 13-15): a fix to one copy that misses the others makes the repos silently
disagree. This guard fails if any present copy differs from the canonical one.

Canonical copy: fullcircle/finding.py. exit 0 = all present copies identical · 1 = a copy drifted ·
2 = canonical unreadable (cannot tell -- never reported as clean).
"""
from __future__ import annotations

import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Each shared file: canonical copy (in fullcircle) -> the repo copies, relative to $HOME. Absent
# copies are skipped (a repo not yet populated is not a drift); a PRESENT copy that differs fails.
SHARED = {
    "finding.py": [
        "PureEuphoria/claimproof/src/claimproof/finding.py",
        "rag-ghost-work/ragghost/finding.py",       # FULL-RESET-GRAPH (after it is populated)
        "corral-work/corral/finding.py",            # SANDBOX-FAN-OUT (after it is populated)
    ],
    "concepts.py": [
        "PureEuphoria/claimproof/src/claimproof/concepts.py",
        "rag-ghost-work/ragghost/concepts.py",
    ],
}
CANON = os.path.join(HERE, "finding.py")            # kept for back-compat with older callers


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def check(home: str | None = None) -> tuple[int, list[str]]:
    home = home or os.path.expanduser("~")
    msgs, drift, present = [], False, 0
    for fname, copies in SHARED.items():
        canon_path = os.path.join(HERE, fname)
        if not os.path.exists(canon_path):
            return 2, ["canonical %s missing: %s" % (fname, canon_path)]
        canon = _sha(canon_path)
        for rel in copies:
            p = os.path.join(home, rel)
            if not os.path.exists(p):
                continue
            present += 1
            if _sha(p) != canon:
                drift = True
                msgs.append("DRIFT: %s differs from canonical %s" % (rel, fname))
            else:
                msgs.append("ok: %s identical" % rel)
    msgs.insert(0, "%d shared file(s); %d copy(ies) present" % (len(SHARED), present))
    return (1 if drift else 0), msgs


def selftest() -> int:
    import tempfile, shutil
    ok = True
    d = tempfile.mkdtemp(prefix="drift_")
    try:
        # a home with one identical copy and one drifted copy of finding.py
        copies = SHARED["finding.py"]
        good = os.path.join(d, copies[0])
        bad = os.path.join(d, copies[1])
        os.makedirs(os.path.dirname(good)); os.makedirs(os.path.dirname(bad))
        shutil.copyfile(os.path.join(HERE, "finding.py"), good)
        open(bad, "w").write("# drifted\n")
        code, msgs = check(home=d)
        if code != 1:
            print("FAIL: a drifted copy must return 1 ->", code, msgs); ok = False
        # now remove the bad one -> all present identical -> 0
        os.remove(bad)
        code2, _ = check(home=d)
        if code2 != 0:
            print("FAIL: all-identical must return 0 ->", code2); ok = False
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
