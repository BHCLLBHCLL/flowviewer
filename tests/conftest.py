"""Sandbox-compatible pytest fixtures.

pytest's built-in tmp_path/tmp_path_factory create directories with
mode=0o700 (see _pytest/tmpdir.py). Python applies that POSIX mode to the
directory ACL on Windows, and the DSH file sandbox cannot access such
directories (PermissionError WinError 5 on listdir/write). We override both
fixtures to create temp dirs with default permissions (0o777 on POSIX,
inherited ACL on Windows), rooted inside tests/ so the suite also works in
sandboxes that deny writes to the system TEMP area.

R110 isolation fix
------------------
The previous implementation named each per-test directory
`{request.node.name}{counter}`, where the counter started at 1 for every
session. A repeated run therefore landed in the *same* directory and saw the
files the previous run had left behind: e.g.
`test_persists_to_file_and_reloads` asserts `not p.exists()` and failed on
the second run, while passing on a clean checkout. That is a harness defect,
not a product one, and it made "the suite is green" unreliable.

Two changes close it:

* every session gets a unique root (`session-<pid>-<uuid4>`) with a
  session-unique counter, so no run can observe another run's leftovers;
* the root is removed again at session exit, so a run leaves no multi-GB
  residue behind (2.4 GB / 14,853 files had accumulated).

`tests/pytest_tmp` is ignored by git (see .gitignore), so cleanup only ever
touches generated data.
"""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

import pytest

_TMP_ROOT = Path(__file__).resolve().parent / "pytest_tmp"


def _fresh_dir(path: Path) -> Path:
    """Create *path* empty (and sandbox-accessible) and return it."""
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def tmp_path_factory():
    """Sandbox-safe replacement for the built-in tmp_path_factory.

    Session-unique root + session-unique numbering so no test can observe a
    previous run's leftovers; the root is deleted when the session ends.
    """
    session_root = _TMP_ROOT / ("session-%d-%s" % (os.getpid(), uuid.uuid4().hex[:8]))

    class _TmpPathFactory:
        def __init__(self) -> None:
            self._basetemp = session_root
            self._count = 0

        def getbasetemp(self) -> Path:
            self._basetemp.mkdir(parents=True, exist_ok=True)
            return self._basetemp

        @property
        def basetemp(self) -> Path:
            return self.getbasetemp()

        def mktemp(self, basename: str, numbered: bool = True) -> Path:
            self._count += 1
            name = f"{basename}{self._count}" if numbered else basename
            # Always unique and always empty: a repeated run must never see a
            # stale file from an earlier run with the same test name.
            return _fresh_dir(self.getbasetemp() / name)

    yield _TmpPathFactory()

    shutil.rmtree(session_root, ignore_errors=True)


@pytest.fixture()
def tmp_path(tmp_path_factory, request) -> Path:
    """Per-test temp dir with default (sandbox-accessible) permissions."""
    return tmp_path_factory.mktemp(request.node.name)

# ── in-repo golden corpus (R114) ──────────────────────────────────────────
#
# The numeric reference assets live under tests/data/golden and are committed,
# so these fixtures resolve on any checkout instead of skipping for want of a
# multi-hundred-megabyte sample.  See scripts/make_golden.py.

_GOLDEN = Path(__file__).resolve().parent / "data" / "golden"


@pytest.fixture(scope="session")
def golden_dir() -> Path:
    if not (_GOLDEN / "meta.json").is_file():
        pytest.skip("golden corpus missing (run scripts/make_golden.py)")
    return _GOLDEN


@pytest.fixture(scope="session")
def fld_golden(golden_dir) -> dict:
    """ex1_100.fld distilled to a committable subset."""
    import numpy as np

    with np.load(golden_dir / "fld_small.npz") as data:
        return {k: data[k] for k in data.files}


@pytest.fixture(scope="session")
def load_cached():
    """Memoised load_file for read-only parsing tests (R127c).

    Several modules parse the same real sample twice: once in a
    load-everything test and once in that sample's own test. The fixture hands
    back the same FieldFile for a given path, so each sample is parsed once per
    session. Tests that MUTATE a FieldFile must keep calling load_file
    themselves -- the cache is shared.
    """
    from fv.model.dataset import load_file

    cache: dict = {}

    def _load(path):
        key = str(path)
        if key not in cache:
            cache[key] = load_file(key)
        return cache[key]

    return _load


@pytest.fixture(scope="session")
def fph_golden(golden_dir) -> dict:
    """tr03_9.fph distilled to a committable subset."""
    import numpy as np

    with np.load(golden_dir / "fph_small.npz") as data:
        return {k: data[k] for k in data.files}
