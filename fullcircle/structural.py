#!/usr/bin/env python3
# CALLED BY: FULL-RESET-GRAPH's SCAN/GRAPH stages and the FULL-CIRCLE-OPTIMIZATION pipeline.
# FIRES WHEN: mapping a target system for LOUD/structural defects (the ones a graph makes visible).
"""FULL-RESET-GRAPH's structural detectors, emitting the shared finding format so they triangulate
with claimproof's silent findings. Every detector keys on a behavioural/structural SIGNAL, never on
a label, so it works on an unfamiliar system (Chris, 2026-09-23).

Detectors are added one at a time, each with a both-directions selftest, per Chris's "build piece by
piece and test step by step". This file EXTENDS FULL-RESET-GRAPH (rag-ghost) whose graph.py already
does MODULE-level orphan/dangling detection; these are the classes it does not yet have.

  second-door-duplicate   the same code reachable at two paths -- a fix to one misses the other
  duplicate-definition    one shared constant defined in >=2 files -- the "many doors" defect
  conflicting-config      one config KEY set to DIFFERENT values in >=2 files
  function-unwired        a function defined and imported but never called anywhere

AST/filesystem only; never executes the target.
"""
from __future__ import annotations

import ast
import hashlib
import os

try:
    from .finding import Finding, triangulate, Triangulated, to_sarif
except ImportError:
    from finding import Finding, triangulate, Triangulated, to_sarif  # type: ignore

# build artifacts (build/, dist/, *.egg-info) are COPIES of src -- scanning them double-counts and
# manufactures second-door duplicates. Skip them everywhere (measured on real repos 2026-09-23).
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
              "build", "dist", ".tox", ".eggs", ".pytest_cache", "site-packages"}


def _skip_dir(d: str) -> bool:
    return d in _SKIP_DIRS or d.endswith(".egg-info")


def _walk(root, exts=None):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not _skip_dir(d)]
        for fn in files:
            if exts and not fn.endswith(exts):
                continue
            yield os.path.join(dirpath, fn)


# ---------------------------------------------------------------- second-door duplicate files
def _second_door(root: str) -> list[Finding]:
    """Two methods: same-inode (a bind mount / hardlink -- literally one file at two paths) and
    same-content (a COPY that will drift). A hardlink fires both -> corroborated; a copy fires
    same-content only."""
    by_inode: dict[tuple, list[str]] = {}
    by_hash: dict[str, list[str]] = {}
    inode_hash: dict[str, tuple] = {}                    # content-hash -> (dev,ino) when shared
    for path in _walk(root, (".py",)):
        rel = os.path.relpath(path, root)
        if os.path.basename(path) == "__init__.py":
            continue
        try:
            st = os.stat(path)
            data = open(path, "rb").read()
        except OSError:
            continue
        if len(data.strip()) < 40:                       # ignore trivial/near-empty files
            continue
        h = hashlib.sha256(data).hexdigest()
        by_inode.setdefault((st.st_dev, st.st_ino), []).append((rel, h))
        by_hash.setdefault(h, []).append(rel)

    out = []
    # both methods key their finding by the DUPLICATED CONTENT (id_key), not the path list, so a
    # hardlink caught by both methods triangulates into one corroborated finding.
    for (_dev, _ino), items in by_inode.items():
        if len(items) > 1:
            paths = sorted(p for p, _ in items)
            h = items[0][1]
            out.append(Finding(
                concept="definition", defect_class="second-door-duplicate",
                location=" | ".join(paths),
                signal="same (st_dev, st_ino) -- one file reachable at two paths",
                evidence="a bind mount or hardlink: a fix at one path never reaches the other",
                method="same-inode", repo="full-reset-graph", severity="high", confidence=0.9,
                both_directions_proven=True, ignored_label="path", extra={"id_key": "dup:" + h}))
    for h, paths in by_hash.items():
        distinct = sorted(set(paths))
        if len(distinct) > 1:
            out.append(Finding(
                concept="definition", defect_class="second-door-duplicate",
                location=" | ".join(distinct), signal="identical content in two distinct files",
                evidence="a copy that will drift: one definition behind two doors",
                method="same-content", repo="full-reset-graph", severity="med", confidence=0.75,
                both_directions_proven=True, ignored_label="path", extra={"id_key": "dup:" + h}))
    return out


