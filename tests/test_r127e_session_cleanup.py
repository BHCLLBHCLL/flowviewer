"""R127e - abandoned pytest_tmp session roots are cleaned automatically.

conftest removes its session root on a normal exit, but a killed run leaves it
behind: 20 roots / 3.3 GB had accumulated by 2026-09-26, and a gate run that
Windows closed mid-flight (AppHangB1, 16 CFD jobs saturating the CPU) added
another 233 MB.  The sweep only touches roots older than 12 hours, so a
concurrent session in the same checkout survives.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import conftest  # noqa: E402


def _make_session(root: Path, name: str, age_hours: float) -> Path:
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "payload.fph").write_text("x" * 16, encoding="utf-8")
    stamp = time.time() - age_hours * 3600
    os.utime(path, (stamp, stamp))
    return path


def test_r127e_only_old_session_roots_are_removed(tmp_path):
    root = tmp_path / "pytest_tmp"
    old = _make_session(root, "session-111-aaaaaaaa", 13.0)
    fresh = _make_session(root, "session-222-bbbbbbbb", 0.1)
    keep = root / "not-a-session"
    keep.mkdir()

    removed = conftest.clean_stale_sessions(root, hours=12)

    assert removed == ["session-111-aaaaaaaa"]
    assert not old.exists()
    assert fresh.is_dir(), "a live session must survive the sweep"
    assert keep.is_dir(), "only session-* directories may be touched"


def test_r127e_missing_root_is_not_an_error(tmp_path):
    assert conftest.clean_stale_sessions(tmp_path / "nope", hours=1) == []


def test_r127e_threshold_is_a_day_scale_guard():
    """The guard has to be far longer than any single session."""
    assert conftest._STALE_SESSION_HOURS >= 6
