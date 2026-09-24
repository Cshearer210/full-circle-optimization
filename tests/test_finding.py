"""Real behavioural tests for the shared finding contract and triangulation engine.

Every test asserts on real output of `fullcircle.finding` against a known input: the identity
algebra (a defect is WHAT/WHERE, never the method), the trust ladder, cross-method disagreement,
and the SARIF shape -- including the rule that a non-file location must never be emitted as a
fabricated file URI.
"""
from __future__ import annotations

import json

import pytest

from fullcircle.finding import (
    CLEAN,
    CONCEPTS,
    FOUND,
    UNKNOWN,
    Finding,
    Triangulated,
    method_disagreements,
    to_sarif,
    triangulate,
    _sarif_locations,
)


def mk(concept="gate", defect_class="no-clean-without-looking", location="g.py:1",
       method="ast", **kw):
    return Finding(concept, defect_class, location, signal=kw.pop("signal", "s"),
                   method=method, **kw)


# ---------------------------------------------------------------- constants / contract
def test_outcome_codes_are_the_three_honest_values():
    assert (CLEAN, FOUND, UNKNOWN) == (0, 1, 2)


def test_concepts_is_the_shared_frozen_list():
    for c in ("gate", "test", "claim", "wire", "definition", "schedule", "instruction",
              "population", "read", "artifact"):
        assert c in CONCEPTS
    assert len(CONCEPTS) == 10


# ---------------------------------------------------------------- identity algebra
def test_identity_ignores_method():
    a = mk(method="ast")
    b = mk(method="mutation")
    assert a.identity() == b.identity()


def test_identity_depends_on_location():
    assert mk(location="g.py:1").identity() != mk(location="g.py:2").identity()


def test_identity_depends_on_defect_class():
    assert mk(defect_class="x").identity() != mk(defect_class="y").identity()


def test_identity_depends_on_concept_when_no_id_key():
    assert mk(concept="gate").identity() != mk(concept="wire").identity()


def test_identity_is_16_hex_chars():
    ident = mk().identity()
    assert len(ident) == 16
    int(ident, 16)  # raises if not hex


def test_id_key_overrides_location_for_identity():
    # two findings at DIFFERENT locations but the same id_key are one defect (e.g. a duplicate
    # whose identity is its content, found by two methods listing different path-sets).
    a = mk(location="a.py:1", extra={"id_key": "dup:HASH"})
    b = mk(location="b.py:9", extra={"id_key": "dup:HASH"})
    assert a.identity() == b.identity()


def test_id_key_identity_ignores_concept_but_uses_defect_class():
    a = mk(concept="read", defect_class="d", extra={"id_key": "k"})
    b = mk(concept="wire", defect_class="d", extra={"id_key": "k"})
    c = mk(concept="wire", defect_class="OTHER", extra={"id_key": "k"})
    assert a.identity() == b.identity()
    assert a.identity() != c.identity()


# ---------------------------------------------------------------- serialisation
def test_to_json_is_sorted_and_deterministic():
    j = mk(both_directions_proven=True).to_json()
    assert j.startswith('{"both_directions_proven"')
    assert j == mk(both_directions_proven=True).to_json()


def test_to_json_round_trips_source_span_and_strength():
    f = Finding("read", "swallowed-exception", "svc.py:12", "except: pass",
                method="ast", source_span="svc.py:12-14", evidence_strength="measured")
    d = json.loads(f.to_json())
    assert d["source_span"] == "svc.py:12-14"
    assert d["evidence_strength"] == "measured"


def test_evidence_strength_defaults_unspecified():
    assert json.loads(mk().to_json())["evidence_strength"] == "unspecified"


def test_defaults_are_conservative():
    f = mk()
    assert f.confidence == 0.5
    assert f.severity == "med"
    assert f.both_directions_proven is False
    assert f.status == "found"
    assert f.extra == {}


# ---------------------------------------------------------------- triangulation
def test_two_methods_one_defect_corroborate():
    tri = triangulate([mk(method="ast", both_directions_proven=True),
                       mk(method="mutation")])
    assert len(tri) == 1
    assert tri[0].corroboration == 2
    assert tri[0].trust == "corroborated"