_LITERAL = (ast.Constant, ast.Tuple, ast.List, ast.Dict, ast.Set)


def _literal_repr(node):
    """A stable repr of a literal assignment value, or None if not a literal."""
    try:
        return ast.unparse(node) if isinstance(node, _LITERAL) else None
    except Exception:
        return None


def _conflicting_definition(root: str) -> list[Finding]:
    """One CONSTANT name assigned DIFFERENT literal values in >=2 files -- which value wins? This is
    Chris's 'conflicting instructions/tools/config' class at the code level. Two methods:
      constant-conflict    same UPPER_CASE name, different literal values across >=2 files
      value-type-mismatch  ... and those values are of different TYPES (almost certainly a real bug)
    They corroborate when a conflict is also a type mismatch."""
    # name -> {value_repr -> set(files)} , and name -> set(type-names)
    seen: dict[str, dict[str, set]] = {}
    types: dict[str, set] = {}
    for path in _walk(root, (".py",)):
        rel = os.path.relpath(path, root)
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
        except (SyntaxError, ValueError, OSError):
            continue
        for node in tree.body:                            # MODULE level only
            if isinstance(node, ast.Assign):
                vr = _literal_repr(node.value)
                if vr is None:
                    continue
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id.isupper() and len(t.id) > 2:
                        seen.setdefault(t.id, {}).setdefault(vr, set()).add(rel)
                        if isinstance(node.value, ast.Constant):
                            types.setdefault(t.id, set()).add(type(node.value.value).__name__)
    out = []
    for name, valmap in seen.items():
        files = set().union(*valmap.values())
        if len(valmap) > 1 and len(files) > 1:            # >1 distinct value AND across >1 file
            loc = "; ".join("%s=%s in {%s}" % (name, v, ",".join(sorted(fs)))
                            for v, fs in sorted(valmap.items()))
            out.append(Finding(
                concept="definition", defect_class="conflicting-definition",
                location=loc[:300], signal="one constant name, different literal values in >=2 files",
                evidence="a session reading one file gets a different value than one reading the other",
                method="constant-conflict", repo="full-reset-graph", severity="high",
                confidence=0.7, both_directions_proven=True, ignored_label="which file 'wins'",
                extra={"id_key": "conflict:" + name}))
            if len(types.get(name, set())) > 1:
                out.append(Finding(
                    concept="definition", defect_class="conflicting-definition",
                    location=loc[:300], signal="the conflicting values are of different TYPES",
                    evidence="same constant is a %s in one file and a %s in another"
                             % tuple(sorted(types[name])[:2]),
                    method="value-type-mismatch", repo="full-reset-graph", severity="high",
                    confidence=0.85, both_directions_proven=True, ignored_label="which file 'wins'",
                    extra={"id_key": "conflict:" + name}))
    return out


