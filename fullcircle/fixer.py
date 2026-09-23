#!/usr/bin/env python3
# CALLED BY: SANDBOX-FAN-OUT (corral) as its per-agent fix engine, and the orchestrator's fixer hook.
# FIRES WHEN: applying fixes to located defects in a system SANDBOX-FAN-OUT was dropped into.
"""SANDBOX-FAN-OUT's safe fix engine (Chris, 2026-09-23: "a bunch of checks and balances that would
make this actually function in a system it is just dropped into").

The eight checks-and-balances, all mechanical here:

  1 ISOLATED CLONE        every fix is tried on a throwaway copy; the live system is never touched
                          until a fix is verified.
  2 SINGLE-WRITER MERGE   only one writer applies verified fixes back; parallel agents cannot collide.
  3 DISJOINT WORK         findings are de-duplicated by identity so no two agents fix the same thing.
  4 VERIFY BOTH DIRECTIONS after a fix, re-run the finder: the target finding must DISAPPEAR *and*
                          no NEW finding may appear.
  5 BEHAVIOURAL TARGETING a fix is located by the finding's structural signal, never a fixed path.
  6 ROLLBACK ON REGRESSION any fix that fails verification is discarded; the clone is thrown away.
  7 MODEL-AGNOSTIC        the patch itself comes from a pluggable provider -- a mechanical Python
                          patch for a known class, or a model (with or without Fable). The engine
                          does not care which produced it.
  8 DRY-RUN FIRST         with dry_run=True nothing on the real target changes; it reports the plan.

Only CORROBORATED, high-confidence findings are auto-fixed here; everything else went to the
orchestrator's human-review queue. This engine is what makes that safe.
"""
from __future__ import annotations

import os
import shutil
import tempfile

try:
    from .finding import Triangulated
except ImportError:
    from finding import Triangulated  # type: ignore

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
    """findings: list[Triangulated]. patch_provider(finding, clone_dir)->bool applies a change to the
    clone. finder(dir)->list[Triangulated] re-detects, for verification."""
    # check 3: disjoint -- one attempt per identity, highest-trust first
    seen, queue = set(), []
    for t in sorted(findings, key=lambda t: (t.corroboration, t.max_confidence), reverse=True):
        if t.identity in seen:
            continue
        seen.add(t.identity)
        if require_corroborated and t.trust == "single-method":
            continue
        if t.max_confidence < min_confidence:
            continue
        queue.append(t)

    staged, results = [], []
    for t in queue:
        clone = tempfile.mkdtemp(prefix="sfo_fix_")
        try:
            # check 1: isolated clone
            shutil.copytree(root, os.path.join(clone, "t"))
            work = os.path.join(clone, "t")
            before = {x.identity for x in finder(work)}
            applied = False
            try:
                applied = bool(patch_provider(t, work))       # check 7: pluggable, model-agnostic
            except Exception as e:
                results.append((t.identity, "patch-error", str(e)[:80])); continue
            if not applied:
                results.append((t.identity, "no-patch", "provider produced no change")); continue
            after = {x.identity for x in finder(work)}
            # check 4 (both directions) + check 6 (rollback)
            if t.identity in after:
                results.append((t.identity, "rolled-back", "fix did not remove the finding")); continue
            introduced = after - (before - {t.identity})
            if introduced:
                results.append((t.identity, "rolled-back",
                                "fix introduced %d new finding(s)" % len(introduced))); continue
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
        owner: dict[str, str] = {}
        for ident, changed, deleted in staged:
            conflict = False
            for rel, b in changed.items():
                if rel in planned and planned[rel] != b:
                    conflicts.append((ident, rel)); conflict = True; break
            if conflict:
                continue
            for rel, b in changed.items():
                planned[rel] = b; owner[rel] = ident
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
                   else "Applied %d fix(es); %d conflict(s) held back." % (len(applied_ids), len(conflicts)),
    }


# ---------------------------------------------------------------- proof
def selftest() -> int:
    ok = True

    # a synthetic finder: a file containing the token "DEADCANARY" is a finding, keyed by path.
    def finder(root):
        try:
            from .finding import Finding, triangulate
        except ImportError:
            from finding import Finding, triangulate
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
                    rel = os.path.relpath(p, root)
                    out.append(Finding("test", "test-cannot-fail", rel, signal="marker",
                                       method="m1", confidence=0.8, both_directions_proven=True,
                                       extra={"id_key": "dc:" + rel}))
                    out.append(Finding("test", "test-cannot-fail", rel, signal="marker",
                                       method="m2", confidence=0.8, both_directions_proven=True,
                                       extra={"id_key": "dc:" + rel}))
        return triangulate(out)

    import tempfile as _tf
    root = _tf.mkdtemp(prefix="sfo_root_")
    try:
        open(os.path.join(root, "bad.py"), "w").write("# DEADCANARY here\nx = 1\n")
        findings = finder(root)
        if not findings or findings[0].trust != "corroborated":
            print("FAIL: setup -- finding should be corroborated ->", findings); ok = False

        # a GOOD provider removes the marker -> verified
        def good(t, work):
            p = os.path.join(work, t.location)
            open(p, "w").write(open(p).read().replace("DEADCANARY", "real_assert()"))
            return True

        # DRY RUN: nothing on the real root changes
        rep = apply_fixes(root, findings, good, finder, dry_run=True)
        if len(rep["verified"]) != 1:
            print("FAIL: good fix should verify ->", rep["results"]); ok = False
        if "DEADCANARY" not in open(os.path.join(root, "bad.py")).read():
            print("FAIL: dry-run modified the real target"); ok = False

        # WET RUN: the fix is applied via single-writer merge
        rep2 = apply_fixes(root, findings, good, finder, dry_run=False)
        if len(rep2["applied"]) != 1:
            print("FAIL: wet run should apply 1 ->", rep2); ok = False
        if "DEADCANARY" in open(os.path.join(root, "bad.py")).read():
            print("FAIL: wet run did not actually fix the file"); ok = False
        # and re-running the finder now returns nothing (the fix really worked)
        if finder(root):
            print("FAIL: finding still present after applied fix"); ok = False
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # ROLLBACK: a provider that introduces a NEW finding must be rolled back, target untouched
    root2 = _tf.mkdtemp(prefix="sfo_root2_")
    try:
        open(os.path.join(root2, "bad.py"), "w").write("# DEADCANARY one\n")
        findings = finder(root2)

        def bad(t, work):
            p = os.path.join(work, t.location)
            open(p, "w").write("x = 1\n")                       # removes this one...
            open(os.path.join(work, "new.py"), "w").write("# DEADCANARY two\n")  # ...adds another
            return True

        rep = apply_fixes(root2, findings, bad, finder, dry_run=False)
        if len(rep["rolled_back"]) != 1 or rep["applied"]:
            print("FAIL: regressing fix must roll back ->", rep); ok = False
        if "DEADCANARY" not in open(os.path.join(root2, "bad.py")).read():
            print("FAIL: rolled-back fix leaked to the real target"); ok = False
        if os.path.exists(os.path.join(root2, "new.py")):
            print("FAIL: rolled-back fix leaked a new file to the target"); ok = False
    finally:
        shutil.rmtree(root2, ignore_errors=True)

    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
