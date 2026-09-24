<!-- Thanks for contributing! Keep the runtime zero-dependency and every detector proven in BOTH
directions. -->

## What this changes

A short description of the change and why.

## Type

- [ ] Bug fix (a finder missed / over-flagged, or a module errored)
- [ ] New defect class or detection method
- [ ] New mechanical fix provider
- [ ] Docs / maintenance / tooling
- [ ] Other

## Proof

- [ ] `python3 run_all_tests.py` passes
- [ ] `python3 -m pytest -q tests` passes
- [ ] `ruff check .` is clean
- [ ] New/changed detectors have a **both-directions** test (fires on known-bad, quiet on known-good)
- [ ] Runtime stays **standard-library only** (dev-only deps go in `requirements-dev.txt`)

## Notes for the reviewer

Anything worth calling out: a real bug the change fixes, a false-positive it removes, coverage
impact, or a design decision.
