# Contributing

Thanks for your interest in `full-circle-optimization`. It is a small, self-contained tool with a
strong opinion about proof, so contributing is straightforward once you know the two rules that never
bend.

## The two rules

1. **The runtime stays zero-dependency.** Everything in `fullcircle/` and `examples/` must run on the
   Python standard library alone. Test-only and lint-only tools are fine — they go in
   `requirements-dev.txt` and are never imported by runtime code.
2. **Every detector is proven in both directions.** A finder must fire on a known-bad input **and**
   stay quiet on a known-good one. A detector proven in only one direction is not proven — it is a
   detector that has never been shown to say "no".

## Getting set up

```bash
git clone https://github.com/Cshearer210/full-circle-optimization
cd full-circle-optimization

# Runtime needs nothing. For the dev workflow:
python3 -m pip install -r requirements-dev.txt   # pytest, coverage, ruff, hypothesis
```

Requires Python 3.11+.

## Running the checks

```bash
python3 run_all_tests.py          # every module's built-in --selftest, in one command
python3 -m pytest -q tests        # the pytest suite (unit, error-path, property, CLI)
python3 -m coverage run -m pytest -q tests && python3 -m coverage report
ruff check .                      # lint
```

All four must be green before a change is ready. CI runs the same steps on Python 3.11 and 3.12.

The optional companion silent-defect finder (`claimproof`) lives in its own repository. The suite is
green without it — its classes are reported as *skipped*, never *failed*. If you have a checkout,
point `CLAIMPROOF_SRC` at it to exercise those classes too.

## Adding a defect class or detector

1. Add the detector to `fullcircle/structural.py` (or the appropriate module), keyed on a
   **behavioural / structural signal**, never on a name — renaming symbols in the target must not
   change the result.
2. Emit the shared `Finding` contract (`fullcircle/finding.py`) so it triangulates with the others.
3. Add a **both-directions** case to that module's `selftest()` and, ideally, focused tests under
   `tests/`. If two independent methods can find the same defect, wire both — corroboration is the
   product.
4. Register it in `DETECTORS` and, if it is a randomised-scale class, add a planter to
   `testbed_scale.py` with a gloss.
5. Run all four checks above.

## Adding a mechanical fix

Mechanical fixes live in `fullcircle/patches.py` and only ever apply to **corroborated**, safe
defect classes. The fixer (`fullcircle/fixer.py`) will still verify on an isolated clone and roll
back on any regression — but a patch provider must refuse anything it is not certain of (return
`False`), never guess.

## Style

- `ruff check .` must pass; see `pyproject.toml` for the (deliberately small) rule set.
- Match the surrounding style. The module selftests intentionally use compact `print(...); ok =
  False` one-liners — that is a convention here, not an accident.
- Keep comments about *why*, not *what*.

## Reporting bugs / requesting features

Use the issue templates. For anything security-sensitive, see [SECURITY.md](SECURITY.md) instead of a
public issue.

By contributing you agree that your contributions are licensed under the project's
[MIT License](LICENSE).
