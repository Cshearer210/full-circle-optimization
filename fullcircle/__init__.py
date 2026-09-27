"""full-circle-optimization -- find what a system PROMISES but does not do, then fix it safely.

⛔ WHY THIS FILE EXISTS, ADDED 2026-09-27, AND ITS ABSENCE WAS INVISIBLE. Until now there was no
`__init__.py` here at all, so `fullcircle` was an implicit NAMESPACE package: `pip install .`
succeeded, `import fullcircle` succeeded, and `fullcircle.__file__` was **None** with no `__all__`
and nothing importable from the top level. Every test passed the whole time, because the tests run
from the checkout where each module is reachable by path. The one person it failed for was a
stranger who installed it -- which is the only person packaging is for.

⭐ THE PUBLIC SURFACE IS DELIBERATELY SMALL: the pipeline, the finding contract, the shared concept
layer, and the safe fixer. The detectors and testbeds stay behind their own modules, because they
are the parts a caller extends rather than calls.

Every module is standard library only. There are no runtime dependencies, and nothing reaches the
network.
"""
from __future__ import annotations

__version__ = "0.1.0"

from .concepts import ConceptMap, build_label_map, classify_function, concept_of_label, rel_id
from .finding import Finding, Triangulated, method_disagreements, to_sarif, triangulate
from .fixer import apply_fixes
from .orchestrator import run
from .structural import raw_findings, scan

__all__ = [
    # the pipeline
    "run",
    # the shared finding contract, and the triangulation that makes a finding trustworthy
    "Finding", "Triangulated", "triangulate", "method_disagreements", "to_sarif",
    # the portability core: classify by behaviour, learn the target's own labels
    "ConceptMap", "build_label_map", "classify_function", "concept_of_label", "rel_id",
    # the structural detectors, and the safe fix engine
    "scan", "raw_findings", "apply_fixes",
    "__version__",
]
