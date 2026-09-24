---
name: Bug report
about: A finder misses a defect, flags a false positive, or a module errors out
title: "[bug] "
labels: bug
assignees: ""
---

## What happened

A clear, concise description of the bug.

## Which part

- [ ] A finder **missed** a real defect (false negative)
- [ ] A finder **flagged** correct code (false positive)
- [ ] The fixer / patches did the wrong thing
- [ ] A module raised an error / crashed
- [ ] Something else

Module(s) involved (e.g. `structural.py`, `orchestrator.py`, `mutation.py`):

## Minimal reproduction

The smallest Python snippet or directory layout that shows the problem. Because every detector keys
on **behaviour, not names**, a tiny synthetic example is usually enough:

```python
# e.g. the code the finder should (or should not) have flagged
```

Command run:

```bash
python3 fullcircle/orchestrator.py <path>
```

## Expected vs actual

- **Expected:** what the finding (or absence of a finding) should have been.
- **Actual:** what happened, including the exact output / traceback.

## Environment

- OS:
- Python version (`python3 --version`):
- Companion `claimproof` installed? yes / no
- `run_all_tests.py` passes on your checkout? yes / no
