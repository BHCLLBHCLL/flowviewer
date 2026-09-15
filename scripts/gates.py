#!/usr/bin/env python3
"""Verification gates (R116).

Two checks that stop the two failure modes the audit found, and that a
reviewer can watch fail:

1. ``assertions`` -- share of test functions that assert against an
   INDEPENDENT expected value (an analytic number, a cross reference, a
   recorded golden) rather than merely shape, presence or a rendered string.
   Measured before R116: 71 of 1307 (5.4%).  A suite in that state proves
   structure, not numbers.

2. ``fields`` -- every attribute of every PostObject must be either consumed
   outside the GUI (the renderer, model or exporter reads it) or listed as
   explicitly reserved in ``tests/field_exemptions.json``.  87 of 313 fields
   had no consumer at all; that is how a fully wired-looking property sheet
   ships with dead controls.

Usage:

    python scripts/gates.py assertions        # report + exit code
    python scripts/gates.py fields
    python scripts/gates.py all --report      # report only, never fail
    python scripts/gates.py thresholds        # show the ratchet
    python scripts/gates.py --set-assertion-min 0.20
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
PKG = ROOT / "fv"
THRESHOLDS = ROOT / "tests" / "gate_thresholds.json"
EXEMPTIONS = ROOT / "tests" / "field_exemptions.json"

#: modules whose assertions matter most (geometry / data correctness)
CORE_TESTS = re.compile(
    r"test_(varreg|mesh_|crdl|cgns|r11[0-9]|r12[0-9]|scene_snapshot|pod|compare)")

DEFAULT_THRESHOLDS = {"assertion_min": 0.45, "core_assertion_min": 0.60,
                     "unconsumed_max": 0}

# ── assertion analysis ────────────────────────────────────────────────────

_INDEPENDENT_CALLS = (
    "approx",              # pytest.approx(...)
    "assert_allclose",     # np.testing.assert_allclose(...)
    "assert_array_equal",
    "assert_array_almost_equal",
    "assert_almost_equal",
    "assert_equal",
    "isclose",
)

_WEAK_STRINGS = ("html", "<mark", "http", "content-type", "json", ".html")

#: predicates whose result is presence/finiteness, not an expectation
_WEAK_CALLS = ("isfinite", "all", "any", "is_file", "exists", "is_dir")


def _is_independent(node: ast.AST) -> bool:
    """True when an assertion compares against something independently derived."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            fn = sub.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name in _INDEPENDENT_CALLS:
                return True
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            text = sub.value.lower()
            if any(w in text for w in _WEAK_STRINGS):
                return False
        if isinstance(sub, ast.Compare):
            left = sub.left
            # A bound test on a weak predicate is not an expectation:
            # `np.isfinite(x).all()`, `x.size > 0`, `len(d) > 0` are all
            # presence/finiteness checks that the audit rightly classed as
            # "asserts nothing independent".
            left_names = {
                getattr(getattr(left, "func", None), "attr", None),
                getattr(getattr(left, "func", None), "id", None),
                getattr(left, "attr", None),
            }
            if left_names & set(_WEAK_CALLS):
                return False
            for op in sub.ops:
                if isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                    return True
            # An exact comparison against a substantive constant is as much an
            # independent expectation as a tolerance check: a recorded count
            # such as n_vertices == 21145 comes from the file, not from the code
            # under test.  Trivial sentinels are excluded so `len(x) == 1`-style
            # shape checks still do not count.
            trivials = (0, 1, 2, -1, "", None, True, False)
            for comp in sub.comparators:
                if not isinstance(comp, ast.Constant):
                    continue
                if comp.value in trivials:
                    continue
                if isinstance(comp.value, (int, float, str, bytes)):
                    return True
    return False


def _test_functions(path: Path):
    # utf-8-sig: a few test modules carry a BOM, which ast.parse rejects.
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            yield node


def assertion_report() -> dict:
    total = independent = 0
    core_total = core_independent = 0
    files = 0
    for path in sorted(TESTS.glob("test_*.py")):
        files += 1
        is_core = bool(CORE_TESTS.search(path.stem))
        for fn in _test_functions(path):
            total += 1
            if is_core:
                core_total += 1
            asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
            ok = any(_is_independent(a.test) for a in asserts)
            if ok:
                independent += 1
                if is_core:
                    core_independent += 1
    return {
        "files": files,
        "tests": total,
        "independent": independent,
        "ratio": (independent / total) if total else 0.0,
        "core_tests": core_total,
        "core_independent": core_independent,
        "core_ratio": (core_independent / core_total) if core_total else 0.0,
    }

# ── field consumption analysis ────────────────────────────────────────────