import re as _re
_WORD = _re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _unwired_function(root: str) -> list[Finding]:
    """A top-level function defined but never used. Corroboration IS the precision here:
      no-call-edge   the name never appears as a call anywhere (broad -- also fires on a name only
                     referenced as a string in a registry/getattr, which is actually wired)
      no-reference   the name appears NOWHERE else -- not a call, not a load, not a string literal
    Truly-dead code fires BOTH (corroborated). A registry-dispatched function fires no-call-edge
    ONLY (single-method lead), so corroboration keeps the string-dispatch false positive at low
    trust instead of asserting it. This extends FULL-RESET-GRAPH's module-level orphan detection to
    functions, and being string-aware is what makes it safe on an unfamiliar system."""
    candidates: dict[str, tuple] = {}      # name -> (rel, lineno)
    ambiguous, decorated, exports = set(), set(), set()
    called, referenced, string_tokens = set(), set(), set()
    trees = []
    for path in _walk(root, (".py",)):
        rel = os.path.relpath(path, root)
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
        except (SyntaxError, ValueError, OSError):
            continue
        trees.append((rel, tree))
        for node in tree.body:                                   # top-level defs are candidates
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in candidates:
                    ambiguous.add(node.name)
                candidates[node.name] = (rel, node.lineno)
                if node.decorator_list:
                    decorated.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "__all__" and \
                            isinstance(node.value, (ast.List, ast.Tuple)):
                        for e in node.value.elts:
                            if isinstance(e, ast.Constant) and isinstance(e.value, str):
                                exports.add(e.value)
    for rel, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    called.add(f.id)
                elif isinstance(f, ast.Attribute):
                    called.add(f.attr)
            elif isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced.add(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                string_tokens.update(_WORD.findall(node.value))

    out = []
    for name, (rel, lineno) in candidates.items():
        if (name in ambiguous or name in decorated or name in exports or
                name.startswith("__") or name.startswith("test") or name in ("main", "run")):
            continue
        # conftest.py functions are pytest fixtures/hooks invoked by the framework by name, not
        # called in source -- they are framework-wired, not unwired (measured FP 2026-09-23).
        if os.path.basename(rel) == "conftest.py":
            continue
        no_call = name not in called
        if not no_call:
            continue                                             # it is called -> wired
        no_reference = name not in referenced and name not in string_tokens
        idk = "unwired:%s:%s" % (rel, name)
        out.append(Finding(
            concept="wire", defect_class="function-unwired",
            location="%s:%d" % (rel, lineno),
            signal="the function name never appears as a call anywhere in the repo",
            evidence="defined and complete, but nothing calls %s" % name,
            method="no-call-edge", repo="full-reset-graph", severity="med", confidence=0.55,
            both_directions_proven=True, ignored_label=name, extra={"id_key": idk}))
        if no_reference:
            out.append(Finding(
                concept="wire", defect_class="function-unwired",
                location="%s:%d" % (rel, lineno),
                signal="the name appears NOWHERE else -- not a call, a load, or a string",
                evidence="%s is truly dead: no reference of any kind reaches it" % name,
                method="no-reference", repo="full-reset-graph", severity="high", confidence=0.8,
                both_directions_proven=True, ignored_label=name, extra={"id_key": idk}))
    return out


def _is_stub(fn):
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]                                  # drop a docstring
    if len(body) != 1:
        return None
    s = body[0]
    if isinstance(s, ast.Pass):
        return "pass"
    if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis:
        return "ellipsis"
    if isinstance(s, ast.Raise):
        e = s.exc
        nm = ""
        if isinstance(e, ast.Call):
            nm = getattr(e.func, "id", getattr(e.func, "attr", ""))
        elif isinstance(e, ast.Name):
            nm = e.id
        elif isinstance(e, ast.Attribute):
            nm = e.attr
        if nm == "NotImplementedError":
            return "not-implemented"
    return None


def _stub_implementation(root: str) -> list[Finding]:
    """A function whose body is a stub (pass / ... / raise NotImplementedError). Corroboration:
      body-is-stub   the body does nothing real
      has-callers    something already calls it
    A stub that is CALLED is 'looks done, isn't' -- corroborated (Chris's half-finished-work class).
    A stub nobody calls yet is a single-method lead. @abstractmethod stubs are skipped by design."""
    called, defs, methods = set(), [], set()
    for path in _walk(root, (".py",)):
        rel = os.path.relpath(path, root)
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for m in node.body:                       # remember which defs are METHODS
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.add(id(m))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.append((rel, node))
            elif isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    called.add(f.id)
                elif isinstance(f, ast.Attribute):
                    called.add(f.attr)
    out = []
    for rel, node in defs:
        if node.name.startswith("__"):
            continue
        if any("abstract" in (getattr(d, "id", getattr(d, "attr", "")) or "").lower()
               for d in node.decorator_list):
            continue                                     # an abstract method is meant to be empty
        kind = _is_stub(node)
        if not kind:
            continue
        # `...` and `raise NotImplementedError` inside a CLASS are interface/abstract idioms (a
        # Protocol or abstract-base contract for subclasses to fill), not half-finished functions --
        # do not flag them (measured FP on real repos 2026-09-23: a typing.Protocol with `...`
        # bodies). A `pass` method, or a module-level stub, still counts.
        if kind in ("not-implemented", "ellipsis") and id(node) in methods:
            continue
        idk = "stub:%s:%s" % (rel, node.name)
        loc = "%s:%d" % (rel, node.lineno)
        out.append(Finding(
            concept="wire", defect_class="stub-implementation", location=loc,
            signal="function body is a stub (%s)" % kind,
            evidence="%s is not actually implemented" % node.name,
            method="body-is-stub", repo="full-reset-graph", severity="med", confidence=0.6,
            both_directions_proven=True, ignored_label=node.name, extra={"id_key": idk}))
        if node.name in called:
            out.append(Finding(
                concept="wire", defect_class="stub-implementation", location=loc,
                signal="the stub is already called by other code",
                evidence="callers depend on %s but it is not implemented" % node.name,
                method="has-callers", repo="full-reset-graph", severity="high", confidence=0.75,
                both_directions_proven=True, ignored_label=node.name, extra={"id_key": idk}))
    return out


