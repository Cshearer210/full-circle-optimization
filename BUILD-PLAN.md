# Portfolio repos — build plan of record

Companion to `~/PureEuphoria/memory/problems/PORTFOLIO-REPOS-JOB-TAXONOMY.md` (the job list) and
`~/PureEuphoria/_plan-state/DEFECT-CLASSES.md` (the canonical class store). This is the ordered
build. Chris confirmed the architecture and all 7 optimization levers 2026-09-23, then said "build
the plan and steps... in-depth dives... then start; work autonomously." Hold: nothing releases until
100% on intended jobs across the test bed.

## The 7 refinements Chris locked 2026-09-23 (these govern every step below)

1. **Corroboration is THE point.** Overlapping methods that agree = trust; disagreement = a finding.
   Built in `fullcircle/finding.py` (selftest PASS). Also going into the main system via
   `~/PureEuphoria/_plan-state/corroboration-implementation-prompt.md`.
2. **FULL-RESET-GRAPH GENERATES the label/definition map.** It learns how the target system labels
   and assigns things, stores that map, and the synonym tool uses it during indexing so a concept is
   detected regardless of the target's naming. The map is an OUTPUT of the mapping stage, consumed by
   claimproof's indexer and by the drop-in adapter.
3. **Loop cap = 2 rounds**, not until-dry. Run everything twice, then STOP and do output/other work
   for a day or two so the tools have new data, then re-run as needed. The orchestrator enforces the
   cap and reports what each round added/fixed.
4. **Human-in-the-loop trigger at EACH STAGE, in EACH repo.** After a stage gathers a lot of info,
   it emits a REVIEW QUEUE and pauses on items that need a human eye — laws, rules, and other
   judgment items especially. The tool never auto-decides those; it batches them for one human pass.
5. **Mechanical/reasoning split on fixes** (his standing method): known class->known patch = Python,
   no model; "same defect as before?" = cheap/local model; novel = opus once, then record the path.
6. **Test bed includes systems NOT shaped like his** + a renamed-everything fixture proving
   label-independence + real online repos + 3 complexity levels.
7. **SARIF output** from each repo so findings annotate code inline in GitHub's UI.

## Shared contract (BUILT)

- `fullcircle/finding.py` — Finding + Triangulated + triangulate() + method_disagreements(). selftest
  PASS 2026-09-23. To be copied byte-identical into each repo; a drift-guard check fails if copies
  diverge.
- CONCEPTS = gate, test, claim, wire, definition, schedule, instruction, population, read, artifact.
- Portability rule: every detector keys on a behavioural SIGNAL + a CONCEPT, names one label it
  IGNORES, and is proven by the renamed-fixture test.

---

## REPO A — FULL-RESET-GRAPH (rag-ghost-work). Maps, finds loud, ORGANIZES, fixes. Runs FIRST.

Deep dive: this repo must produce the label/definition map (refinement 2) that everything downstream
uses, so it is built first.

- [ ] A1. Rename local dir/package rag-ghost -> full_reset_graph (keep imports working); GitHub
      rename handed to Chris as a one-liner (needs token, public act).
- [ ] A2. MAPPING stage: build the label/definition map — for each concept, record how THIS system
      names/assigns it (the observed labels, their definitions inferred from behaviour). Output:
      `system-map.json` {concept: {labels:[...], definition, examples}}.
- [ ] A3. Synonym detection during indexing reads that map so a concept is found under any label.
- [ ] A4. New detectors (structural, not label-based): unwired, nothing-calls-it, conflicting
      instructions/tools (>1 authority for one subject), second-door duplicate (st_dev,st_ino +
      findmnt), >1 definition of a shared constant, scheduled-job-never-ran, reimplemented-read-path.
- [ ] A5. ORGANIZE stage: propose a directory layout that makes the concepts usable; emit as a plan
      (SANDBOX-FAN-OUT applies the moves), not applied directly.
- [ ] A6. Each detector emits Finding format + SARIF; both-directions selftest each.
- [ ] A7. Human-review queue: conflicts, law/rule/instruction findings -> review queue, not auto-fix.
- [ ] A8. Renamed-fixture test proves catch rate unchanged after relabeling.

