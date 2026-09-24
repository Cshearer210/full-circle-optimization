---
name: Feature request
about: Propose a new defect class, detection method, or mechanical fix
title: "[feature] "
labels: enhancement
assignees: ""
---

## The problem

What defect or workflow is not covered today? If it is a new **defect class**, describe the shape of
the bug in behavioural terms (what the code *does* that is wrong), not a specific name.

## Proposed detection

How could a finder recognise it structurally (AST / call graph)? Ideally name **two independent
signals**, since a defect corroborated by two methods is the whole trust story here.

## Both-directions proof

Every detector must fire on a known-bad case **and** stay quiet on a known-good one. Sketch both:

- **Known-bad** (must be flagged):
- **Known-good** (must NOT be flagged):

## Alternatives / prior art

Anything you considered, or existing tools that do part of this.

## Scope check

- [ ] Runtime stays **zero-dependency** (standard library only)
- [ ] It works without executing the target's code (static), or is clearly opt-in if it runs code
