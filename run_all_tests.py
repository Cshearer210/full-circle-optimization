#!/usr/bin/env python3
# CALLED BY: CI and any session verifying the whole portfolio at once.
# FIRES WHEN: proving every module is green in one command (both-directions selftests).
"""One command that runs every module's selftest across all four repos and the test bed. Exit 0 only
if every one passes. This is the single proof a reviewer (or CI) runs."""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                    # fullcircle package
sys.path.insert(0, os.path.expanduser("~/PureEuphoria/claimproof/src"))

MODULES = [
    ("fullcircle.finding", "selftest"),
    ("fullcircle.concepts", "selftest"),
    ("fullcircle.structural", "selftest"),
    ("fullcircle.drift_guard", "selftest"),
    ("fullcircle.fixer", "selftest"),
    ("fullcircle.patches", "selftest"),
    ("fullcircle.orchestrator", "selftest"),
    ("fullcircle.testbed", "selftest"),
    ("claimproof.multimethod", "selftest"),
    ("claimproof.rag_index", "selftest"),
]


def main() -> int:
    passed, failed = [], []
    for mod, fn in MODULES:
        try:
            m = importlib.import_module(mod)
            code = getattr(m, fn)()
            (passed if code == 0 else failed).append(mod)
        except Exception as e:
            print("ERROR importing/running %s: %s" % (mod, e))
            failed.append(mod)
    print("=" * 60)
    print("PORTFOLIO SELFTESTS: %d passed, %d failed (of %d)"
          % (len(passed), len(failed), len(MODULES)))
    for m in failed:
        print("  FAILED:", m)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