def test_same_method_twice_is_still_one_method():
    # corroboration counts DISTINCT methods, not finding objects.
    tri = triangulate([mk(method="ast"), mk(method="ast")])
    assert tri[0].corroboration == 1
    assert tri[0].trust == "single-method"


def test_multi_method_without_both_directions_is_not_corroborated():
    tri = triangulate([mk(method="ast", both_directions_proven=False),
                       mk(method="callgraph", both_directions_proven=False)])
    assert tri[0].corroboration == 2
    assert tri[0].trust == "multi-method"


def test_single_method_is_a_lead():
    tri = triangulate([mk(method="only")])
    assert tri[0].trust == "single-method"


def test_triangulate_sorts_most_corroborated_first():
    a1 = mk(location="s.py:1", method="ast", extra={"id_key": "S"})
    a2 = mk(location="s.py:1", method="mut", extra={"id_key": "S"})
    lone = mk(location="u.py:2", method="only")
    tri = triangulate([lone, a1, a2])
    assert tri[0].corroboration == 2
    assert tri[-1].corroboration == 1


def test_triangulate_max_confidence_is_the_group_max():
    tri = triangulate([mk(method="a", confidence=0.4, extra={"id_key": "S"}),
                       mk(method="b", confidence=0.9, extra={"id_key": "S"})])
    assert tri[0].max_confidence == 0.9


def test_triangulate_both_directions_any_true_if_any_member_has_it():
    tri = triangulate([mk(method="a", both_directions_proven=False, extra={"id_key": "S"}),
                       mk(method="b", both_directions_proven=True, extra={"id_key": "S"})])
    assert tri[0].both_directions_any is True


def test_triangulate_empty_input():
    assert triangulate([]) == []


def test_triangulate_preserves_every_finding():
    findings = [mk(method="a", extra={"id_key": "S"}),
                mk(method="b", extra={"id_key": "S"}),
                mk(location="z.py:9", method="c")]
    tri = triangulate(findings)
    assert sum(len(t.findings) for t in tri) == len(findings)


def test_triangulated_trust_property_directly():
    t = Triangulated("id", "gate", "d", "g.py:1", ["a", "b"], 0.9, 2, True, [])
    assert t.trust == "corroborated"
    assert Triangulated("id", "gate", "d", "g.py:1", ["a", "b"], 0.9, 2, False, []).trust \
        == "multi-method"
    assert Triangulated("id", "gate", "d", "g.py:1", ["a"], 0.9, 1, True, []).trust \
        == "single-method"


# ---------------------------------------------------------------- disagreement
def test_disagreement_flag_and_clear_names_direction():
    flag = Finding("test", "dead-canary", "t.py:1", "mutation survived", method="mutation")
    clr = Finding("test", "clean-verdict", "t.py:1", "asserts on real return", method="ast")
    dis = method_disagreements([flag, clr])
    assert len(dis) == 1
    assert "flagged by {mutation}" in dis[0]
    assert "called clean by {ast}" in dis[0]


def test_two_flags_is_not_a_disagreement():
    a = Finding("test", "d", "t.py:1", "x", method="m1")
    b = Finding("test", "d", "t.py:1", "x", method="m2")
    assert method_disagreements([a, b]) == []


def test_only_a_clear_is_not_a_disagreement():
    clr = Finding("test", "clean-verdict", "t.py:1", "x", method="ast")
    assert method_disagreements([clr]) == []


def test_same_method_flag_and_clear_is_not_a_disagreement():
    # if the SAME method both flags and clears, it is not two methods disagreeing.
    flag = Finding("test", "d", "t.py:1", "x", method="m")
    clr = Finding("test", "clean-verdict", "t.py:1", "x", method="m")
    assert method_disagreements([flag, clr]) == []


