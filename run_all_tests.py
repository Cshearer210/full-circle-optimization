#!/usr/bin/env python3
# CALLED BY: CI and any reviewer verifying the whole repo at once.
# FIRES WHEN: proving every module is green in one command (both-directions selftests).
"""One command that runs every module's selftest. Exit 0 only if every REQUIRED module passes.

The fullcircle modules are self-contained (standard library only) and are all required. The
silent-defect finder `claimproof` is a separate, optional companion tool; its two modules are run
when importable and reported as SKIPPED (never FAILED) when it is not installed, so a fresh clone of
this repo is green on its own. Install the companion, or point CLAIMPROOF_SRC at a local checkout,
to exercise those two as well.
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                    # fullcircle package

# Optional companion: add a local checkout to the path if CLAIMPROOF_SRC points at one.
_CP = os.environ.get("CLAIMPROOF_SRC")
if _CP and os.path.isdir(_CP):
    sys.path.insert(0, _CP)

REQUIRED = [
    ("fullcircle.finding", "selftest"),
    ("fullcircle.concepts", "selftest"),
    ("fullcircle.structural", "selftest"),
    ("fullcircle.drift_guard", "selftest"),
    ("fullcircle.fixer", "selftest"),
    ("fullcircle.patches", "selftest"),
    ("fullcircle.orchestrator", "selftest"),
    ("fullcircle.testbed", "selftest"),
    ("fullcircle.testbed_scale", "selftest"),
    ("fullcircle.mutation", "selftest"),
    ("fullcircle._optional", "selftest"),
]

# The companion silent-defect finder. Optional: skipped (not failed) when not installed.
OPTIONAL = [
    ("claimproof.multimethod", "selftest"),
    ("claimproof.rag_index", "selftest"),
]


def _run(modules):
    passed, failed, skipped = [], [], []
    for mod, fn in modules:
        try:
            m = importlib.import_module(mod)
        except Exception as e:
            if modules is OPTIONAL:
                skipped.append(mod)
                continue
            print("ERROR importing %s: %s" % (mod, e))
            failed.append(mod)
            continue
        try:
            code = getattr(m, fn)()
            (passed if code == 0 else failed).append(mod)
        except Exception as e:
            print("ERROR running %s: %s" % (mod, e))
            failed.append(mod)
    return passed, failed, skipped


def main() -> int:
    rp, rf, _ = _run(REQUIRED)
    op, of, os_skipped = _run(OPTIONAL)
    print("=" * 60)
    print("REQUIRED selftests: %d passed, %d failed (of %d)" % (len(rp), len(rf), len(REQUIRED)))
    for m in rf:
        print("  FAILED:", m)
    if os_skipped:
        print("OPTIONAL companion (claimproof): SKIPPED -- not installed (%s)"
              % ", ".join(os_skipped))
    else:
        print("OPTIONAL companion (claimproof): %d passed, %d failed (of %d)"
              % (len(op), len(of), len(OPTIONAL)))
        for m in of:
            print("  FAILED:", m)
    # exit code is governed by REQUIRED (and by the companion only when it is actually present)
    return 0 if not rf and not of else 1


if __name__ == "__main__":
    sys.exit(main())
