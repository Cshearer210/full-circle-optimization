#!/usr/bin/env python3
# CALLED BY: the FULL-CIRCLE-OPTIMIZATION CLI (python -m fullcircle.orchestrator <target>).
# FIRES WHEN: running the whole portfolio as one team over a target system.
"""FULL-CIRCLE-OPTIMIZATION -- the thin linker.

It owns NO detection or fix logic. It:
  1. collects RAW findings from every finder (claimproof silent + FULL-RESET-GRAPH structural),
  2. TRIANGULATES them together so a defect two DIFFERENT TOOLS find corroborates (the reliability
     story: overlapping methods across tools, not just within one),
  3. runs at most 2 ROUNDS (cap at 2, then re-run later when there is new data),
  4. routes judgment items -- conflicts, laws/rules, single-method leads -- to a HUMAN-REVIEW QUEUE
     rather than auto-fixing them (a human eye at each stage),
  5. emits one aggregate SARIF + a run report.

A finder is any callable(root) -> list[Finding]. In production the two real finders are wired in
main(); the loop/cap/queue logic is proven here with synthetic finders so it is testable in
isolation. Fixing between rounds is SANDBOX-FAN-OUT's job; the orchestrator calls a fixer hook if
one is supplied, else it simply re-finds (and converges when nothing new appears).
"""
from __future__ import annotations

try:
    from .finding import Finding, triangulate, to_sarif, Triangulated
except ImportError:
    from finding import Finding, triangulate, to_sarif, Triangulated  # type: ignore

# defect classes that a human must rule on, never a bot (conflicts/rules need a human eye)
JUDGMENT_CLASSES = {"conflicting-definition", "conflicting-instruction", "law-or-rule-change"}


def _partition(tri: list[Triangulated]):
    """Split findings into auto-fixable (corroborated, mechanical) and human-review (judgment or a
    single-method lead that is not yet trustworthy enough to fix on an unfamiliar system)."""
    auto, review = [], []
    for t in tri:
        if t.defect_class in JUDGMENT_CLASSES or t.trust != "corroborated":
            review.append(t)
        else:
            auto.append(t)
    return auto, review


def run(root, finders, fixer=None, max_rounds=2) -> dict:
    """Run the pipeline. `finders`: list of callable(root)->list[Finding]. `fixer`: optional
    callable(list[Triangulated], root)->int applied between rounds (SANDBOX-FAN-OUT in production)."""
    rounds = []
    seen: set[str] = set()
    last_tri: list[Triangulated] = []
    for r in range(1, max_rounds + 1):
        raw: list[Finding] = []
        for f in finders:
            raw.extend(f(root))
        tri = triangulate(raw)                       # cross-repo triangulation happens HERE
        last_tri = tri
        ids = {t.identity for t in tri}
        new = ids - seen
        seen |= ids
        auto, review = _partition(tri)
        fixed = 0
        if fixer and auto:
            fixed = fixer(auto, root)                # SANDBOX-FAN-OUT applies verified fixes
        rounds.append({
            "round": r, "total": len(tri), "new": len(new),
            "corroborated": sum(1 for t in tri if t.trust == "corroborated"),
            "auto_fixable": len(auto), "needs_human": len(review), "fixed": fixed,
        })
        if r > 1 and not new and not fixed:
            break                                    # converged: nothing new and nothing fixed
    auto, review = _partition(last_tri)
    return {
        "target": root,
        "rounds": rounds,
        "findings": last_tri,
        "human_review_queue": review,
        "auto_fixable": auto,
        "sarif": to_sarif(last_tri, "full-circle-optimization"),
        "message": ("Ran %d round(s), capped at %d; re-run later once the code has changed. "
                    "%d item(s) need a human decision."
                    % (len(rounds), max_rounds, len(review))),
    }


