"""Real behavioural tests for the portability core (behaviour -> concept classification and the
learned synonym map). The load-bearing property is label-independence: classification must key on
what the code DOES, never on what it is named.
"""
from __future__ import annotations

import ast

from fullcircle import concepts
from fullcircle.concepts import (
    CONCEPTS,
    ConceptMap,
    build_label_map,
    classify_function,
    concept_of_label,
    _claim_strings,
    _norm,
)


def _fn(src):
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return n
    raise AssertionError("no function in source")


# ---------------------------------------------------------------- classify_function
def test_assert_only_is_a_test():
    assert classify_function(_fn("def t():\n    assert x == 1\n")) == "test"


def test_exit_nonzero_is_a_gate():
    assert classify_function(_fn("import sys\ndef g(x):\n    if not x:\n        sys.exit(1)\n")) == "gate"


def test_guarded_raise_is_a_gate():
    assert classify_function(_fn("def g(x):\n    if not x:\n        raise ValueError('bad')\n")) == "gate"


def test_unconditional_raise_is_not_classified():
    assert classify_function(_fn("def h():\n    raise NotImplementedError\n")) is None


def test_clean_exit_zero_is_not_a_gate():
    assert classify_function(_fn("import sys\ndef f():\n    sys.exit(0)\n")) is None


def test_bare_exit_is_not_a_gate():
    assert classify_function(_fn("import sys\ndef f():\n    print('done')\n    sys.exit()\n")) is None


def test_if_only_function_is_not_a_gate():
    assert classify_function(_fn("def k(x):\n    if x:\n        return 1\n    return 0\n")) is None


def test_assert_and_exit_is_a_gate_not_a_test():
    src = "import sys\ndef g(x):\n    assert x\n    if not x:\n        sys.exit(2)\n"
    assert classify_function(_fn(src)) == "gate"


def test_on_exit_callback_is_not_a_gate():
    # a callee whose name merely ends in "exit" is not an actual exit call.
    assert classify_function(_fn("def cleanup():\n    on_exit('shutdown')\n")) is None
    assert classify_function(_fn("def cleanup():\n    handle_exit()\n")) is None


def test_plain_function_is_not_classified():
    assert classify_function(_fn("def add(a, b):\n    return a + b\n")) is None


def test_async_gate_is_classified():
    src = "import sys\nasync def g(x):\n    if not x:\n        sys.exit(1)\n"
    assert classify_function(_fn(src)) == "gate"


# ---------------------------------------------------------------- _norm
def test_norm_splits_snake_and_camel_and_lowercases():
    assert _norm("enforce_policy") == "enforce policy"
    assert _norm("validateToken") == "validate token"
    assert _norm("MAX_RETRIES") == "max retries"


def test_norm_drops_non_word_separators():
    assert _norm("a.b-c") == "a b c"


# ---------------------------------------------------------------- _claim_strings
def test_claim_string_is_collected():
    tree = ast.parse('msg = "All tests pass"\n')
    assert any("all tests pass" in c.lower() for c in _claim_strings(tree))


def test_plain_string_is_not_a_claim():
    tree = ast.parse('label = "just a short plain name"\n')
    assert _claim_strings(tree) == []


def test_long_claim_like_string_is_ignored():
    # the length guard: a >120-char string is not collected even if it contains a claim word.
    tree = ast.parse('x = "%s done"\n' % ("y" * 200))
    assert _claim_strings(tree) == []


# ---------------------------------------------------------------- concept_of_label
def test_learned_label_resolves():
    cm = ConceptMap()
    cm.add("gate", "enforce_policy", "a.py")
    assert concept_of_label(cm, "enforce_policy") == "gate"


def test_seed_synonym_resolves_without_being_observed():
    assert concept_of_label(ConceptMap(), "nightly_job") == "schedule"


def test_unrelated_label_resolves_to_none():
    assert concept_of_label(ConceptMap(), "banana_smoothie") is None


# ---------------------------------------------------------------- build_label_map (label independence)
def test_build_label_map_learns_by_behaviour(make_repo):
    root = make_repo({
        "app/enforce_policy.py": "import sys\ndef enforce_policy(x):\n    if not x:\n        sys.exit(1)\n    return True\n",
        "app/verify_widget.py": "def verify_widget():\n    assert 1 == 1\n",
        "app/core.py": "MAX_RETRIES = 5\ndef go():\n    print('All tests pass')\n    return 1\n",
    })
    cm = build_label_map(root)
    assert "enforce policy" in cm.labels["gate"]
    assert "verify widget" in cm.labels["test"]
    assert "max retries" in cm.labels["definition"]
    assert any("all tests pass" in c.lower() for c in cm.examples["claim"])


def test_classification_is_label_independent(make_repo):
    ordinary = make_repo({
        "a.py": "import sys\ndef enforce_policy(x):\n    if not x:\n        sys.exit(1)\n",
        "b.py": "def verify_widget():\n    assert 1 == 1\n",
    })
    nonsense = make_repo({
        "a.py": "import sys\ndef zqx(x):\n    if not x:\n        sys.exit(1)\n",
        "b.py": "def wpq():\n    assert 1 == 1\n",
    })
    m1, m2 = build_label_map(ordinary), build_label_map(nonsense)
    assert "zqx" in m2.labels["gate"]
    assert "wpq" in m2.labels["test"]
    # the COUNTS must be identical despite the different names
    assert len(m1.labels["gate"]) == len(m2.labels["gate"])
    assert len(m1.labels["test"]) == len(m2.labels["test"])


def test_build_label_map_prunes_vendored_dirs(make_repo):
    root = make_repo({
        ".venv/vend.py": "import sys\ndef vendored_gate(x):\n    if not x:\n        sys.exit(1)\n",
        "app/real.py": "import sys\ndef real_gate(x):\n    if not x:\n        sys.exit(1)\n",
    })
    cm = build_label_map(root)
    assert "real gate" in cm.labels["gate"]
    assert "vendored gate" not in cm.labels["gate"]


def test_build_label_map_only_learns_upper_case_constants(make_repo):
    root = make_repo({"app/m.py": "GOOD_CONST = 9\nlower_case = 5\n"})
    cm = build_label_map(root)
    assert "good const" in cm.labels["definition"]
    assert "lower case" not in cm.labels["definition"]


def test_build_label_map_survives_a_syntax_error(make_repo):
    root = make_repo({
        "broken.py": "def (((:\n",  # unparsable -> skipped, not a crash
        "ok.py": "import sys\ndef g(x):\n    if not x:\n        sys.exit(1)\n",
    })
    cm = build_label_map(root)
    assert "g" in cm.labels["gate"]


# ---------------------------------------------------------------- ConceptMap
def test_conceptmap_to_json_is_sorted_and_has_all_concepts():
    import json
    cm = ConceptMap()
    cm.add("gate", "check_it", "a.py")
    d = json.loads(cm.to_json())
    assert set(d["labels"]) == set(CONCEPTS)
    assert "check it" in d["labels"]["gate"]


def test_conceptmap_examples_are_capped_at_twelve():
    cm = ConceptMap()
    for i in range(30):
        cm.add("gate", "g%d" % i, "f%d.py" % i)
    assert len(cm.examples["gate"]) == 12
    # but every distinct label is still learned
    assert len(cm.labels["gate"]) == 30


def test_module_selftest_passes():
    assert concepts.selftest() == 0
