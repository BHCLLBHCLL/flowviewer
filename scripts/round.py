#!/usr/bin/env python3
"""flowviewer round gate + auto-push (R110).

Every R-round in `analysis/improvement_plan_r110_r132.md` ends the same way:
verify the change actually holds, then commit and push to `origin/main`.
This script fixes that sequence so a round cannot be closed by hand-waving.

Tiers
-----
fast  (default) ruff + mypy + pytest minus the slow GUI module.
      This is the per-round gate; it must be green before anything is pushed.
full  pytest over the whole suite (the current suite is ~17 minutes, so it is
      a pre-release gate rather than a per-round one).
gold  placeholder for the R116 assertion-density / field-consumption gates.

Usage
-----
    python scripts/round.py --check                    # fast gate only
    python scripts/round.py --check --full             # fast + full suite
    python scripts/round.py --commit "R110: ..." --push
    python scripts/round.py --commit "R111: ..." --push --full

Rules enforced here (see the plan, section 2):
  * never commit unless the fast gate is green;
  * never commit with an empty or non-"R<num>:" subject;
  * never commit while tracked files are unstaged in a way that mixes rounds
    (everything under the repo is staged with `git add -A`);
  * `--push` always targets `origin main` and then re-reads the branch status,
    so an "ahead" state is reported instead of silently left behind.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: pytest module(s) excluded from the fast tier because they dominate runtime.
_SLOW_TEST_TARGETS = ["--ignore=tests/test_gui.py"]

_TYPED_MODULES = [
    "fv/model/varreg.py",
    "fv/model/derived.py",
    "fv/model/report.py",
]

#: subjects look like "R110: fix(plane): ..." — a round number is mandatory.
#: Sub-rounds carry a letter suffix (R113b), so allow one.
_SUBJECT_RE = re.compile(r"^R\d+[a-z]?\b.*\S")


def _run(label, *cmd, capture=False):
    print("\n==> [%s] %s" % (label, " ".join(str(c) for c in cmd)))
    p = subprocess.run(
        [str(c) for c in cmd], cwd=str(ROOT),
        capture_output=capture, text=True)
    if capture:
        out = (p.stdout or "") + (p.stderr or "")
        tail = "\n".join(out.strip().splitlines()[-12:])
        if tail:
            print(tail)
    if p.returncode != 0:
        print("==> FAILED: %s" % label)
    return p.returncode


def gate_fast():
    """ruff + mypy + the test suite minus the slow GUI module."""
    steps = [
        ("lint", (sys.executable, "-m", "ruff", "check", "fv/", "tests/",
                  "scripts/")),
        ("types", (sys.executable, "-m", "mypy",
                   *[str(ROOT / m) for m in _TYPED_MODULES])),
        ("test-fast", (sys.executable, "-m", "pytest", "tests", "-q",
                       * _SLOW_TEST_TARGETS)),
    ]
    for label, cmd in steps:
        if _run(label, *cmd) != 0:
            return False
    return True


def gate_full():
    """The whole suite — pre-release gate, not a per-round one."""
    return _run("test-full", sys.executable, "-m", "pytest", "tests", "-q") == 0


def _git(*args, capture=True):
    p = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=capture,
                       text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _branch_status():
    _, out = _git("status", "-sb")
    return out.strip().splitlines()[0] if out.strip() else "?"


def _has_changes():
    code, out = _git("status", "--porcelain")
    return bool(out.strip())


def commit_and_push(subject, push=False, body=None):
    """Stage everything, commit with *subject*, optionally push to origin/main."""
    if not _SUBJECT_RE.match(subject.strip()):
        print('refusing to commit: subject must start with "R<num>: " '
              "(got %r)" % subject)
        return 1
    if not _has_changes():
        print("nothing to commit (working tree clean)")
        return 0

    code, out = _git("rev-parse", "--abbrev-ref", "HEAD")
    branch = out.strip()
    if branch != "main":
        print("refusing to commit on branch %r (rounds land on main)" % branch)
        return 1

    if _run("stage", "git", "add", "-A") != 0:
        return 1
    if _run("commit", "git", "commit", "-m", subject,
            *(["-m", body] if body else [])) != 0:
        return 1
    print("\n==> committed on main: %s" % subject)

    if not push:
        print("==> not pushed (pass --push to publish)")
        return 0
    if _run("push", "git", "push", "origin", "main") != 0:
        return 1
    print("==> branch status: %s" % _branch_status())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="run the fast gate (default when no action is given)")
    ap.add_argument("--full", action="store_true",
                    help="also run the full test suite")
    ap.add_argument("--commit", metavar="SUBJECT",
                    help='commit subject, e.g. "R110: fix(plane): ..."')
    ap.add_argument("--body", metavar="TEXT",
                    help="optional commit body (evidence, regression numbers)")
    ap.add_argument("--push", action="store_true",
                    help="push the commit to origin/main")
    args = ap.parse_args(argv)

    if not (args.check or args.commit):
        args.check = True

    print("flowviewer round gate :: branch %s" % _branch_status())
    if args.check or args.commit:
        if not gate_fast():
            print("\n==> ROUND GATE FAIL (fast)")
            return 1
        if args.full and not gate_full():
            print("\n==> ROUND GATE FAIL (full)")
            return 1
        print("\n==> ROUND GATE PASS")

    if args.commit:
        return commit_and_push(args.commit, push=args.push, body=args.body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