# ---------------------------------------------------------------- proof
def selftest() -> int:
    ok = True

    # synthetic finders: finder1 and finder2 each find a shared defect S by a DIFFERENT method
    # (cross-repo corroboration), plus one unique single-method lead each.
    def f1(root):
        return [Finding("gate", "no-clean-without-looking", "g.py:1", signal="s", method="ast",
                        both_directions_proven=True, extra={"id_key": "S"}),
                Finding("wire", "function-unwired", "u.py:2", signal="s", method="no-call-edge")]

    def f2(root):
        return [Finding("gate", "no-clean-without-looking", "g.py:1", signal="s", method="mutation",
                        both_directions_proven=True, extra={"id_key": "S"}),
                Finding("definition", "conflicting-definition", "c.py:3", signal="s",
                        method="constant-conflict", both_directions_proven=True,
                        extra={"id_key": "conflict:X"})]

    rep = run("/fake", [f1, f2])

    # 1. the shared defect is corroborated ACROSS the two finders
    shared = [t for t in rep["findings"] if t.defect_class == "no-clean-without-looking"]
    if not shared or shared[0].corroboration != 2:
        print("FAIL: cross-repo corroboration missing ->", shared); ok = False

    # 2. two rounds ran, and round 2 added nothing new (converged; no fixer)
    if len(rep["rounds"]) != 2 or rep["rounds"][1]["new"] != 0:
        print("FAIL: expected 2 rounds, 0 new in round 2 ->", rep["rounds"]); ok = False

    # 3. the conflicting-definition (judgment) and the single-method lead go to human review
    rq_classes = {t.defect_class for t in rep["human_review_queue"]}
    if "conflicting-definition" not in rq_classes:
        print("FAIL: conflict not routed to human review ->", rq_classes); ok = False
    if not any(t.defect_class == "function-unwired" for t in rep["human_review_queue"]):
        print("FAIL: single-method lead not routed to human review"); ok = False

    # 4. the corroborated gate is auto-fixable, NOT in the human queue
    if any(t.defect_class == "no-clean-without-looking" for t in rep["human_review_queue"]):
        print("FAIL: a corroborated mechanical finding was sent to human review"); ok = False
    if not any(t.defect_class == "no-clean-without-looking" for t in rep["auto_fixable"]):
        print("FAIL: corroborated finding not marked auto-fixable"); ok = False

    # 5. a fixer that clears everything makes round 2 converge with fixed>0 then stop
    def fixer(auto, root):
        return len(auto)
    rep2 = run("/fake", [f1, f2], fixer=fixer)
    if rep2["rounds"][0]["fixed"] < 1:
        print("FAIL: fixer not invoked ->", rep2["rounds"]); ok = False

    # 6. SARIF is well-formed
    if rep["sarif"]["version"] != "2.1.0" or "runs" not in rep["sarif"]:
        print("FAIL: bad SARIF"); ok = False

    # 7. the per-round `corroborated` count reflects TRUST (only >=2-method findings), not a miscount.
    #    Round 1 has exactly one corroborated finding (the shared S); the unwired lead and the
    #    conflict are single-method. (kills L67  t.trust != "single-method" -> ==)
    if rep["rounds"][0]["corroborated"] != 1:
        print("FAIL: round 1 should report exactly 1 corroborated finding ->",
              rep["rounds"][0]["corroborated"]); ok = False

    # 8. the 2-round cap's early-convergence break must actually FIRE: given room for 3 rounds and
    #    finders that converge, it stops at 2 (round 2 adds nothing new). The old test ran at
    #    max_rounds=2 where the loop ends naturally, so this break was never exercised.
    #    (kills L70  r > 1 -> r <= 1)
    rep3 = run("/fake", [f1, f2], max_rounds=3)
    if len(rep3["rounds"]) != 2:
        print("FAIL: a converged run should stop at 2 rounds, not run to max ->",
              len(rep3["rounds"])); ok = False

    # 9. _wire_real_finders() always wires the in-repo structural finder and is stable across calls
    #    (calling it twice returns the same finder count -- no companion path is duplicated).
    n1 = len(_wire_real_finders())
    n2 = len(_wire_real_finders())
    if n1 < 1 or n1 != n2:
        print("FAIL: _wire_real_finders unstable or empty ->", n1, n2); ok = False

    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _wire_real_finders():
    """Best-effort wiring of the real finders; returns the list of those available.

    The structural finder ships in this repo and is always wired. The silent-defect finder lives in
    a separate companion repo (claimproof) and is added only when it is importable -- so the
    orchestrator runs whether or not the companion is installed."""
    finders = []
    try:
        from . import structural
        from ._optional import load_claimproof
    except ImportError:                        # when run as a script, not a package
        import structural                      # type: ignore
        from _optional import load_claimproof  # type: ignore
    finders.append(structural.raw_findings)
    multimethod, rag_index = load_claimproof()
    if multimethod is not None:
        finders.append(multimethod.raw_findings)
    if rag_index is not None:
        finders.append(rag_index.raw_findings)
    return finders


if __name__ == "__main__":
    import sys, json as _json
    if "--selftest" in sys.argv or len(sys.argv) == 1:
        sys.exit(selftest())
    target = [a for a in sys.argv[1:] if not a.startswith("-")][0]
    finders = _wire_real_finders()
    fixer_hook = None
    if "--fix" in sys.argv:                               # apply only SAFE mechanical fixes
        try:
            from . import fixer as _fx, patches as _pt
        except ImportError:
            import fixer as _fx, patches as _pt          # type: ignore

        def _combined(dir_):
            raw = []
            for f in finders:
                raw.extend(f(dir_))
            return triangulate(raw)

        def fixer_hook(auto, root):                       # noqa: F811  (matches run()'s fixer sig)
            rep = _fx.apply_fixes(root, auto, _pt.dispatch, _combined, dry_run=False)
            return len(rep["applied"])
    rep = run(target, finders, fixer=fixer_hook)
    for rd in rep["rounds"]:
        print("round %(round)d: %(total)d findings (%(new)d new, %(corroborated)d corroborated, "
              "%(auto_fixable)d auto-fixable, %(needs_human)d need you)" % rd)
    print(rep["message"])
    if "--sarif" in sys.argv:
        out = sys.argv[sys.argv.index("--sarif") + 1]
        open(out, "w").write(_json.dumps(rep["sarif"], indent=2))
        print("SARIF written:", out)
    sys.exit(0)