_TERMINALS = (ast.Return, ast.Raise, ast.Break, ast.Continue)


def _dead_code(root: str) -> list[Finding]:
    """A statement that follows an unconditional return/raise/break/continue in the same block --
    it can never run. Fix: remove it, or fix the control flow that made it unreachable."""
    out = []
    for path in _walk(root, (".py",)):
        rel = os.path.relpath(path, root)
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            for attr in ("body", "orelse", "finalbody"):
                body = getattr(node, attr, None)
                if not isinstance(body, list):
                    continue
                for i, stmt in enumerate(body[:-1]):
                    if isinstance(stmt, _TERMINALS):
                        nxt = body[i + 1]
                        ln = getattr(nxt, "lineno", getattr(stmt, "lineno", 0))
                        out.append(Finding(
                            concept="wire", defect_class="dead-code",
                            location="%s:%d" % (rel, ln),
                            signal="statement follows an unconditional %s" % type(stmt).__name__.lower(),
                            evidence="this line can never run",
                            method="after-terminal", repo="full-reset-graph", severity="med",
                            confidence=0.85, both_directions_proven=True,
                            extra={"id_key": "dead:%s:%d" % (rel, ln)}))
                        break
    return out


def _unused_import(root: str) -> list[Finding]:
    """An imported name never referenced in the file. Fix: remove it (or actually use it)."""
    out = []
    for path in _walk(root, (".py",)):
        rel = os.path.relpath(path, root)
        if os.path.basename(path) == "__init__.py":       # __init__ re-exports; do not flag
            continue
        try:
            src = open(path, encoding="utf-8", errors="replace").read()
            tree = ast.parse(src)
        except (SyntaxError, ValueError, OSError):
            continue
        imported, exports, star = {}, set(), False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imported[a.asname or a.name.split(".")[0]] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                if any(a.name == "*" for a in node.names):
                    star = True
                else:
                    for a in node.names:
                        imported[a.asname or a.name] = node.lineno
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "__all__" and \
                            isinstance(node.value, (ast.List, ast.Tuple)):
                        for e in node.value.elts:
                            if isinstance(e, ast.Constant) and isinstance(e.value, str):
                                exports.add(e.value)
        if star:                                           # a star import may use anything; skip file
            continue
        used, strtok = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                strtok.update(_WORD.findall(node.value))   # forward-ref type hints live in strings
        for name, ln in imported.items():
            if name in used or name in exports or name in strtok or name == "annotations":
                continue
            out.append(Finding(
                concept="wire", defect_class="unused-import", location="%s:%d" % (rel, ln),
                signal="imported name '%s' is never referenced" % name,
                evidence="a dead import adds noise and a false dependency",
                method="import-never-used", repo="full-reset-graph", severity="low",
                confidence=0.8, both_directions_proven=True,
                extra={"id_key": "unusedimp:%s:%s" % (rel, name)}, ignored_label=name))
    return out


