#!/usr/bin/env python3
# CALLED BY: the package __init__ that exports apply_fixes, and the `fix` command.
# FIRES WHEN: a located defect is repaired in a system this tool was dropped into.
"""The safe fix engine: the checks and balances that let a fix be applied to somebody else's
system without breaking it.

Finding a defect and repairing one are different jobs with different risks. A finder that is
wrong costs you a wasted look. **A fixer that is wrong costs you your codebase** -- so every
property below exists to make a bad fix impossible to land, rather than unlikely.

  1 ISOLATED CLONE         every fix is tried on a throwaway copy; the real system is not touched
                           until the fix is verified.
  2 SINGLE-WRITER MERGE    one writer applies verified fixes back, so parallel agents cannot
                           collide even when two of them touch the same file.
  3 DISJOINT WORK          findings are de-duplicated by identity, so no two agents spend effort
                           fixing the same thing.
  4 VERIFY BOTH DIRECTIONS after a fix, the finder runs again: the target finding must DISAPPEAR
                           *and* no NEW finding may appear. Half of that test is the half people
                           skip, and it is the half that catches a "fix" that broke something else.
  5 BEHAVIOURAL TARGETING  a fix is located by the finding's own signal, never by a hard-coded
                           path -- so it still works in a system laid out differently from yours.
  6 ROLLBACK ON REGRESSION any fix that fails verification is discarded with its clone. Nothing
                           partially-applied is ever left behind.
  7 MODEL-AGNOSTIC         the patch comes from a pluggable provider: a mechanical Python patch
                           for a known class, or a model for anything else. The engine does not
                           care which produced it, and does not trust either one.
  8 DRY-RUN FIRST          the default. With `dry_run=True` nothing on the real target changes and
                           the report says what WOULD happen.

⭐ ITS CANONICAL HOME IS `sandbox-fan-out`, AND THAT IS WORTH SAYING OUT LOUD BECAUSE IT WAS
WRONG FOR A WHILE. This file spent its first days in a sibling repository while its own header
read "the SANDBOX-FAN-OUT role" -- built correctly, filed in the wrong place. Repairing what
another tool located is sandbox-fan-out's entire job, so that is where the definition lives.

⚠ AND THE SECOND COPY IS DELIBERATE, NOT AN ACCIDENT. `full-circle-optimization` composes the
finders and this fixer into one pipeline, and every one of these tools has to `pip install` and
work ALONE -- so it carries a copy rather than depending on a package a stranger may not have.
The two are kept BYTE-IDENTICAL by `fullcircle/drift_guard.py`, which lists this file as a shared
contract: edit one and the guard fails until the other matches. Two copies of one definition is
only a defect when nothing notices them diverging.

## What a "finding" has to look like

The engine is deliberately DUCK-TYPED and imports no defect model, so it works with any finder --
this project's, a sibling tool's, or your own. A finding is any object carrying:

    .identity        a stable, hashable id for the defect. Two findings of the SAME defect must
                     compare equal, or check 3 cannot de-duplicate and check 4 cannot tell
                     whether the defect went away.
    .location        where to apply the patch, relative to the root. Your patch provider decides
                     what it means; the engine only hands it back to you.
    .corroboration   how many independent methods found it (int). Higher is attempted first.
    .max_confidence  0.0-1.0.
    .trust           "corroborated" when more than one method agrees. Anything else is only
                     attempted if you pass require_corroborated=False.

⛔ THE TWO DEFAULTS ARE THE SAFETY STORY, AND BOTH ARE TESTED BY MUTATION. `dry_run=True` means a
call that forgets the keyword reports a plan instead of writing to a live system, and
`require_corroborated=True` means a defect only one method believes in is never auto-repaired.
If either default ever flips, the selftest fails rather than the user's repository.
"""
from __future__ import annotations

import os
import shutil
import tempfile

_SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv"}


def _snapshot(root: str) -> dict[str, bytes]:
    files = {}
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP]
        for f in fs:
            p = os.path.join(dp, f)
            try:
                files[os.path.relpath(p, root)] = open(p, "rb").read()
            except OSError:
                pass
    return files


def _diff(before: dict[str, bytes], after: dict[str, bytes]):
    """(changed_or_added {rel: bytes}, deleted [rel])."""
    changed = {r: b for r, b in after.items() if before.get(r) != b}
    deleted = [r for r in before if r not in after]
    return changed, deleted


