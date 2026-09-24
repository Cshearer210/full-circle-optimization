"""Real behavioural tests for the randomised scale harness: every planter writes a uniquely-named
defect and declares its class, the controls stay clean, and a small randomised run catches every
planted defect with zero false positives (a continuous label-independence proof via random names).
"""
from __future__ import annotations

import os
import random

import pytest

from fullcircle import testbed_scale
from fullcircle.testbed_scale import (
    GLOSS,
    PLANTERS,
    _controls,
    _tok,
    _touches,
    gen_random_system,
    get_findings,
    run,
)
from fullcircle.finding import Finding, triangulate


@pytest.mark.parametrize("planter", PLANTERS, ids=[p.__name__ for p in PLANTERS])
def test_each_planter_writes_a_file_and_declares_its_class(planter, tmp_path):
    rng = random.Random(0)
    root = str(tmp_path)
    defect_class, token = planter(root, rng)
    assert isinstance(defect_class, str) and defect_class
    assert isinstance(token, str) and token
    py = [f for _, _, fs in os.walk(root) for f in fs if f.endswith(".py")]
    assert py


def test_there_are_sixteen_planters():
    assert len(PLANTERS) == 16


def test_tok_is_six_lowercase_letters():
    t = _tok(random.Random(1))
    assert len(t) == 6 and t.isalpha() and t.islower()


def test_touches_matches_location_and_id_key():
    f = Finding("wire", "function-unwired", "orphan_abc.py:1", signal="s", method="m",
                ignored_label="dead_abc", extra={"id_key": "unwired:orphan_abc.py:dead_abc"})
    t = triangulate([f])[0]
    assert _touches(t, "orphan_abc.py")   # via location
    assert _touches(t, "dead_abc")        # via ignored_label / id_key
    assert not _touches(t, "totally_unrelated_token")


def test_controls_are_not_flagged(tmp_path):
    root = str(tmp_path)
    rng = random.Random(3)
    toks = _controls(root, rng)
    tri = get_findings(root)
    for t in tri:
        for tok in toks:
            assert not _touches(t, tok), "control %s wrongly flagged by %s" % (tok, t.defect_class)


def test_gen_random_system_returns_ground_and_controls(tmp_path):
    ground, controls = gen_random_system(str(tmp_path), random.Random(5))
    assert ground  # at least one planted
    assert controls
    assert all(isinstance(c, tuple) and len(c) == 2 for c in ground)


def test_small_scale_run_catches_everything_with_no_false_positives():
    r = run(n_configs=25, seed=11)
    assert r["false_positives"] == 0
    for cls, planted in r["per_class_planted"].items():
        assert r["per_class_caught"].get(cls, 0) == planted, "missed some %s" % cls
    assert r["configs_clean"] == r["n_configs"]


def test_gloss_covers_every_planter_class(tmp_path):
    for i, planter in enumerate(PLANTERS):
        root = str(tmp_path / ("g%d" % i))
        os.makedirs(root)
        cls, _ = planter(root, random.Random(i))
        assert cls in GLOSS, "no gloss for %s" % cls


def test_module_selftest_passes():
    assert testbed_scale.selftest() == 0