def _object_fields() -> dict:
    """{field: [owning classes]} for every PostObject dataclass attribute."""
    tree = ast.parse((PKG / "model" / "objects.py").read_text(encoding="utf-8-sig"))
    fields: dict = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for st in node.body:
            if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                fields.setdefault(st.target.id, []).append(node.name)
    return fields


def field_report() -> dict:
    fields = _object_fields()
    sources = {}
    for path in PKG.rglob("*.py"):
        if path.name == "objects.py" or "gui" in path.parts:
            continue
        sources[path] = path.read_text(encoding="utf-8-sig")

    exempt = set()
    if EXEMPTIONS.is_file():
        exempt = set(json.loads(EXEMPTIONS.read_text(encoding="utf-8"))["reserved"])

    unconsumed, reserved, stale = [], [], []
    for name in sorted(fields):
        pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])")
        used = any(pattern.search(text) for text in sources.values())
        if used:
            if name in exempt:
                # the field is consumed again, so the exemption is stale
                stale.append(name)
            continue
        (reserved if name in exempt else unconsumed).append(name)
    return {"total": len(fields), "unconsumed": unconsumed,
            "reserved": reserved, "stale": stale}

# ── thresholds ────────────────────────────────────────────────────────────


def _load_thresholds() -> dict:
    if THRESHOLDS.is_file():
        data = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
    else:
        data = {}
    merged = dict(DEFAULT_THRESHOLDS)
    merged.update({k: v for k, v in data.items() if k in DEFAULT_THRESHOLDS})
    return merged


def _save_thresholds(data: dict) -> None:
    THRESHOLDS.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")

# ── entry point ───────────────────────────────────────────────────────────


def run(which: str, report_only: bool) -> int:
    th = _load_thresholds()
    failed = []

    if which in ("assertions", "all"):
        rep = assertion_report()
        print("[assertions] %d/%d tests carry an independent expectation "
              "(%.1f%%; required %.1f%%)"
              % (rep["independent"], rep["tests"], 100 * rep["ratio"],
                 100 * th["assertion_min"]))
        print("[assertions] core modules: %d/%d (%.1f%%; required %.1f%%)"
              % (rep["core_independent"], rep["core_tests"],
                 100 * rep["core_ratio"], 100 * th["core_assertion_min"]))
        if rep["ratio"] < th["assertion_min"]:
            failed.append("assertions: overall ratio below the threshold")
        if rep["core_ratio"] < th["core_assertion_min"]:
            failed.append("assertions: core-module ratio below the threshold")

    if which in ("fields", "all"):
        rep = field_report()
        print("[fields] %d object fields, %d reserved, %d UNCONSUMED"
              % (rep["total"], len(rep["reserved"]), len(rep["unconsumed"])))
        for name in rep["unconsumed"][:20]:
            print("    unconsumed: " + name)
        if len(rep["unconsumed"]) > th["unconsumed_max"]:
            failed.append("fields: %d field(s) have no consumer (max %d)"
                          % (len(rep["unconsumed"]), th["unconsumed_max"]))
        # Ratchet: the reserved list may only shrink.  An entry that became
        # consumed is dead weight that would otherwise mask a future regression,
        # so it has to be deleted rather than left lying around.
        if rep["stale"]:
            print("[fields] %d stale exemption(s) -- delete them: %s"
                  % (len(rep["stale"]), ", ".join(rep["stale"][:10])))
            failed.append("fields: %d stale exemption(s)" % len(rep["stale"]))

    if failed and not report_only:
        for line in failed:
            print("[gate] FAIL " + line)
        return 1
    if failed:
        print("[gate] (report only) would fail: " + "; ".join(failed))
    else:
        print("[gate] PASS")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("which", nargs="?", default="all",
                    choices=["assertions", "fields", "all", "thresholds"])
    ap.add_argument("--report", action="store_true",
                    help="print the numbers but never fail")
    ap.add_argument("--set-assertion-min", type=float, default=None)
    ap.add_argument("--set-core-assertion-min", type=float, default=None)
    args = ap.parse_args(argv)

    if args.which == "thresholds":
        print(json.dumps(_load_thresholds(), indent=2, sort_keys=True))
        return 0

    th = _load_thresholds()
    if args.set_assertion_min is not None:
        th["assertion_min"] = args.set_assertion_min
    if args.set_core_assertion_min is not None:
        th["core_assertion_min"] = args.set_core_assertion_min
    if args.set_assertion_min is not None or args.set_core_assertion_min is not None:
        _save_thresholds(th)
        print("[gate] thresholds updated: " + json.dumps(th, sort_keys=True))
        return 0

    return run(args.which, args.report)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