## REPO B — claimproof (PureEuphoria/claimproof). Finds SILENT, multi-method. Runs SECOND + verifies.

Deep dive: the multi-method engine is the differentiator. Each silent class gets >=2 independent
methods; findings triangulate.

- [ ] B1. Multi-method engine: a registry of {defect_class: [method1, method2, ...]}; each method
      returns Findings; triangulate() collapses them; report corroboration per finding.
- [ ] B2. Implement >=2 methods for each priority silent class from the taxonomy (start:
      dead-canary = mutation + AST-asserts-on-return; gate-cant-fail = AST-controlflow + mutation +
      run-twice-idempotence; absent-looks-like-clean = default-with-no-writer + except-returns-success).
- [ ] B3. RAG indexer (Chris's Telegram table): index done-messages/checks/gates/tests/diagnostics
      by behaviour; retrieve by meaning; report label/definition/synonym mismatches. Consumes A2's map.
- [ ] B4. Verifier mode: re-run after SANDBOX-FAN-OUT; a fix must make the finding disappear AND
      break nothing (both directions).
- [ ] B5. SARIF + JSON output. Human-review queue for judgment-class findings.
- [ ] B6. Renamed-fixture + carrot-sandbox scoreboard: 100% on intended silent classes.

## REPO C — SANDBOX-FAN-OUT (corral-work). Fixes efficiently, dropped-in. Runs THIRD.

Deep dive: 8 checks-and-balances (taxonomy repo-3 section) + mechanical/reasoning fix routing.

- [ ] C1. Rename local dir/package corral -> sandbox_fan_out; GitHub rename handed to Chris.
- [ ] C2. Fix router (refinement 5): known-class->Python patch; same-as-before->cheap model; novel->
      opus once then record the path.
- [ ] C3. The 8 checks: isolated clone/agent, single-writer merge, disjoint split, per-fix verify
      gate (re-run finder both directions), behavioural targeting, rollback-on-regression, works
      with/without Fable, dry-run-first.
- [ ] C4. Confidence gate: auto-fix only corroborated high-confidence; single-method -> human queue.
- [ ] C5. Applies A5's organize plan (file moves) under the same clone/verify/merge safety.
- [ ] C6. Human-review queue at merge stage. SARIF of what was fixed.

## REPO D — FULL-CIRCLE-OPTIMIZATION (full-circle-optimization-work). Links them. Thin.

- [ ] D1. Drop-in adapter: discover the target's shape once (build/consume A2's map), hand all repos
      the structural map so none re-derives it.
- [ ] D2. Orchestrator: run A->B->C->B(verify); loop cap = 2 rounds (refinement 3); per-round log of
      added/fixed; then STOP and emit "do outputs for a day or two, re-run when new data".
- [ ] D3. Aggregate SARIF + a single run report (found/fixed/verified per round, per repo).
- [ ] D4. Drift-guard: the 4 copies of finding.py are byte-identical.

## TEST BED (refinement 6) — the proof, runs against ALL repos

- [ ] T1. 3 complexity levels of fake systems (basic / medium / very complex), each with planted
      instances of every taxonomy class + clean controls.
- [ ] T2. Renamed-everything fixture (label-independence proof).
- [ ] T3. Real online repos people ask for help with (fix and, where appropriate, offer back).
- [ ] T4. Old versions of Chris's own system via git (1wk/2wk/1-6mo).
- [ ] T5. Agent-tier runs (haiku/sonnet + opus, with and without Fable).
- [ ] T6. LIVE runs on Chris's real system (MOST IMPORTANT; after the other session frees it).
- [ ] T7. Scoreboard: intended jobs must be 100% across every config before any release.

## RELEASE HOLD

Nothing is pushed to a public URL, renamed on GitHub, or released until T7 is 100%. Local commits to
Chris's own repos are backups (allowed). GitHub renames + any release wait for Chris.

## PROGRESS LOG (append as things land)

- 2026-09-23: shared contract `fullcircle/finding.py` BUILT, selftest PASS. Plan written. Refinements
  1-7 locked. Corroboration prompt for main system written.
