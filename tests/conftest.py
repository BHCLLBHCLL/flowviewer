"""Sandbox-compatible pytest fixtures.

pytest's built-in tmp_path/tmp_path_factory create directories with
mode=0o700 (see _pytest/tmpdir.py). Python applies that POSIX mode to the
directory ACL on Windows, and the DSH file sandbox cannot access such
directories (PermissionError WinError 5 on listdir/write). We override both
fixtures to create temp dirs with default permissions (0o777 on POSIX,
inherited ACL on Windows), rooted inside tests/ so the suite also works in
sandboxes that deny writes to the system TEMP area.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_TMP_ROOT = Path(__file__).resolve().parent / "pytest_tmp"


@pytest.fixture(scope="session")
def tmp_path_factory():
    """Sandbox-safe replacement for the built-in tmp_path_factory."""

    class _TmpPathFactory:
        def __init__(self) -> None:
            self._basetemp = _TMP_ROOT
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
            p = self.getbasetemp() / name
            p.mkdir(parents=True, exist_ok=True)
            return p

    return _TmpPathFactory()


@pytest.fixture()
def tmp_path(tmp_path_factory, request) -> Path:
    """Per-test temp dir with default (sandbox-accessible) permissions."""
    return tmp_path_factory.mktemp(request.node.name)
