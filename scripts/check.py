#!/usr/bin/env python3
"""flowviewer quality gate (R24).

One-click CI/local gate: static analysis + type check + full test suite +
perf thresholds.  Each stage fails fast (non-zero exit) with a clear
label so a red CI points straight at the failing stage.

Stages:
  1. lint   ruff check fv/ tests/
  2. types  mypy on the progressively-typed core modules
            (fv/model/varreg.py fv/model/derived.py fv/model/report.py)
  3. test   pytest (full suite)
  4. bench  python scripts/benchmark.py --check

Usage:
    python scripts/check.py            # all stages
    python scripts/check.py lint       # single stage
    python scripts/check.py --skip=bench  # skip one stage
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# progressively-typed modules must be kept as a strict-typed allow-set
# (see [tool.mypy] follow_imports = "skip"); extend as typing coverage grows.
_TYPED_MODULES = [
    "fv/model/varreg.py",
    "fv/model/derived.py",
    "fv/model/report.py",
]


def _run(label, *cmd, cwd=ROOT):
    print("\n==> [%s] %s" % (label, " ".join(cmd)))
    p = subprocess.run([str(c) for c in cmd], cwd=str(cwd))
    if p.returncode != 0:
        print("==> FAILED: %s" % label)
    return p.returncode


def _stages(only, skip):
    all_stages = {
        "lint": lambda: _run("lint", sys.executable, "-m", "ruff", "check",
                             "fv/", "tests/"),
        "types": lambda: _run(
            "types", sys.executable, "-m", "mypy",
            *map(lambda m: str(ROOT / m), _TYPED_MODULES)),
        "test": lambda: _run("test", sys.executable, "-m", "pytest",
                             "tests", "-q"),
        "bench": lambda: _run("bench", sys.executable,
                              "scripts/benchmark.py", "--check"),
    }
    if only:
        return {k: v for k, v in all_stages.items() if k in only}
    return {k: v for k, v in all_stages.items() if k not in skip}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    only = [a for a in argv if not a.startswith("--")]
    skip = set()
    for a in argv:
        if a.startswith("--skip="):
            skip.update(x.strip() for x in a.split("=", 1)[1].split(","))
    bad = (set(only) | skip) - set(["lint", "types", "test", "bench"])
    if bad:
        print("unknown stage(s): %s" % sorted(bad))
        return 2
    stages = _stages(only, skip)
    print("flowviewer quality gate: %s" % ", ".join(stages))
    ok = True
    for label, fn in stages.items():
        if fn() != 0:
            ok = False
            break
    print("\n==> GATE %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))