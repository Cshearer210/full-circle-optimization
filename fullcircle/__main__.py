"""`fullcircle [run <path>|doctor|selftest]` -- the command line.

Reachable as the `fullcircle` console script and as `python3 -m fullcircle`; both go through `cli`,
which is `main` wrapped so an internal crash exits 2 (COULD NOT TELL) instead of 1, which is this
tool's code for "found something". `main` itself stays exception-transparent, for the tests.
The per-module script form (`python3 fullcircle/orchestrator.py <path>`) is unchanged and still
works, so nothing that already used it breaks.
"""
from __future__ import annotations

import json
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
    # ⛔ THE ROOT CAUSE OF THE MISSING --fix, FIXED HERE RATHER THAN ONLY ITS INSTANCE. This CLI
    # hand-parses argv, so ANY flag it does not implement was silently accepted and ignored -- and
    # an ignored flag is indistinguishable from a working one. `--fix` was advertised and
    # unimplemented for as long as it was precisely because nothing objected. A typo
    # (`--sarfi`, `--fx`) had the same shape: the command looked like it obeyed you.
    # ⭐ Exit 2, not 1: being handed an instruction this build cannot carry out is COULD-NOT-TELL,
    # never a clean or a finding.
    KNOWN_FLAGS = {"--fix", "--sarif"}
    unknown = [a for a in argv[1:] if a.startswith("-") and a not in KNOWN_FLAGS]
    if unknown:
        sys.stdout.write("unknown flag(s) %s -- this build does not implement them, so it will not"
                         " pretend to. COULD NOT DO WHAT YOU ASKED -- UNKNOWN, not clean.\n\n%s"
                         % (", ".join(unknown), USAGE))
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
    from .orchestrator import _wire_real_finders, build_fixer_hook, run
    from .finding import to_sarif
    finders = _wire_real_finders()
    # ⛔ THE FLAG THIS LINE READS WAS ADVERTISED AND UNIMPLEMENTED UNTIL 2026-09-28. The usage text
    # above has promised `--fix` since this CLI was written; this function never looked for it, so
    # the INSTALLED command parsed it nowhere, repaired nothing, warned nobody, and exited 1 as
    # though it had worked. The working hook existed the whole time, reachable only as
    # `python3 -m fullcircle.orchestrator <path> --fix`, which no document mentions.
    # Caught by sandbox-fan-out's `proving-ground/composed_run.py`, which plants a function
    # referenced by nothing and asks the two harder questions: did the dead one GO, did the live
    # ones STAY. Neither module's own selftest could see it -- the wiring was the missing piece.
    want_fix = "--fix" in argv
    result = run(target, finders, fixer=build_fixer_hook(finders) if want_fix else None)
    findings = result.get("findings") or []
    sys.stdout.write("full-circle over %s\n  %d finding(s) after triangulation\n"
                     % (os.path.abspath(target), len(findings)))
    if want_fix:
        applied = sum(rd.get("fixed", 0) for rd in result.get("rounds") or [])
        auto = len(result.get("auto_fixable") or [])
        sys.stdout.write("  --fix: %d repair(s) applied and re-verified on a clone before landing;"
                         " %d finding(s) were auto-fixable\n" % (applied, auto))
        if auto and not applied:
            # ⭐ SAYING SO IS THE POINT. "0 applied" out of a non-empty auto-fixable set is either a
            # class with no mechanical patch provider or a repair rolled back because re-verifying
            # moved something else. Both are real answers; silence is what let the whole flag go
            # missing unnoticed for as long as it did.
            sys.stdout.write("         nothing landed: either no mechanical patch exists for those"
                             " classes, or a repair was rolled back by re-verification\n")
    for f in findings[:20]:
        sys.stdout.write("    %s\n" % (getattr(f, "target", None) or f))
    if "--sarif" in argv:
        out = argv[argv.index("--sarif") + 1]
        # ⛔ THIS CALL RAISED TypeError ON EVERY RUN UNTIL 2026-09-28: `to_sarif(findings)` is
        # missing the required `tool_name`, so the advertised `--sarif` flag had NEVER produced a
        # file through the installed command. It left a zero-byte file behind and Python exited 1
        # -- WHICH IS THIS CLI'S CODE FOR "found something". A crash and a successful finding were
        # the same exit code, so nothing in a CI log, a test, or a person's terminal could tell
        # them apart. That indistinguishability is the real defect; the missing argument is one
        # instance of it. See the try/except in __main__ below, which makes an internal error
        # exit 2 instead of impersonating a result.
        payload = to_sarif(findings, "full-circle-optimization")
        text = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
        wrote = os.path.getsize(out)
        if wrote == 0:
            # an empty SARIF uploads cleanly and shows a reviewer zero alerts, which reads as
            # "the tool found nothing" -- never let that pass as success
            sys.stdout.write("SARIF came out EMPTY for %d finding(s) -- refusing to call that"
                             " written. UNKNOWN, not clean.\n" % len(findings))
            return 2
        sys.stdout.write("SARIF written: %s (%d bytes, %d finding(s))\n"
                         % (out, wrote, len(findings)))
    return 1 if findings else 0


def cli(argv=None):
    """The console-script entry point: `main`, wrapped so a CRASH cannot impersonate a RESULT.

    ⛔ WHY THIS WRAPPER EXISTS, AND IT IS THE ROOT CAUSE RATHER THAN THE INSTANCE. An unhandled
    exception makes the interpreter exit 1 -- and 1 is this tool's documented code for "it looked,
    and found something". So on 2026-09-28 a TypeError inside `--sarif` produced a zero-byte file,
    printed a traceback, and exited 1: a CI job reading only the exit code, a test asserting
    "nonzero means findings", and a person skimming the terminal would each have called it a
    working run. Three outcomes need three DISTINGUISHABLE codes or there are only two.

    ⭐ 2 IS THE HONEST CODE FOR A TOOL THAT BROKE: it could not tell, which is never clean and is
    not a finding either. The traceback still prints -- suppressing it would trade one blind spot
    for another.
    """
    try:
        return main(argv)
    except SystemExit:
        raise
    except BaseException:                                    # noqa: BLE001 -- deliberately broad
        import traceback
        traceback.print_exc()
        sys.stdout.write("fullcircle FAILED INTERNALLY -- that is COULD-NOT-TELL (exit 2), not a"
                         " finding and not clean. The traceback above is the bug report.\n")
        return 2


if __name__ == "__main__":
    sys.exit(cli())
