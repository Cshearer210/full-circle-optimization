# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- A pytest suite under `tests/` (239 tests) covering every module: happy paths, edge and boundary
  cases, error/exception paths, the corroboration logic, and the SARIF output shape — alongside the
  existing `run_all_tests.py` selftests, which still run.
- `hypothesis` property-based tests (dev-only) for the finding identity/triangulation invariants.
- Coverage measurement (`coverage`) and a `ruff` lint step, both wired into CI.
- Standard OSS maintenance files: `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  this changelog, `.github/dependabot.yml`, issue templates, and a pull-request template.
- `pyproject.toml` with tool configuration (pytest, coverage, ruff) and `requirements-dev.txt` for
  the dev toolchain. The runtime remains zero-dependency.

### Changed
- CI now runs the selftests **and** pytest with coverage **and** ruff, on Python 3.11 and 3.12.

### Fixed
- Removed dead code surfaced while adding the suite: an unused `Triangulated` import in `fixer.py`,
  an unused `os` import in `orchestrator.py`, and an unused `inode_hash` local in `structural.py`.
  No behavior changed.

## [0.1.0] - 2026-09-24

### Added
- Initial public release.
- **Shared finding contract + triangulation** (`finding.py`): a defect is identified by *what is
  wrong where*, independent of the method that found it, so independent methods collapse to one
  corroborated finding; SARIF 2.1.0 export.
- **Structural finder** (`structural.py`): ten defect classes — second-door duplicate, conflicting
  definition, unwired function, called stub, dead code, unused import, mutable default argument, bare
  except, resource leak, shadowed builtin — each keyed on a behavioural/structural signal.
- **Orchestrator** (`orchestrator.py`): thin linker that triangulates across finders, runs a
  two-round loop, and splits results into auto-fixable vs. a human-review queue.
- **Safe fixer** (`fixer.py` / `patches.py`): isolated-clone fixes, verify-both-directions, rollback
  on regression, single-writer merge; the one mechanical fix is removal of corroborated dead code.
- **Portability core** (`concepts.py`): classify code by behaviour into shared concepts and learn the
  target's own labels, so detection survives renaming.
- **Mutation testing** (`mutation.py`): change the code and the tests must go red; a surviving
  mutation proves a green suite is protecting nothing.
- **Test bed + scale harness** (`testbed.py` / `testbed_scale.py`): generate systems with known
  planted defects plus clean controls and score catch rate against ground truth, including a
  fully-renamed variant as a label-independence proof.
- **Optional companion loader** (`_optional.py`): wires the separate `claimproof` silent-defect
  finder when present, and cleanly skips (never fails) its classes when absent.
- MIT license, CI, and a runnable `examples/demo.py`.

[Unreleased]: https://github.com/Cshearer210/full-circle-optimization/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Cshearer210/full-circle-optimization/releases/tag/v0.1.0