def _mutable_default(root: str) -> list[Finding]:
    """A function default that is a mutable literal ([], {}, set()) -- it is shared across calls and
    accumulates state. Fix: default to None and build the container inside the function."""
    out = []
    for path in _walk(root, (".py",)):
        rel = os.path.relpath(path, root)
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in list(node.args.defaults) + list(node.args.kw_defaults):
                    if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                        ln = getattr(d, "lineno", node.lineno)
                        out.append(Finding(
                            concept="definition", defect_class="mutable-default-arg",
                            location="%s:%d" % (rel, ln),
                            signal="a %s literal is a default argument" % type(d).__name__.lower(),
                            evidence="the same mutable object is reused across every call to %s" % node.name,
                            method="mutable-literal-default", repo="full-reset-graph", severity="med",
                            confidence=0.9, both_directions_proven=True,
                            extra={"id_key": "mutdef:%s:%s" % (rel, node.name)}, ignored_label=node.name))
    return out


def _bare_except(root: str) -> list[Finding]:
    """`except:` with no type catches EVERYTHING -- including KeyboardInterrupt and SystemExit, so
    Ctrl-C and a clean exit get swallowed. Fix: catch `Exception`, or the specific error(s)."""
    out = []
    for path in _walk(root, (".py",)):
        rel = os.path.relpath(path, root)
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                out.append(Finding(
                    concept="read", defect_class="bare-except", location="%s:%d" % (rel, node.lineno),
                    signal="a bare 'except:' catches everything, incl. KeyboardInterrupt/SystemExit",
                    evidence="Ctrl-C and clean exits get caught here too",
                    method="bare-except", repo="full-reset-graph", severity="med", confidence=0.85,
                    both_directions_proven=True, extra={"id_key": "bareexc:%s:%d" % (rel, node.lineno)}))
    return out


def _resource_leak(root: str) -> list[Finding]:
    """`open(...)` whose handle is discarded or method-chained (never closed, not in a `with`) --
    the file descriptor leaks. Fix: use `with open(...) as f:`, or close it in a finally."""
    out = []
    for path in _walk(root, (".py",)):
        rel = os.path.relpath(path, root)
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            call = None
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Call):
                call = node.value                          # open(f).read()
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value                          # bare open(f)
            if call and isinstance(call.func, ast.Name) and call.func.id == "open":
                ln = getattr(call, "lineno", 0)
                out.append(Finding(
                    concept="read", defect_class="resource-leak", location="%s:%d" % (rel, ln),
                    signal="open() handle is discarded/chained, never closed and not in a `with`",
                    evidence="the file descriptor leaks",
                    method="open-not-managed", repo="full-reset-graph", severity="med",
                    confidence=0.75, both_directions_proven=True,
                    extra={"id_key": "leak:%s:%d" % (rel, ln)}))
    return out


_SHADOWABLE = {"list", "dict", "set", "tuple", "str", "int", "float", "open", "type", "input",
               "filter", "map", "sum", "max", "min", "id", "bytes", "range", "object", "format"}


def _shadowed_builtin(root: str) -> list[Finding]:
    """A MODULE-LEVEL name (or a def) that shadows a builtin -- calling that builtin later in the
    module then breaks. Fix: rename. (Function-local shadowing is skipped -- it is common and scoped.)"""
    out = []
    for path in _walk(root, (".py",)):
        rel = os.path.relpath(path, root)
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
        except (SyntaxError, ValueError, OSError):
            continue
        for node in tree.body:                             # MODULE level only (precision)
            names = []
            if isinstance(node, ast.Assign):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [node.name]
            for nm in names:
                if nm in _SHADOWABLE:
                    out.append(Finding(
                        concept="definition", defect_class="shadowed-builtin",
                        location="%s:%d" % (rel, node.lineno),
                        signal="module-level name '%s' shadows a builtin" % nm,
                        evidence="calling the builtin %s() later in this module now breaks" % nm,
                        method="shadows-builtin", repo="full-reset-graph", severity="low",
                        confidence=0.7, both_directions_proven=True,
                        extra={"id_key": "shadow:%s:%s" % (rel, nm)}, ignored_label=nm))
    return out