def apply_fixes(root, findings, patch_provider, finder, *, dry_run=True,
                min_confidence=0.6, require_corroborated=True) -> dict:
    """Repair located defects safely. Returns a report; writes nothing unless dry_run=False.

    root            the system to repair.
    findings        objects carrying the attributes documented at the top of this module.
    patch_provider  patch_provider(finding, clone_dir) -> bool. Applies ONE change inside the
                    clone and says whether it changed anything. It may be mechanical or a model.
    finder          finder(dir) -> findings. Run again after each patch, to verify BOTH
                    directions. This is what makes a wrong fix impossible to land.
    """
    # check 3: disjoint -- one attempt per identity, highest-trust first
    seen, queue = set(), []
    for t in sorted(findings, key=lambda t: (t.corroboration, t.max_confidence), reverse=True):
        if t.identity in seen:
            continue
        seen.add(t.identity)
        if require_corroborated and t.trust != "corroborated":
            continue
        if t.max_confidence < min_confidence:
            continue
        queue.append(t)

    staged, results = [], []
    for t in queue:
        clone = tempfile.mkdtemp(prefix="corral_fix_")
        try:
            # check 1: isolated clone
            shutil.copytree(root, os.path.join(clone, "t"))
            work = os.path.join(clone, "t")
            before = {x.identity for x in finder(work)}
            applied = False
            try:
                applied = bool(patch_provider(t, work))       # check 7: pluggable, model-agnostic
            except Exception as e:
                results.append((t.identity, "patch-error", str(e)[:80]))
                continue
            if not applied:
                results.append((t.identity, "no-patch", "provider produced no change"))
                continue
            after = {x.identity for x in finder(work)}
            # check 4 (both directions) + check 6 (rollback)
            if t.identity in after:
                results.append((t.identity, "rolled-back", "fix did not remove the finding"))
                continue
            introduced = after - (before - {t.identity})
            if introduced:
                results.append((t.identity, "rolled-back",
                                "fix introduced %d new finding(s)" % len(introduced)))
                continue
            changed, deleted = _diff(_snapshot(root), _snapshot(work))
            staged.append((t.identity, changed, deleted))
            results.append((t.identity, "verified", "%d file(s) changed, %d deleted"
                            % (len(changed), len(deleted))))
        finally:
            shutil.rmtree(clone, ignore_errors=True)

    # check 2: single-writer merge -- detect conflicts, then one writer applies
    applied_ids, conflicts = [], []
    if not dry_run:
        planned: dict[str, bytes] = {}
        for ident, changed, deleted in staged:
            conflict = False
            for rel, b in changed.items():
                if rel in planned and planned[rel] != b:
                    conflicts.append((ident, rel))
                    conflict = True
                    break
            if conflict:
                continue
            for rel, b in changed.items():
                planned[rel] = b
            applied_ids.append((ident, changed, deleted))
        for ident, changed, deleted in applied_ids:
            for rel, b in changed.items():
                p = os.path.join(root, rel)
                os.makedirs(os.path.dirname(p) or root, exist_ok=True)
                open(p, "wb").write(b)
            for rel in deleted:
                try:
                    os.remove(os.path.join(root, rel))
                except OSError:
                    pass

    return {
        "considered": len(findings), "attempted": len(queue),
        "verified": [r for r in results if r[1] == "verified"],
        "rolled_back": [r for r in results if r[1] == "rolled-back"],
        "results": results,
        "applied": [i for i, _, _ in applied_ids] if not dry_run else [],
        "conflicts": conflicts,
        "dry_run": dry_run,
        "message": ("DRY RUN: %d verified fix(es) staged, not applied. Re-run with dry_run=False "
                    "to merge." % len([r for r in results if r[1] == "verified"])) if dry_run
                   else "Applied %d fix(es); %d conflict(s) held back."
                        % (len(applied_ids), len(conflicts)),
    }


# ─────────────────────────────── the proof ───────────────────────────────
# ⛔ A LOCAL STUB, NOT AN IMPORT. The engine is duck-typed on purpose, so its own proof must not
# reach for another project's defect model -- if it did, this project would quietly depend on that
# one, and the "works with any finder" claim would be untested.

class _Found:
    """The smallest thing the engine accepts, so the duck-typing is exercised rather than assumed."""

    def __init__(self, identity, location, corroboration=2, max_confidence=0.8,
                 trust="corroborated"):
        self.identity = identity
        self.location = location
        self.corroboration = corroboration
        self.max_confidence = max_confidence
        self.trust = trust

    def __repr__(self):
        return "_Found(%r, trust=%s)" % (self.identity, self.trust)


def _marker_finder(root):
    """A file containing the token DEADCANARY is a defect, keyed by its relative path."""
    out = []
    for dp, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP]
        for f in fs:
            p = os.path.join(dp, f)
            try:
                txt = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if "DEADCANARY" in txt:
                # forward slashes always: a path used as an IDENTITY must not change spelling
                # between platforms, or the same defect reads as two on Windows
                rel = os.path.relpath(p, root).replace(os.sep, "/")
                out.append(_Found("dc:" + rel, rel))
    return out


