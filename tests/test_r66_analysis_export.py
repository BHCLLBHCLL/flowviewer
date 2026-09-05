"""R66 tests: analysis report export helper (copy_report).

R64/R65 let the GUI run the report family; R66 makes the results persist by
allowing a generated report to be exported to a destination directory. The
pure, headless-testable piece is ``fv.gui.analysis.copy_report``, which copies a
self-contained single-file HTML report to ``dest_dir`` (creating it as needed)
and returns the resulting path -- or ``None`` when the source is missing or
unreadable. The Qt layer (``reportview`` Save As button + recent-report combo)
is display-bound and is not exercised here.
"""

from __future__ import annotations

from pathlib import Path

from fv.gui.analysis import copy_report


def _html(tmp_path):
    p = tmp_path / "rep_spectral.html"
    p.write_text(
        "<html><body><canvas>hi</canvas></body></html>", encoding="utf-8")
    return p


def test_copy_report_default_name(tmp_path):
    src = _html(tmp_path)
    out = copy_report(str(src), str(tmp_path / "out"))
    assert out is not None
    assert out.name == src.name
    assert out.exists()
    assert out.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


def test_copy_report_custom_name(tmp_path):
    src = _html(tmp_path)
    out = copy_report(str(src), str(tmp_path / "out"), name="renamed.html")
    assert out.name == "renamed.html"
    assert out.exists()


def test_copy_report_returns_path(tmp_path):
    src = _html(tmp_path)
    out = copy_report(str(src), str(tmp_path / "o"))
    assert isinstance(out, Path)


def test_copy_report_creates_dest_dir(tmp_path):
    src = _html(tmp_path)
    dest = tmp_path / "a" / "b"
    out = copy_report(str(src), str(dest))
    assert out is not None
    assert out.parent.exists()


def test_copy_report_missing_src_returns_none(tmp_path):
    assert copy_report(str(tmp_path / "nope.html"), str(tmp_path / "o")) is None


def test_copy_report_dir_src_returns_none(tmp_path):
    assert copy_report(str(tmp_path), str(tmp_path / "o")) is None
