#!/usr/bin/env python3
# CALLED BY: the test bed, the scale test, the orchestrator and run_all_tests.py.
# FIRES WHEN: a run wants the optional silent-defect finder wired in, if it is available.
"""Optional companion loader.

full-circle-optimization ships three working roles of its own -- the linker (orchestrator +
finding), the structural finder (structural), and the safe fixer (fixer + patches). The SILENT
defect classes (a test that cannot fail, a gate that ignores its input, a swallowed exception, and
a few more) are found by a separate companion tool, `claimproof`, which lives in its own repository.

This module makes that companion OPTIONAL, with no hard dependency and no hard-coded path:

  * the fullcircle finders always stand alone (10 defect classes, proven by the test bed), and
  * when `claimproof` is importable, its two finders are added, extending the proof to the silent
    classes as well.

Availability order:
  1. an installed `claimproof` package (pip install, or a checkout on PYTHONPATH), then
  2. a directory named by the CLAIMPROOF_SRC environment variable (a local checkout of the
     companion repo), added to sys.path if it exists.
"""
from __future__ import annotations

import os
import sys

# Defect classes that only the companion silent-defect finder proves. The fullcircle structural
# finder does not claim these; when claimproof is absent they are reported as NOT EXERCISED rather
# than counted as misses, so a self-contained run stays honest and green.
SILENT_CLASSES = frozenset({
    "test-cannot-fail",
    "swallowed-exception",
    "labeled-gate-that-cannot-fail",
    "predicate-returns-none",
    "unreachable-except",
    "assert-constant-in-production",
})


class _EmptyFinder:
    """Stands in for a companion finder that is not installed: finds nothing, never errors."""

    @staticmethod
    def raw_findings(root):
        return []


def load_claimproof():
    """Return (multimethod, rag_index) from the companion repo, or (None, None) if unavailable."""
    src = os.environ.get("CLAIMPROOF_SRC")
    if src and os.path.isdir(src) and src not in sys.path:
        sys.path.insert(0, src)
    try:
        from claimproof import multimethod, rag_index  # type: ignore
        return multimethod, rag_index
    except Exception:
        return None, None


def claimproof_finders():
    """Silent finders if available, else empty stubs. Second value says whether it is present."""
    mm, ri = load_claimproof()
    if mm is None or ri is None:
        return _EmptyFinder, _EmptyFinder, False
    return mm, ri, True


def selftest() -> int:
    # The loader must never raise, whether or not the companion is installed, and must report a
    # consistent presence flag.
    ok = True
    mm, ri, present = claimproof_finders()
    if mm.raw_findings(".") != [] and not present:
        print("FAIL: absent companion should find nothing"); ok = False
    if present:
        # if it claims present, its finders must actually be callable
        try:
            mm.raw_findings(os.path.dirname(__file__))
            ri.raw_findings(os.path.dirname(__file__))
        except Exception as e:
            print("FAIL: present companion finders not callable ->", e); ok = False
    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(selftest())