def selftest() -> int:
    ok = True

    def say(cond, msg, extra=""):
        nonlocal ok
        if not cond:
            ok = False
            print("FAIL: %s %s" % (msg, extra))
        else:
            print("  ok:   %s" % msg)

    def good(t, work):
        p = os.path.join(work, t.location)
        open(p, "w").write(open(p).read().replace("DEADCANARY", "real_assert()"))
        return True

    root = tempfile.mkdtemp(prefix="corral_root_")
    try:
        open(os.path.join(root, "bad.py"), "w").write("# DEADCANARY here\nx = 1\n")
        findings = _marker_finder(root)
        say(len(findings) == 1, "setup: one corroborated finding", findings)

        rep = apply_fixes(root, findings, good, _marker_finder, dry_run=True)
        say(len(rep["verified"]) == 1, "a good fix VERIFIES against the re-run finder", rep["results"])
        say("DEADCANARY" in open(os.path.join(root, "bad.py")).read(),
            "GUARD: a dry run does not touch the real target")

        rep2 = apply_fixes(root, findings, good, _marker_finder, dry_run=False)
        say(len(rep2["applied"]) == 1, "a wet run applies through the single writer", rep2)
        say("DEADCANARY" not in open(os.path.join(root, "bad.py")).read(),
            "and the real file is actually repaired")
        say(not _marker_finder(root), "the finder now finds nothing -- the repair really worked")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # a fix that introduces a NEW defect must be rolled back, target untouched
    root2 = tempfile.mkdtemp(prefix="corral_root2_")
    try:
        open(os.path.join(root2, "bad.py"), "w").write("# DEADCANARY one\n")
        findings = _marker_finder(root2)

        def bad(t, work):
            p = os.path.join(work, t.location)
            open(p, "w").write("x = 1\n")                                      # removes this one
            open(os.path.join(work, "new.py"), "w").write("# DEADCANARY two\n")  # ...adds another
            return True

        rep = apply_fixes(root2, findings, bad, _marker_finder, dry_run=False)
        say(len(rep["rolled_back"]) == 1 and not rep["applied"],
            "MUST FIRE: a fix that introduces a new defect is ROLLED BACK", rep)
        say("DEADCANARY" in open(os.path.join(root2, "bad.py")).read(),
            "and the rolled-back fix did not leak to the real target")
        say(not os.path.exists(os.path.join(root2, "new.py")),
            "and it did not leak a new file either")
    finally:
        shutil.rmtree(root2, ignore_errors=True)

    # a fix that does not remove the defect is rolled back too
    root3 = tempfile.mkdtemp(prefix="corral_root3_")
    try:
        open(os.path.join(root3, "bad.py"), "w").write("# DEADCANARY three\n")
        f3 = _marker_finder(root3)

        def useless(t, work):
            p = os.path.join(work, t.location)
            open(p, "a").write("# a comment that fixes nothing\n")
            return True

        rep = apply_fixes(root3, f3, useless, _marker_finder, dry_run=False)
        say(len(rep["rolled_back"]) == 1, "MUST FIRE: a fix that does not remove the defect", rep)
    finally:
        shutil.rmtree(root3, ignore_errors=True)

    # a provider that raises is recorded, not crashed on
    root4 = tempfile.mkdtemp(prefix="corral_root4_")
    try:
        open(os.path.join(root4, "bad.py"), "w").write("# DEADCANARY four\n")

        def boom(t, work):
            raise RuntimeError("provider exploded")

        rep = apply_fixes(root4, _marker_finder(root4), boom, _marker_finder, dry_run=False)
        say(any(r[1] == "patch-error" for r in rep["results"]),
            "MUST FIRE: a provider that raises is recorded as patch-error", rep["results"])
    finally:
        shutil.rmtree(root4, ignore_errors=True)

    # THE TWO DEFAULTS, killed by mutation rather than trusted
    r5 = tempfile.mkdtemp(prefix="corral_dflt_")
    try:
        p5 = os.path.join(r5, "bad.py")
        open(p5, "w").write("# DEADCANARY five\n")
        rep = apply_fixes(r5, _marker_finder(r5), good, _marker_finder)   # NO dry_run kwarg
        say(rep["dry_run"] is True, "dry_run DEFAULTS to True", rep["dry_run"])
        say("DEADCANARY" in open(p5).read(),
            "so a call that forgets the keyword does not write to a live system")
    finally:
        shutil.rmtree(r5, ignore_errors=True)

    r6 = tempfile.mkdtemp(prefix="corral_dflt2_")
    try:
        open(os.path.join(r6, "bad.py"), "w").write("# DEADCANARY six\n")
        single = [_Found("dc:bad.py", "bad.py", corroboration=1, max_confidence=0.9,
                         trust="single-method")]
        rep = apply_fixes(r6, single, good, _marker_finder, dry_run=False)
        say(rep["attempted"] == 0 and not rep["applied"],
            "require_corroborated DEFAULTS to True, so a one-method defect is NOT auto-fixed", rep)
    finally:
        shutil.rmtree(r6, ignore_errors=True)

    # and a below-threshold confidence is skipped
    r7 = tempfile.mkdtemp(prefix="corral_conf_")
    try:
        open(os.path.join(r7, "bad.py"), "w").write("# DEADCANARY seven\n")
        weak = [_Found("dc:bad.py", "bad.py", max_confidence=0.2)]
        rep = apply_fixes(r7, weak, good, _marker_finder, dry_run=False)
        say(rep["attempted"] == 0, "a finding below min_confidence is not attempted", rep)
    finally:
        shutil.rmtree(r7, ignore_errors=True)

    print("SELFTEST: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(selftest())
