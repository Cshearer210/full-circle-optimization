# full-circle-optimization

**One pass that runs several independent code-health finders as a team and trusts a defect only when two of them agree — so it holds up on a codebase it has never seen.**

[![CI](https://github.com/Cshearer210/full-circle-optimization/actions/workflows/ci.yml/badge.svg)](https://github.com/Cshearer210/full-circle-optimization/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

## Why it exists

The dangerous defects in generated code are the *quiet* ones: a test that runs but asserts nothing,
a gate that always returns `True`, the same function copied to two paths so a fix to one silently
misses the other, a constant with two different values in two files. Each survives review because a
single checker has a single blind spot — and a single checker gives you no way to tell a real
finding from a false alarm.

The whole idea here is **corroboration**. Every defect is looked for by *several independent
methods*. A defect that two methods agree on is trustworthy precisely because no one blind spot
could have produced both — so it is safe to act on. A defect only one method saw is a *lead*, and
it is routed to a human instead of auto-fixed. Nothing keys on a name: the finders look at what the
code *does* (its AST and call graph), so renaming everything in the target changes none of the
results.

## Limits, up front

- **Python source only.** Detection is AST- and call-graph-based; it does not analyse other
  languages.
- **Proven on generated systems, not yet on real third-party repos.** The proof below plants known
  defects into synthetic projects and scores against ground truth. Running against arbitrary public
  repositories is on the roadmap, not a claim.
- **Auto-fix is deliberately narrow.** Only *corroborated, mechanical* defects are eligible; the
  one auto-fix implemented today is removal of corroborated dead/unwired code, and every fix is
  verified on a throwaway clone and rolled back if anything moves. Everything else — conflicts,
  single-method leads — goes to a human review queue.
- **Mostly static.** It reasons about code shape, not runtime behaviour. The one exception is the
  mutation-testing module, which actually runs a target's test suite against mutated copies.
- **The silent-defect classes need an optional companion.** Six of the sixteen defect classes are
  found by a separate tool, `claimproof` (its own repository). It is optional: without it, this
  repo still proves the ten *structural* classes on its own (see the status table). With it
  installed, the same pipeline additionally proves the six silent classes.

## Install

Zero friction — it is pure Python standard library. **No dependencies, no build step, no account,
and it makes no network calls.**

```bash
git clone https://github.com/Cshearer210/full-circle-optimization
cd full-circle-optimization
python3 run_all_tests.py        # the whole proof, in one command
```

Requires Python 3.11+.

## Minimal example

Run the pipeline over any Python project directory:

```bash
python3 fullcircle/orchestrator.py <path-to-a-project>                 # 2-round pipeline
python3 fullcircle/orchestrator.py <path> --sarif findings.sarif      # + SARIF for code scanning
python3 fullcircle/structural.py  <path>                              # just the structural finder
```

Or from Python:

```python
from fullcircle import orchestrator

finders = orchestrator._wire_real_finders()          # structural finder (+ companion if installed)
report  = orchestrator.run("path/to/project", finders)

for t in report["auto_fixable"]:       # corroborated by >=2 methods -> safe to auto-fix
    print(t.defect_class, t.location, t.methods)
for t in report["human_review_queue"]: # single-method leads / judgment calls -> a human decides
    print(t.defect_class, t.location, t.methods)
```

## Demo

`examples/demo.py` builds a throwaway project with four planted defects plus one clean control,
runs the real pipeline over it, and prints what it found. This is the **actual, unedited output**
of a fresh clone (companion not installed):

```
$ python3 examples/demo.py
full-circle-optimization demo
target: a generated project with 4 planted defects + 1 clean control
finders wired: 1 (structural only)

round 1: 4 findings  3 corroborated  2 auto-fixable  2 need a human
round 2: 4 findings  3 corroborated  2 auto-fixable  2 need a human

CORROBORATED (>=2 independent methods -> safe to auto-fix):
  [corroborated] function-unwired         core/orphan.py:1  via no-call-edge,no-reference
  [corroborated] stub-implementation      core/pay.py:1  via body-is-stub,has-callers

HUMAN-REVIEW QUEUE (single-method leads or judgment calls):
  [corroborated] conflicting-definition   RETRY_LIMIT='five' in {conf/b.py}; RETRY_LIMIT  via constant-conflict,value-type-mismatch
  [single-method] second-door-duplicate    core/handler_a.py | legacy/handler_b.py  via same-content

SARIF 2.1.0 written with 4 result(s) (drop-in for GitHub code scanning).
Ran 2 round(s), capped at 2; re-run later once the code has changed. 2 item(s) need a human decision.
```

Note two design decisions visible in that output: the `conflicting-definition` is corroborated but
still sent to a human (choosing which value is correct is a judgment call, never a bot's), and the
`second-door-duplicate` is a single-method lead, so it too waits for a human rather than being
auto-fixed.

## Proof

The test bed generates fake systems with **known** planted defects plus clean controls, runs every
finder, and scores catch rate against ground truth — then repeats with **every symbol and file
renamed**, which is the label-independence proof: the catch rate must not move when the names do.

Fixed bed, three complexity levels, fresh clone (structural classes; companion not installed):

```
$ python3 fullcircle/testbed.py
TEST BED -- intended-job catch rate across levels (must be 100%, 0 FP)
companion silent-defect finder: not installed -- structural classes only;
silent classes reported as SKIPPED (install claimproof to exercise them)
  basic              4/4 caught  0 false-pos   OK  (3 silent skipped)
  basic+renamed      4/4 caught  0 false-pos   OK  (3 silent skipped)
  medium             4/4 caught  0 false-pos   OK  (3 silent skipped)
  medium+renamed     4/4 caught  0 false-pos   OK  (3 silent skipped)
  complex            4/4 caught  0 false-pos   OK  (3 silent skipped)
  complex+renamed    4/4 caught  0 false-pos   OK  (3 silent skipped)
VERDICT: 100% on intended jobs, 0 false positives (structural classes; silent classes not exercised)
```

Randomised scale test — hundreds of systems, each with a random subset of classes under random
names (a continuous label-independence proof). Fresh clone:

```
$ python3 fullcircle/testbed_scale.py
SCALE TEST -- 300 randomised systems, 1644 planted defects
  bare-except                       ...   100.0%
  conflicting-definition            ...   100.0%
  dead-code                         ...   100.0%
  function-unwired                  ...   100.0%
  mutable-default-arg               ...   100.0%
  resource-leak                     ...   100.0%
  second-door-duplicate             ...   100.0%
  shadowed-builtin                  ...   100.0%
  stub-implementation               ...   100.0%
  unused-import                     ...   100.0%
  false positives on controls: 0
  clean configs: 300/300
  SKIPPED (companion silent-defect finder not installed): assert-constant-in-production, labeled-gate-that-cannot-fail, predicate-returns-none, swallowed-exception, test-cannot-fail, unreachable-except
VERDICT: 100% catch, 0 false positives across all configs (structural classes; silent classes not exercised)
```

**Measured on a fresh clone: 10 structural defect classes, 1,644 planted defects across 300
randomised systems, 100% caught, 0 false positives.** Every module also ships a `--selftest` that
proves it fires on a known-bad case **and** stays quiet on a known-good one — a detector proven in
only one direction is not proven.

## Status

| Component | State |
|---|---|
| Structural finder — 10 defect classes (see below) | **Works today.** 100% catch, 0 false positives, 300 randomised + 3-level fixed bed, label-independent |
| Triangulation + shared finding contract + SARIF 2.1.0 export | **Works today** |
| Orchestrator — 2-round loop, corroborated-vs-lead split, human-review queue | **Works today** |
| Safe fixer — isolated clone, verify-both-directions, rollback, single-writer merge | **Works today** (exercised by selftests; auto-fix limited to the corroborated dead/unwired class) |
| Mutation testing — proves a target's own suite can actually fail | **Works today** (self-quality module) |
| Concept/label portability core — classify by behaviour, learn the target's own names | **Works today** |
| Silent-defect classes (6) — test-cannot-fail, gate-ignores-input, swallowed-exception, predicate-returns-none, unreachable-except, assert-cannot-fail | **Optional companion** (`claimproof`, separate repo); integration wired, skipped cleanly when absent |
| Live runs against real third-party repositories | **Roadmap** — proven on generated systems only so far |
| More mechanical auto-fix providers | **Roadmap** |

### The 10 structural classes proven self-contained

`second-door-duplicate` · `conflicting-definition` · `function-unwired` · `stub-implementation` ·
`dead-code` · `unused-import` · `mutable-default-arg` · `bare-except` · `resource-leak` ·
`shadowed-builtin`. Each is found by two independent methods where possible; where they agree the
finding is marked *corroborated*, otherwise it is a *lead* for human review.

## How it works

```
finders  ->  triangulate  ->  partition            ->  loop (<=2 rounds)  ->  one SARIF + report
(each a    (collapse to    (corroborated+mechanical
 callable   one finding     -> auto-fixable;
 root ->    per defect,     everything else
 findings)  count methods)  -> human review)
```

- **`finding.py`** — the one shared finding contract (a defect is identified by *what is wrong
  where*, independent of which method found it) and the triangulation engine, plus SARIF export.
- **`structural.py`** — the structural finder: duplicates, conflicting definitions, unwired
  functions, called stubs and more, each keyed on a behavioural/structural signal, never a label.
- **`orchestrator.py`** — the thin linker: collects findings from every wired finder, triangulates,
  runs at most two rounds, and splits results into auto-fixable vs human-review.
- **`fixer.py` / `patches.py`** — the safe fix engine: every fix is tried on an isolated clone,
  verified in both directions (the target finding must disappear *and* nothing new may break), and
  rolled back otherwise; verified fixes are merged by a single writer so parallel work cannot
  collide.
- **`concepts.py`** — the portability core: classify code by behaviour into shared concepts and
  learn the target's own names for them, so detection survives renaming.
- **`mutation.py`** — mutation testing: change the code and the tests must go red; a surviving
  mutation proves a green suite is protecting nothing.
- **`testbed.py` / `testbed_scale.py`** — the proof harness described above.

The silent-defect finder (`claimproof`) lives in its own repository and is loaded only if
importable, or if `CLAIMPROOF_SRC` points at a local checkout. This repo therefore stands entirely
on its own; the companion only *adds* the six silent classes.

## License

MIT — see [LICENSE](LICENSE).
