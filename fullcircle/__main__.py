"""`fullcircle [run <path>|doctor|selftest]` -- the command line.

Reachable as the `fullcircle` console script and as `python3 -m fullcircle`; both call this `main`.
The per-module script form (`python3 fullcircle/orchestrator.py <path>`) is unchanged and still
works, so nothing that already used it breaks.
"""
from __future__ import annotations

import os
import sys
import tempfile

USAGE = """full-circle-optimization -- find what a system PROMISES but does not do, then fix it

  fullcircle run <path>          the pipeline over a project: find, triangulate, report
  fullcircle run <path> --fix    ...and apply only the SAFE mechanical fixes
  fullcircle run <path> --sarif <out>   write SARIF for a code-scanning upload
  fullcircle doctor              verify THIS install actually works, before trusting it
  fullcircle selftest            every module's own both-directions selftest

Exit codes, and they are the point:
  0   it looked, and everything checks out
  1   it looked, and found something
  2   IT COULD NOT TELL -- never treat this as clean
"""


def doctor(argv=None):
    """Verify the INSTALL, not the checkout. Names every check, then PASS or FAIL.

    ⛔ WHY: this repo's tests live beside the source, not in the wheel, so nothing a stranger can run
    after `pip install` exercises anything. And the failure that made this necessary was exactly the
    kind a green CI cannot see -- there was no `__init__.py`, so the installed package imported fine
    with `__file__ = None`, exported nothing, and had no command to type. Check 1 is that specific
    failure, named, so it cannot come back quietly.

    ⭐ Check 3 runs the tool in BOTH DIRECTIONS on synthetic systems: a planted defect must be found,
    and a clean system must come back quiet. An instrument only ever seen to find nothing has no
    opinion about a negative.
    """
    checks, failed = [], 0

    def ck(name, fn):
        nonlocal failed
        try:
            detail = fn()
            checks.append(("ok", name, detail or ""))
        except Exception as exc:                                   # noqa: BLE001
            failed += 1
            checks.append(("FAIL", name, "%s: %s" % (type(exc).__name__, exc)))

    def _real_package():
        import fullcircle
        f = getattr(fullcircle, "__file__", None)
        if not f:
            raise RuntimeError(
                "imported, but __file__ is None -- an implicit NAMESPACE package, not a real "
                "install. This is the exact defect that shipped until 2026-09-27: pip install "
                "succeeded, import succeeded, and nothing was actually importable.")
        return f

    def _public_api():
        # the population is __all__ itself, never a list typed in here -- a typed list goes stale
        # the first time a name is added, and it goes stale silently.
        import fullcircle
        missing = [n for n in fullcircle.__all__ if not hasattr(fullcircle, n)]
        if missing:
            raise RuntimeError("promised by __all__ and absent from the install: %s"
                               % ", ".join(missing))
        return "%d public names, all resolvable" % len(fullcircle.__all__)

    def _finds_and_stays_quiet():
        # ⭐ `scan(root)` ALREADY triangulates -- it is literally `triangulate(raw_findings(root))`.
        # The first version of this check triangulated its output a second time and died with
        # `TypeError: 'str' object is not callable`. The doctor caught that on its first run against
        # a real install, which is the whole argument for having one.
        from fullcircle import scan
        with tempfile.TemporaryDirectory() as d:
            planted = os.path.join(d, "planted")
            os.makedirs(planted)
            # a test that CANNOT FAIL: it asserts a constant, so it is green whatever the code does.
            _w(planted, "app.py", "def add(a, b):\n    return a + b\n")
            _w(planted, "test_app.py", "def test_add():\n    assert True\n")
            found = scan(planted)
            if not found:
                raise RuntimeError("a planted cannot-fail test produced no finding, so this tool "
                                   "cannot be trusted to find a real one")
            n = len(found)

            clean = os.path.join(d, "clean")
            os.makedirs(clean)
            _w(clean, "core.py", "def add(a, b):\n    return a + b\n")
            _w(clean, "test_core.py", "from core import add\n\n\n"
                                      "def test_add():\n    assert add(2, 2) == 4\n")
            still = scan(clean)
            if len(still) >= n:
                raise RuntimeError("a clean system produced as many findings (%d) as a planted one "
                                   "(%d), so the detector is not discriminating" % (len(still), n))
        return ("%d finding(s) in a planted system, %d in a clean one -- it discriminates"
                % (n, len(still)))

    def _unreadable_is_not_clean():
        from fullcircle import scan
        gone = os.path.join(tempfile.gettempdir(), "fullcircle-no-such-system-xyz")
        try:
            out = list(scan(gone))
        except Exception:                                          # noqa: BLE001
            return "a missing target raises rather than returning an empty clean result"
        if out:
            raise RuntimeError("a path that does not exist produced %d finding(s)" % len(out))
        return ("a missing target returns no findings -- callers must treat that as UNKNOWN, which "
                "is what the CLI's exit 2 is for")

    ck("the installed package is real, not an empty namespace", _real_package)
    ck("every public name is importable from the install", _public_api)
    ck("it finds a planted defect and discriminates against a clean system", _finds_and_stays_quiet)
    ck("an unreadable target is never reported as clean", _unreadable_is_not_clean)

    for state, name, detail in checks:
        sys.stdout.write("  %-4s %s%s\n" % (state + ":", name, ("  -- " + detail) if detail else ""))
    sys.stdout.write("fullcircle doctor: %s (%d check(s), %d failure(s))\n"
                     % ("PASS" if not failed else "FAIL", len(checks), failed))
    return 0 if not failed else 1