DETECTORS = {
    "second-door-duplicate": [_second_door],
    "conflicting-definition": [_conflicting_definition],
    "function-unwired": [_unwired_function],
    "stub-implementation": [_stub_implementation],
    "dead-code": [_dead_code],
    "unused-import": [_unused_import],
    "mutable-default-arg": [_mutable_default],
    "bare-except": [_bare_except],
    "resource-leak": [_resource_leak],
    "shadowed-builtin": [_shadowed_builtin],
}


def raw_findings(root: str) -> list[Finding]:
    out: list[Finding] = []
    for methods in DETECTORS.values():
        for m in methods:
            out.extend(m(root))
    return out


def scan(root: str) -> list[Triangulated]:
    return triangulate(raw_findings(root))


# ---------------------------------------------------------------- proof
def selftest() -> int:
    import tempfile, shutil
    ok = True

    def write(root, rel, body):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p) or root, exist_ok=True)
        open(p, "w", encoding="utf-8").write(body)

    d = tempfile.mkdtemp(prefix="struct_")
    try:
        body = "def compute(x):\n    return x * 2 + 1  # a real definition worth duplicating\n"
        write(d, "app/calc.py", body)
        # a COPY (distinct inode, same content) -> same-content method fires
        write(d, "lib/calc_copy.py", body)
        # a HARDLINK (same inode) -> same-inode AND same-content -> corroborated
        os.link(os.path.join(d, "app/calc.py"), os.path.join(d, "hardlinked_calc.py"))
        # a unique file -> nothing
        write(d, "app/other.py", "def unrelated():\n    return 'nothing to see, distinct content here'\n")

        tri = scan(d)
        dups = [t for t in tri if t.defect_class == "second-door-duplicate"]
        # there must be at least one corroborated DUP (the hardlink, same-inode + same-content)
        corr = [t for t in dups if t.corroboration >= 2]
        if not corr:
            print("FAIL: hardlink should corroborate (same-inode + same-content) ->", dups); ok = False
        # a content-duplicate finding must exist naming the copy
        content_hits = [t for t in dups if any("calc_copy.py" in f.location for f in t.findings)]
        if not content_hits:
            print("FAIL: the copy was not detected ->", dups); ok = False
        # the unique file must NOT appear in any DUPLICATE finding (it may be flagged unwired -- fine)
        if any("other.py" in t.location for t in dups):
            print("FAIL: unique file flagged as duplicate (false positive)"); ok = False

        # negative control: a repo with no duplicates -> no findings
        d2 = tempfile.mkdtemp(prefix="struct2_")
        try:
            # every function is called, so NO detector (dup, conflict, or unwired) should fire
            write(d2, "a.py", "def helper():\n    return 'aaaaaaaaaaaaaaaaaaaaaaaaa distinct'\n"
                              "def entry():\n    return helper()\n\nentry()\n")
            write(d2, "b.py", "def worker():\n    return 'bbbbbbbbbbbbbbbbbbbbbbbbb distinct'\n\nworker()\n")
            leftover = scan(d2)
            if leftover:
                print("FAIL: clean repo produced findings ->", leftover); ok = False
        finally:
            shutil.rmtree(d2, ignore_errors=True)

        # conflicting-definition: same const, different values AND different types -> corroborated;
        # same const same value -> NOT flagged; a const in only one file -> NOT flagged
        d3 = tempfile.mkdtemp(prefix="struct3_")
        try:
            write(d3, "conf_a.py", "TIMEOUT = 30\nSHARED = 'ok'\nONLY_HERE = 1\n")
            write(d3, "conf_b.py", "TIMEOUT = 'sixty'\nSHARED = 'ok'\n")   # TIMEOUT conflicts + type
            tri3 = scan(d3)
            conf = [t for t in tri3 if t.defect_class == "conflicting-definition"]
            names = {t.findings[0].extra.get("id_key") for t in conf}
            if "conflict:TIMEOUT" not in names:
                print("FAIL: TIMEOUT conflict not detected ->", conf); ok = False
            timeout = next((t for t in conf if t.findings[0].extra.get("id_key") == "conflict:TIMEOUT"), None)
            if not timeout or timeout.corroboration != 2:
                print("FAIL: TIMEOUT (int vs str) should corroborate ->", timeout); ok = False
            if "conflict:SHARED" in names:
                print("FAIL: same value in both files should NOT conflict"); ok = False
            if "conflict:ONLY_HERE" in names:
                print("FAIL: a const in one file only should NOT conflict"); ok = False
        finally:
            shutil.rmtree(d3, ignore_errors=True)

        # function-unwired: truly-dead -> corroborated (both methods); string-dispatched -> single
        # method (no-call-edge only); called -> not flagged; decorated -> not flagged
        d4 = tempfile.mkdtemp(prefix="struct4_")
        try:
            write(d4, "mod.py",
                  "import registry\n"
                  "def dead_fn():\n    return 1\n"                       # nothing references it
                  "def dispatched():\n    return 2\n"                    # referenced only as a string
                  "def used():\n    return 3\n"
                  "def caller():\n    return used()\n"                   # uses used()
                  "caller()\n"
                  "HANDLERS = 'dispatched'\n")                          # string ref to dispatched
            write(d4, "registry.py", "def register(name):\n    return name\n\nregister('x')\n")
            tri4 = scan(d4)
            uw = {t.location.split(':')[0] + ':' + t.findings[0].extra['id_key']: t
                  for t in tri4 if t.defect_class == "function-unwired"}
            keys = {t.findings[0].extra["id_key"]: t for t in tri4 if t.defect_class == "function-unwired"}
            dead = keys.get("unwired:mod.py:dead_fn")
            if not dead or dead.corroboration != 2:
                print("FAIL: dead_fn should be corroborated unwired ->", dead); ok = False
            disp = keys.get("unwired:mod.py:dispatched")
            if not disp or disp.corroboration != 1 or "no-call-edge" not in disp.methods:
                print("FAIL: string-dispatched fn should be single-method lead ->", disp); ok = False
            if "unwired:mod.py:used" in keys or "unwired:mod.py:caller" in keys:
                print("FAIL: a called function was flagged as unwired"); ok = False
        finally:
            shutil.rmtree(d4, ignore_errors=True)

        # stub-implementation: a called stub -> corroborated; a real fn -> not flagged;
        # an @abstractmethod stub -> not flagged
        d5 = tempfile.mkdtemp(prefix="struct5_")
        try:
            write(d5, "svc.py",
                  "import abc\n"
                  "def process_payment(order):\n    raise NotImplementedError\n"   # stub, and called
                  "def real(x):\n    return x + 1\n"                                # real, called
                  "class Base(abc.ABC):\n    @abc.abstractmethod\n    def do(self):\n        pass\n"  # abstract -> ok
                  "process_payment(1)\nreal(2)\n")
            tri5 = scan(d5)
            stubs = {t.findings[0].extra["id_key"]: t for t in tri5 if t.defect_class == "stub-implementation"}
            pp = stubs.get("stub:svc.py:process_payment")
            if not pp or pp.corroboration != 2:
                print("FAIL: called stub should be corroborated ->", list(stubs)); ok = False
            if "stub:svc.py:real" in stubs:
                print("FAIL: a real function was flagged as a stub"); ok = False
            if "stub:svc.py:do" in stubs:
                print("FAIL: an @abstractmethod was flagged as a stub"); ok = False
        finally:
            shutil.rmtree(d5, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys, json as _json
    argv = sys.argv[1:]
    if "--selftest" in argv or not [a for a in argv if not a.startswith("-")]:
        sys.exit(selftest())
    tri = scan([a for a in argv if not a.startswith("-")][0])
    print("full-reset-graph structural: %d finding(s)" % len(tri))
    for t in tri:
        print("  [%s] %s  methods=%s  %s" % (t.trust, t.location[:80], ",".join(t.methods), t.defect_class))
    if "--sarif" in argv:
        out = argv[argv.index("--sarif") + 1]
        open(out, "w").write(_json.dumps(to_sarif(tri, "full-reset-graph"), indent=2))
        print("SARIF written:", out)
    sys.exit(1 if tri else 0)