# ---------------------------------------------------------------- SARIF locations
def test_sarif_locations_file_line():
    locs = _sarif_locations("guard.py:40")
    assert locs[0]["physicalLocation"]["artifactLocation"]["uri"] == "guard.py"
    assert locs[0]["physicalLocation"]["region"]["startLine"] == 40


def test_sarif_locations_pipe_becomes_one_uri_per_path():
    locs = _sarif_locations("a/util.py | b/util.py")
    uris = [l["physicalLocation"]["artifactLocation"]["uri"] for l in locs]
    assert uris == ["a/util.py", "b/util.py"]


def test_sarif_locations_structural_becomes_logical():
    locs = _sarif_locations("call-graph:orphan:mod.f")
    assert "physicalLocation" not in locs[0]
    assert locs[0]["logicalLocations"][0]["fullyQualifiedName"] == "call-graph:orphan:mod.f"


def test_sarif_locations_non_digit_line_is_logical():
    # a colon whose tail is not a pure integer is not a real file position.
    locs = _sarif_locations("weird:notanumber")
    assert "logicalLocations" in locs[0]


# ---------------------------------------------------------------- SARIF document
def test_sarif_level_follows_trust():
    tri = triangulate([mk(method="ast", both_directions_proven=True),
                       mk(method="mut"),
                       mk(location="u.py:2", method="only")])
    sar = to_sarif(tri, "t")
    level_for = {}
    for r in sar["runs"][0]["results"]:
        for word in ("corroborated", "single-method"):
            if word in r["message"]["text"]:
                level_for[word] = r["level"]
    assert level_for["corroborated"] == "error"
    assert level_for["single-method"] == "warning"


def test_sarif_schema_version_and_rules():
    sar = to_sarif(triangulate([mk()]), "mytool")
    assert sar["version"] == "2.1.0"
    assert sar["$schema"].endswith("sarif-2.1.0.json")
    assert sar["runs"][0]["tool"]["driver"]["name"] == "mytool"
    assert sar["runs"][0]["tool"]["driver"]["rules"]


def test_sarif_message_carries_method_names_and_count():
    tri = triangulate([mk(method="ast", both_directions_proven=True), mk(method="mutation")])
    msg = to_sarif(tri, "t")["runs"][0]["results"][0]["message"]["text"]
    assert "2 method(s)" in msg
    assert "ast" in msg and "mutation" in msg


def test_sarif_empty_findings_is_valid_and_has_no_results():
    sar = to_sarif([], "t")
    assert sar["runs"][0]["results"] == []
    assert sar["runs"][0]["tool"]["driver"]["rules"] == []


def test_module_selftest_passes():
    from fullcircle import finding
    assert finding.selftest() == 0


# ---------------------------------------------------------------- property-based
def test_identity_is_deterministic_property():
    hypothesis = pytest.importorskip("hypothesis")
    from hypothesis import strategies as st

    @hypothesis.given(st.text(min_size=1, max_size=20), st.text(min_size=1, max_size=20),
                      st.text(min_size=1, max_size=20))
    def check(concept, defect_class, location):
        f1 = Finding(concept, defect_class, location, "s", method="a")
        f2 = Finding(concept, defect_class, location, "s", method="b")  # different method
        assert f1.identity() == f2.identity()
        assert len(f1.identity()) == 16

    check()


def test_triangulate_never_drops_findings_property():
    hypothesis = pytest.importorskip("hypothesis")
    from hypothesis import strategies as st

    finding_st = st.builds(
        Finding,
        concept=st.sampled_from(CONCEPTS),
        defect_class=st.sampled_from(["a", "b", "c"]),
        location=st.sampled_from(["x.py:1", "y.py:2", "z.py:3"]),
        signal=st.just("s"),
        method=st.sampled_from(["m1", "m2", "m3"]),
    )

    @hypothesis.given(st.lists(finding_st, max_size=25))
    def check(findings):
        tri = triangulate(findings)
        assert sum(len(t.findings) for t in tri) == len(findings)
        # corroboration never exceeds the number of distinct methods in a group
        for t in tri:
            assert t.corroboration == len({f.method for f in t.findings})

    check()
