"""Real behavioural tests for the optional companion loader.

The core guarantee: the loader NEVER raises, whether or not `claimproof` is installed, and it reports
a consistent presence flag. The absent path is forced deterministically (so it is exercised even on
a machine where the companion happens to be importable) by poisoning `sys.modules['claimproof']`,
which makes the import statement inside the loader raise ImportError -- exactly the fresh-clone case.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

from fullcircle import _optional
from fullcircle._optional import (
    SILENT_CLASSES,
    _EmptyFinder,
    claimproof_finders,
    load_claimproof,
)


def _companion_installed():
    return importlib.util.find_spec("claimproof") is not None


@pytest.fixture
def companion_forced_absent(monkeypatch):
    """Force `import claimproof` to fail regardless of the machine's real state."""
    monkeypatch.delenv("CLAIMPROOF_SRC", raising=False)
    for name in ("claimproof", "claimproof.multimethod", "claimproof.rag_index"):
        monkeypatch.setitem(sys.modules, name, None)  # None in sys.modules -> ImportError on import
    yield


# ---------------------------------------------------------------- empty stand-in
def test_empty_finder_finds_nothing():
    assert _EmptyFinder.raw_findings(".") == []
    assert _EmptyFinder.raw_findings("/anything") == []


# ---------------------------------------------------------------- absent path (deterministic)
def test_load_claimproof_returns_none_pair_when_absent(companion_forced_absent):
    assert load_claimproof() == (None, None)


def test_claimproof_finders_absent_gives_empty_stubs(companion_forced_absent):
    mm, ri, present = claimproof_finders()
    assert present is False
    assert mm is _EmptyFinder and ri is _EmptyFinder
    assert mm.raw_findings("x") == []
    assert ri.raw_findings("x") == []


def test_loader_never_raises_when_absent(companion_forced_absent):
    # the whole point: a fresh clone must not blow up when the companion is missing.
    load_claimproof()
    claimproof_finders()


# ---------------------------------------------------------------- present path (conditional)
@pytest.mark.skipif(not _companion_installed(), reason="companion claimproof not installed")
def test_present_companion_finders_are_callable():
    mm, ri, present = claimproof_finders()
    assert present is True
    # both must be importable and callable without raising on a real directory
    here = os.path.dirname(_optional.__file__)
    assert isinstance(mm.raw_findings(here), list)
    assert isinstance(ri.raw_findings(here), list)


# ---------------------------------------------------------------- CLAIMPROOF_SRC path handling
def test_claimproof_src_dir_is_added_to_syspath(monkeypatch, tmp_path):
    # even when the dir contains no companion, a real dir named by CLAIMPROOF_SRC is put on the path.
    src = str(tmp_path / "companion_checkout")
    os.makedirs(src)
    monkeypatch.setenv("CLAIMPROOF_SRC", src)
    for name in ("claimproof", "claimproof.multimethod", "claimproof.rag_index"):
        monkeypatch.setitem(sys.modules, name, None)  # still no real companion -> (None, None)
    result = load_claimproof()
    assert result == (None, None)
    assert src in sys.path


def test_nonexistent_claimproof_src_is_ignored(monkeypatch):
    monkeypatch.setenv("CLAIMPROOF_SRC", "/no/such/dir/zzz")
    for name in ("claimproof", "claimproof.multimethod", "claimproof.rag_index"):
        monkeypatch.setitem(sys.modules, name, None)
    assert load_claimproof() == (None, None)


# ---------------------------------------------------------------- silent-class contract
def test_silent_classes_are_the_six_companion_classes():
    assert isinstance(SILENT_CLASSES, frozenset)
    assert len(SILENT_CLASSES) == 6
    for c in ("test-cannot-fail", "swallowed-exception", "labeled-gate-that-cannot-fail",
              "predicate-returns-none", "unreachable-except", "assert-constant-in-production"):
        assert c in SILENT_CLASSES


def test_module_selftest_passes():
    assert _optional.selftest() == 0
