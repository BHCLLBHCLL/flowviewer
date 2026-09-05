"""R72 tests: Batch report-bundle packaging (export/import .zip + reopen).

R71 lets the user run every Analysis report kind at once into a scratch folder
with an ``index.html`` linking each result, but the batch lives in a temp dir
that is overwritten on the next run and cannot be archived, shared or reopened.
R72 adds ``export_report_bundle``/``open_report_bundle`` in ``fv.gui.analysis``
so a batch can be packed into a single ``.zip`` and reopened later.

These tests exercise only the pure zip/HTML logic; report generation is out of
scope (fake single-file HTML is used). Pure stdlib/pathlib, headless.
"""

from __future__ import annotations

import zipfile

from fv.gui import analysis


def _html(name: str) -> str:
    return f"<!doctype html><html><body>{name}</body></html>\n"


def test_report_index_html_basename_links(tmp_path):
    paths = {"spectral": str(tmp_path / "spectral.html"),
             "spatial_pod": str(tmp_path / "pod.html")}
    doc = analysis.report_index_html(paths)
    assert "Spectral Field Map (R58)" in doc
    assert "Spatial POD Report (R54)" in doc
    assert 'href="spectral.html"' in doc
    assert 'href="pod.html"' in doc
    assert "2 report(s) generated." in doc


def test_report_index_html_escapes_html(tmp_path):
    doc = analysis.report_index_html(
        {"spectral": str(tmp_path / "a<&>.html")}, title='X "y" & <z>')
    assert "&lt;z&gt;" in doc
    assert "&amp;" in doc
    assert 'href="a&lt;&amp;&gt;.html"' in doc


def test_write_report_index_uses_index_html(tmp_path):
    paths = {"spectral": str(tmp_path / "spectral.html")}
    index = analysis.write_report_index(paths, str(tmp_path))
    assert index == tmp_path / "index.html"
    assert "Spectral Field Map (R58)" in index.read_text(encoding="utf-8")


def test_export_report_bundle_empty_paths_returns_none(tmp_path):
    assert analysis.export_report_bundle({}, str(tmp_path / "b.zip")) is None


def test_export_report_bundle_all_missing_returns_none(tmp_path):
    paths = {"spectral": str(tmp_path / "nope.html")}
    assert analysis.export_report_bundle(paths, str(tmp_path / "b.zip")) is None


def test_export_report_bundle_zips_reports_and_index(tmp_path):
    (tmp_path / "spectral.html").write_text(_html("sig"), encoding="utf-8")
    (tmp_path / "pod.html").write_text(_html("pod"), encoding="utf-8")
    zip_path = tmp_path / "bundle.zip"
    out = analysis.export_report_bundle(
        {"spectral": str(tmp_path / "spectral.html"),
         "spatial_pod": str(tmp_path / "pod.html")}, str(zip_path))
    assert out == zip_path
    names = zipfile.ZipFile(zip_path).namelist()
    assert "index.html" in names
    assert "spectral.html" in names
    assert "pod.html" in names
    with zipfile.ZipFile(zip_path) as zf:
        assert "Spectral Field Map (R58)" in zf.read("index.html").decode("utf-8")


def test_export_report_bundle_skips_missing_files(tmp_path):
    (tmp_path / "spectral.html").write_text(_html("sig"), encoding="utf-8")
    paths = {"spectral": str(tmp_path / "spectral.html"),
             "coherence": str(tmp_path / "gone.html")}
    out = analysis.export_report_bundle(paths, str(tmp_path / "bundle.zip"))
    assert out is not None
    names = zipfile.ZipFile(out).namelist()
    assert "spectral.html" in names
    assert "gone.html" not in names


def test_open_report_bundle_roundtrip_extracts_index_and_reports(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "spectral.html").write_text(_html("sig"), encoding="utf-8")
    (src / "pod.html").write_text(_html("pod"), encoding="utf-8")
    zip_path = tmp_path / "bundle.zip"
    analysis.export_report_bundle(
        {"spectral": str(src / "spectral.html"),
         "spatial_pod": str(src / "pod.html")}, str(zip_path))
    dest = tmp_path / "dest"
    index = analysis.open_report_bundle(str(zip_path), str(dest))
    assert index == dest / "index.html"
    assert index.is_file()
    assert (dest / "spectral.html").is_file()
    assert (dest / "pod.html").is_file()
    text = index.read_text(encoding="utf-8")
    assert 'href="spectral.html"' in text


def test_open_report_bundle_nonexistent_zip_returns_none(tmp_path):
    assert analysis.open_report_bundle(
        str(tmp_path / "missing.zip"), str(tmp_path / "dest")) is None


def test_open_report_bundle_blocks_path_traversal(tmp_path):
    dest = tmp_path / "dest"
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("index.html", _html("ok"))
        zf.writestr("../evil.txt", "pwned")
    index = analysis.open_report_bundle(str(zip_path), str(dest))
    assert index == dest / "index.html"
    assert index.is_file()
    assert not (tmp_path / "evil.txt").exists()
    assert not (dest / "evil.txt").exists()


def test_open_report_bundle_skips_directory_entries(tmp_path):
    dest = tmp_path / "dest"
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("index.html", _html("ok"))
        zf.writestr("sub/", "")
        zf.writestr("sub/note.html", _html("note"))
    index = analysis.open_report_bundle(str(zip_path), str(dest))
    assert index == dest / "index.html"
    assert index.is_file()
    assert (dest / "sub" / "note.html").is_file()


def test_open_report_bundle_no_index_returns_none(tmp_path):
    dest = tmp_path / "dest"
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("only.html", _html("only"))
    assert analysis.open_report_bundle(str(zip_path), str(dest)) is None


def test_open_report_bundle_corrupt_zip_returns_none(tmp_path):
    zip_path = tmp_path / "corrupt.zip"
    zip_path.write_bytes(b"not a real zip")
    assert analysis.open_report_bundle(
        str(zip_path), str(tmp_path / "dest")) is None
