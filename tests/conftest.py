"""Shared pytest fixtures and path wiring for the full-circle-optimization suite.

The package is imported as a top-level `fullcircle` package (no `pip install` step, matching the
zero-dependency runtime story), so the repo root goes on `sys.path` here rather than in every test
file. The helpers below build throwaway target repositories on disk -- the finders and the fixer all
operate on a directory, so almost every real test needs one.
"""
from __future__ import annotations

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _write(root: str, rel: str, body: str) -> str:
    """Write `body` to `root/rel`, creating parent directories. Returns the absolute path."""
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p) or root, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(body)
    return p


@pytest.fixture
def write_tree(tmp_path):
    """Return a writer bound to a fresh temp directory, plus the directory itself.

    Usage:
        def test_x(write_tree):
            root, w = write_tree
            w("pkg/mod.py", "x = 1\n")
    """
    root = str(tmp_path)

    def w(rel: str, body: str) -> str:
        return _write(root, rel, body)

    return root, w


@pytest.fixture
def make_repo(tmp_path):
    """Return a factory that writes a whole {relpath: body} mapping into a fresh subdir and returns
    that subdir. Lets one test build several independent target repos."""
    counter = {"n": 0}

    def build(files: dict) -> str:
        counter["n"] += 1
        root = os.path.join(str(tmp_path), "repo_%d" % counter["n"])
        os.makedirs(root, exist_ok=True)
        for rel, body in files.items():
            _write(root, rel, body)
        return root

    return build