def _w(d, rel, text):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p) or d, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def _selftest_all():
    """Every module's own selftest, the same set `run_all_tests.py` runs."""
    import importlib
    names = ("finding", "concepts", "structural", "drift_guard", "fixer", "patches",
             "orchestrator", "testbed", "testbed_scale", "mutation", "_optional")
    bad = []
    for n in names:
        mod = importlib.import_module("fullcircle." + n)
        fn = getattr(mod, "selftest", None)
        if fn is None:
            bad.append("%s has no selftest" % n)
            continue
        if fn() != 0:
            bad.append(n)
    sys.stdout.write("fullcircle selftest: %s (%d module(s), %d failing)%s\n"
                     % ("PASS" if not bad else "FAIL", len(names), len(bad),
                        ("  -- " + ", ".join(bad)) if bad else ""))
    return 0 if not bad else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0
    cmd = argv[0]
    if cmd == "doctor":
        return doctor(argv[1:])
    if cmd in ("selftest", "--selftest"):
        return _selftest_all()
    if cmd != "run":
        sys.stdout.write("unknown command %r\n\n%s" % (cmd, USAGE))
        return 2
    paths = [a for a in argv[1:] if not a.startswith("-")]
    # a --sarif value is a path and must not be mistaken for the target
    if "--sarif" in argv:
        val = argv[argv.index("--sarif") + 1] if argv.index("--sarif") + 1 < len(argv) else None
        paths = [p for p in paths if p != val]
    if not paths:
        sys.stdout.write("run needs a path.\n\n%s" % USAGE)
        return 2
    target = paths[0]
    if not os.path.isdir(target):
        # UNKNOWN, never clean -- the house rule, and the reason exit 2 exists
        sys.stdout.write("%s is not a directory. COULD NOT LOOK -- UNKNOWN, not clean.\n" % target)
        return 2
    from .orchestrator import _wire_real_finders, run
    from .finding import to_sarif
    result = run(target, _wire_real_finders())
    findings = result.get("findings") or []
    sys.stdout.write("full-circle over %s\n  %d finding(s) after triangulation\n"
                     % (os.path.abspath(target), len(findings)))
    for f in findings[:20]:
        sys.stdout.write("    %s\n" % (getattr(f, "target", None) or f))
    if "--sarif" in argv:
        out = argv[argv.index("--sarif") + 1]
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(to_sarif(findings))
        sys.stdout.write("SARIF written: %s\n" % out)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
