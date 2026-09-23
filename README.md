# FULL-CIRCLE-OPTIMIZATION

**Find the defects that hide in AI-built systems — then fix them safely — on a codebase the tools
have never seen.** This is the linker that runs four tools as one team; each also stands alone.

Silent defects survive because a single check has a single blind spot. The whole design here is
**corroboration**: every defect is found by several *independent* methods, and a defect two methods
agree on is trustworthy precisely because no one blind spot could hide it. That is what makes the
findings reliable on an unfamiliar system.

## The four tools

| Tool | Job | Runs |
|---|---|---|
| **claimproof** | finds **silent** defects (a test that can't fail, a gate that can't fail, a claim with no backing) using several methods per class; also verifies fixes | 1st, and again as verifier |
| **FULL-RESET-GRAPH** | maps the system, finds **loud/structural** defects (duplicates, conflicting definitions, unwired code) and organises files | before claimproof |
| **SANDBOX-FAN-OUT** | **fixes** located defects safely when dropped into an unfamiliar system (isolated clone, verify, roll back, single-writer merge) | after finding |
| **FULL-CIRCLE-OPTIMIZATION** | the thin linker: one finding format, cross-tool triangulation, a 2-round loop, a human-review queue, one report | ties them together |

## Why it works on systems it has never seen

Every detector keys on **behaviour**, never on a **label**. It does not look for a folder named
`tests/` — it looks for a function the test runner would collect that checks nothing. It does not
look for a "Done." message — it opens the thing the message claims. So renaming everything in the
target changes nothing.

**Proven, not asserted.** The test bed generates fake systems at three complexity levels, plants a
known defect of each class plus clean controls, then scores against ground truth — and repeats the
whole thing with **every symbol renamed**:

```
$ python3 fullcircle/testbed.py
  basic              6/6 caught  0 false-pos   OK
  basic+renamed      6/6 caught  0 false-pos   OK
  medium             6/6 caught  0 false-pos   OK
  medium+renamed     6/6 caught  0 false-pos   OK
  complex            6/6 caught  0 false-pos   OK
  complex+renamed    6/6 caught  0 false-pos   OK
  VERDICT: 100% on intended jobs, 0 false positives
```

The `+renamed` rows are the label-independence proof: catch rate does not move when the names do.

## Defect classes proven so far

- **test that cannot fail** — runs code, checks nothing (claimproof: weak-oracle + return-ignored)
- **gate that cannot fail** — named like a gate, returns a constant / ignores its input (claimproof RAG indexer: constant-verdict + input-ignored)
- **second-door duplicate** — the same code at two paths; a fix to one misses the other (FULL-RESET-GRAPH: same-inode + same-content)
- **conflicting definition** — one constant, different values in two files (FULL-RESET-GRAPH: constant-conflict + value-type-mismatch)
- **unwired function** — defined and complete, nothing calls it (FULL-RESET-GRAPH: no-call-edge + no-reference)
- **swallowed exception** — an error turned into a success-looking result (claimproof: silent-swallow + returns-success)

Each is found by **two independent methods**; where they agree the finding is marked *corroborated*.
A finding only one method saw is a *lead*, routed to human review rather than auto-fixed.

## Run it

```bash
python3 fullcircle/orchestrator.py <path-to-a-system>            # the whole pipeline, 2 rounds
python3 fullcircle/orchestrator.py <path> --sarif out.sarif      # + inline GitHub annotations
python3 fullcircle/testbed.py                                    # the proof across 3 levels
```

Any single tool alone:

```bash
python3 fullcircle/structural.py <path>       # FULL-RESET-GRAPH structural finder
python3 fullcircle/rag... (claimproof)        # claimproof: python -m claimproof.multimethod <path>
```

Every module has a `--selftest` that proves it fires on a known-bad case **and** stays quiet on a
known-good one (both directions), because a detector proven in only one direction is not proven.

## How a fix is applied safely

`SANDBOX-FAN-OUT` never touches the live system until a fix is proven on a throwaway clone: it
applies the change, re-runs the finder, and keeps the fix **only if the finding disappears and
nothing new breaks**. Anything that regresses is rolled back; verified fixes are merged by a single
writer so parallel agents cannot collide. It auto-fixes only corroborated, high-confidence findings;
everything else — conflicts, rules, single-method leads — goes to a human.

## Status

Foundation and the five defect classes above are built and pass the test bed at 100% with zero false
positives, at three complexity levels including the renamed (label-independent) variants. Still on
the roadmap: mutation-based detection (the strongest silent method), more silent classes, the
organise stage, and live runs against real third-party repositories. Nothing is released until the
whole roadmap clears the test bed.
