"""Real behavioural tests for the thin linker: cross-finder corroboration, the corroborated-vs-lead
partition, the 2-round cap with early convergence, the human-review routing of judgment classes, and
the SARIF aggregate. Uses synthetic finders so the loop/cap/queue logic is proven in isolation.
"""
from __future__ import annotations

from fullcircle import orchestrator
from fullcircle.orchestrator import JUDGMENT_CLASSES, _partition, _wire_real_finders, run
from fullcircle.finding import Finding, triangulate


def f1(root):
    return [Finding("gate", "no-clean-without-looking", "g.py:1", signal="s", method="ast",
                    both_directions_proven=True, extra={"id_key": "S"}),
            Finding("wire", "function-unwired", "u.py:2", signal="s", method="no-call-edge")]


def f2(root):
    return [Finding("gate", "no-clean-without-looking", "g.py:1", signal="s", method="mutation",
                    both_directions_proven=True, extra={"id_key": "S"}),
            Finding("definition", "conflicting-definition", "c.py:3", signal="s",
                    method="constant-conflict", both_directions_proven=True,
                    extra={"id_key": "conflict:X"})]


def test_cross_finder_corroboration():
    rep = run("/fake", [f1, f2])
    shared = [t for t in rep["findings"] if t.defect_class == "no-clean-without-looking"]
    assert shared and shared[0].corroboration == 2


def test_two_rounds_converge_without_a_fixer():
    rep = run("/fake", [f1, f2])
    assert len(rep["rounds"]) == 2
    assert rep["rounds"][1]["new"] == 0


def test_judgment_class_goes_to_human_review():
    rep = run("/fake", [f1, f2])
    assert "conflicting-definition" in {t.defect_class for t in rep["human_review_queue"]}


def test_single_method_lead_goes_to_human_review():
    rep = run("/fake", [f1, f2])
    assert any(t.defect_class == "function-unwired" for t in rep["human_review_queue"])


def test_corroborated_mechanical_is_auto_fixable():
    rep = run("/fake", [f1, f2])
    assert not any(t.defect_class == "no-clean-without-looking" for t in rep["human_review_queue"])
    assert any(t.defect_class == "no-clean-without-looking" for t in rep["auto_fixable"])


def test_round_corroborated_count_reflects_trust():
    rep = run("/fake", [f1, f2])
    assert rep["rounds"][0]["corroborated"] == 1


def test_early_convergence_break_stops_before_max_rounds():
    rep = run("/fake", [f1, f2], max_rounds=3)
    assert len(rep["rounds"]) == 2


def test_fixer_hook_is_invoked_and_counted():
    def fixer(auto, root):
        return len(auto)

    rep = run("/fake", [f1, f2], fixer=fixer)
    assert rep["rounds"][0]["fixed"] >= 1


def test_sarif_is_well_formed():
    rep = run("/fake", [f1, f2])
    assert rep["sarif"]["version"] == "2.1.0"
    assert "runs" in rep["sarif"]


def test_run_with_no_findings_is_empty_and_stable():
    rep = run("/fake", [lambda root: []])
    assert rep["findings"] == []
    assert rep["auto_fixable"] == []
    assert rep["human_review_queue"] == []


def test_message_reports_rounds_and_human_count():
    rep = run("/fake", [f1, f2])
    assert "round(s)" in rep["message"]
    assert "need a human decision" in rep["message"]


def test_partition_splits_auto_and_review():
    tri = triangulate([
        Finding("gate", "no-clean-without-looking", "g.py:1", signal="s", method="a",
                both_directions_proven=True, extra={"id_key": "S"}),
        Finding("gate", "no-clean-without-looking", "g.py:1", signal="s", method="b",
                both_directions_proven=True, extra={"id_key": "S"}),
        Finding("definition", "conflicting-definition", "c.py:3", signal="s", method="a",
                both_directions_proven=True, extra={"id_key": "C"}),
    ] + [Finding("definition", "conflicting-definition", "c.py:3", signal="s", method="b",
                 both_directions_proven=True, extra={"id_key": "C"})])
    auto, review = _partition(tri)
    assert any(t.defect_class == "no-clean-without-looking" for t in auto)
    assert any(t.defect_class == "conflicting-definition" for t in review)


def test_judgment_classes_content():
    assert "conflicting-definition" in JUDGMENT_CLASSES
    assert "law-or-rule-change" in JUDGMENT_CLASSES


def test_wire_real_finders_is_stable_and_nonempty():
    n1 = len(_wire_real_finders())
    n2 = len(_wire_real_finders())
    assert n1 >= 1
    assert n1 == n2


def test_wire_real_finders_includes_structural():
    from fullcircle import structural
    assert structural.raw_findings in _wire_real_finders()


def test_run_over_a_real_target_directory(make_repo):
    # end-to-end with the REAL wired finders over a planted target.
    root = make_repo({
        "core/orphan.py": "def compute_rebate(order):\n    return order * 0.1\n",
        "core/pay.py": "def settle(inv):\n    raise NotImplementedError\nsettle(1)\n",
    })
    rep = run(root, _wire_real_finders())
    assert rep["target"] == root
    got = {t.defect_class for t in rep["findings"]}
    assert "function-unwired" in got
    assert "stub-implementation" in got


def test_module_selftest_passes():
    assert orchestrator.selftest() == 0
