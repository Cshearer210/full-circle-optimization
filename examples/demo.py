#!/usr/bin/env python3
"""A self-contained, runnable demo of the full-circle-optimization pipeline.

It builds a tiny throwaway project with a handful of KNOWN defects plus clean controls, runs the
real pipeline over it (the structural finder, plus the companion silent-defect finder if it is
installed), and prints what it found: which findings are corroborated by two independent methods
(trustworthy enough to auto-fix), which are single-method leads routed to a human, and a SARIF
summary. Nothing here is mocked -- it calls the same code the CLI does.

    python3 examples/demo.py

Exit code is 0 (the demo always builds the same target); it is a demonstration, not a test. Run
`python3 run_all_tests.py` for the pass/fail proof.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fullcircle import orchestrator  # noqa: E402


def _w(root, rel, body):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p) or root, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(body)


def build_target(root):
    """Plant defects the structural finder catches, plus clean controls it must leave alone."""
    # DEFECT: the same real logic at two paths -- fix one, miss the other (second-door duplicate)
    dup = "def block():\n    return 'a real block worth keeping exactly once'\nblock()\n"
    _w(root, "core/handler_a.py", dup)
    _w(root, "legacy/handler_b.py", dup)

    # DEFECT: one constant, two different values in two files (conflicting definition)
    _w(root, "conf/a.py", "RETRY_LIMIT = 5\n")
    _w(root, "conf/b.py", "RETRY_LIMIT = 'five'\n")

    # DEFECT: a function defined and complete that nothing anywhere calls (unwired)
    _w(root, "core/orphan.py", "def compute_rebate(order):\n    return order * 0.1\n")

    # DEFECT: a stub other code already calls as if it were done
    _w(root, "core/pay.py",
       "def settle_invoice(inv):\n    raise NotImplementedError\nsettle_invoice(1)\n")

    # CONTROL: a real, fully-wired helper -- must NOT be flagged
    _w(root, "core/util.py",
       "def _double(x):\n    return x * 2\ndef run():\n    return _double(21)\nrun()\n")


def main():
    root = tempfile.mkdtemp(prefix="fco_demo_")
    try:
        build_target(root)
        finders = orchestrator._wire_real_finders()
        companion = " + companion silent finder" if len(finders) > 1 else " (structural only)"
        print("full-circle-optimization demo")
        print("target: a generated project with 4 planted defects + 1 clean control")
        print("finders wired: %d%s\n" % (len(finders), companion))

        rep = orchestrator.run(root, finders)

        for rd in rep["rounds"]:
            print("round %(round)d: %(total)d findings  %(corroborated)d corroborated  "
                  "%(auto_fixable)d auto-fixable  %(needs_human)d need a human" % rd)

        print("\nCORROBORATED (>=2 independent methods -> safe to auto-fix):")
        auto = rep["auto_fixable"]
        for t in auto:
            print("  [%s] %-24s %s  via %s"
                  % (t.trust, t.defect_class, t.location[:46], ",".join(t.methods)))
        if not auto:
            print("  (none)")

        print("\nHUMAN-REVIEW QUEUE (single-method leads or judgment calls):")
        review = rep["human_review_queue"]
        for t in review:
            print("  [%s] %-24s %s  via %s"
                  % (t.trust, t.defect_class, t.location[:46], ",".join(t.methods)))
        if not review:
            print("  (none)")

        out = os.path.join(root, "findings.sarif")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(rep["sarif"], fh, indent=2)
        n_results = len(rep["sarif"]["runs"][0]["results"])
        print("\nSARIF %s written with %d result(s) (drop-in for GitHub code scanning)."
              % (rep["sarif"]["version"], n_results))
        print(rep["message"])
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
