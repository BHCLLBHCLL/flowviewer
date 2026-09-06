"""R82 - headless HTTP service for report-family bundles (section 8.77).

R64-R81 produce a bundle directory of self-contained single-file HTML reports
plus an ``index.html``. R32's server serves only the streaming CGNS surface;
``fv/web/report_server.py`` mounts a bundle on a stdlib ThreadingHTTPServer so
it can be browsed / shared / downloaded without a GUI. Zero third-party deps.
"""

import io
import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest  # noqa: E402

pytest.importorskip("h5py")

from fv.web.report_server import (  # noqa: E402
    bundle_listings,
    bundle_title,
    serve_bundle,
)

# ── fixtures / helpers ─────────────────────────────────────────────────────


def _write_report(dirpath: Path, name: str, body: str) -> Path:
    out = dirpath / name
    out.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{name}</title></head><body>{body}</body></html>\n",
        encoding="utf-8")
    return out


def _make_bundle(dirpath: Path, *, with_index: bool = True) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    _write_report(dirpath, "spectral_report.html", "<h1>spectral</h1>")
    _write_report(dirpath, "coherence_report.html", "<h1>coherence</h1>")
    if with_index:
        (dirpath / "index.html").write_text(
            "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
            "<title>my analysis bundle</title></head><body>"
            "<h1>my analysis bundle</h1><p>2 report(s) generated.</p>"
            "<ul><li><a href=\"spectral_report.html\">Spectral analysis</a></li>"
            "<li><a href=\"coherence_report.html\">Coherence analysis</a></li>"
            "</ul></body></html>\n", encoding="utf-8")
    return dirpath


def _http(method, port, path, body=None, headers=None):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, data=body, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:  # non-2xx is still a response
        return exc.code, exc.headers, exc.read()


def _shutdown(server, thread):
    try:
        server.shutdown()
    except Exception:  # pragma: no cover
        pass
    try:
        server.server_close()
    except Exception:  # pragma: no cover
        pass
    if thread and thread.is_alive():
        thread.join(timeout=2.0)


# ── listing / title helpers ────────────────────────────────────────────────


def test_bundle_listings_parse_index(tmp_path):
    """bundle_listings reads href+label from a report_index_html-style index."""
    bundle = _make_bundle(tmp_path / "b")
    listings = bundle_listings(bundle)
    assert [item["name"] for item in listings] == [
        "spectral_report.html", "coherence_report.html"]
    assert listings[0]["label"] == "Spectral analysis"
    assert listings[1]["label"] == "Coherence analysis"


def test_bundle_listings_falls_back_to_scan(tmp_path):
    """Without an index.html, listings fall back to a sorted *.html scan."""
    bundle = _make_bundle(tmp_path / "b", with_index=False)
    listings = bundle_listings(bundle)
    assert [item["name"] for item in listings] == [
        "coherence_report.html", "spectral_report.html"]
    assert listings[0]["label"] == "coherence_report"  # stem fallback


def test_bundle_title(tmp_path):
    bundle = _make_bundle(tmp_path / "b")
    assert bundle_title(bundle / "index.html") == "my analysis bundle"
    assert bundle_title(None) == "flowviewer analysis bundle"


# ── HTTP service ───────────────────────────────────────────────────────────


def test_serve_bundle_index_page(tmp_path):
    """GET / and /index.html both return the bundle index page."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        for path in ("/", "/index.html"):
            status, headers, data = _http("GET", server.port, path)
            assert status == 200
            assert headers.get("Content-Type", "").startswith("text/html")
            text = data.decode("utf-8")
            assert "Spectral analysis" in text and "Coherence analysis" in text
    finally:
        _shutdown(server, thread)


def test_serve_bundle_list(tmp_path):
    """/api/list returns the JSON report listing with browse labels."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, _, data = _http("GET", server.port, "/api/list")
        assert status == 200
        body = json.loads(data)
        assert body["ok"] is True
        assert body["title"] == "my analysis bundle"
        names = [item["name"] for item in body["reports"]]
        assert names == ["spectral_report.html", "coherence_report.html"]
    finally:
        _shutdown(server, thread)


def test_serve_bundle_report_file(tmp_path):
    """A single report is served by basename with text/html."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, headers, data = _http("GET", server.port,
                                      "/spectral_report.html")
        assert status == 200
        assert headers.get("Content-Type", "").startswith("text/html")
        assert b"<h1>spectral</h1>" in data
    finally:
        _shutdown(server, thread)


def test_serve_bundle_404(tmp_path):
    """An unknown path yields a clean JSON 404."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, _, data = _http("GET", server.port, "/nope.html")
        assert status == 404
        assert json.loads(data)["ok"] is False
    finally:
        _shutdown(server, thread)


def test_serve_bundle_traversal_blocked(tmp_path):
    """A path escaping the bundle dir is refused (403)."""
    bundle = _make_bundle(tmp_path / "b")
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, _, data = _http("GET", server.port, "/..%2Fsecret.txt")
        assert status == 403
        assert json.loads(data)["ok"] is False
    finally:
        _shutdown(server, thread)


def test_serve_bundle_zip_download(tmp_path):
    """/api/bundle.zip streams an archive containing index.html + reports."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, headers, data = _http("GET", server.port, "/api/bundle.zip")
        assert status == 200
        assert headers.get("Content-Type", "").startswith("application/zip")
        assert "attachment" in headers.get("Content-Disposition", "")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            assert "index.html" in names
            assert "spectral_report.html" in names
            assert "coherence_report.html" in names
    finally:
        _shutdown(server, thread)


def test_serve_bundle_fallback_index(tmp_path):
    """A bundle without index.html gets a generated index at /."""
    bundle = _make_bundle(tmp_path / "b", with_index=False)
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, _, data = _http("GET", server.port, "/")
        assert status == 200
        text = data.decode("utf-8")
        assert "coherence_report.html" in text
        assert "spectral_report.html" in text
        status, _, _ = _http("GET", server.port, "/api/list")
        assert status == 200
    finally:
        _shutdown(server, thread)


def test_serve_bundle_rejects_non_dir(tmp_path):
    """serve_bundle raises ValueError for a missing / non-directory path."""
    with pytest.raises(ValueError):
        serve_bundle(str(tmp_path / "missing"))


def test_serve_bundle_zip_empty_is_404(tmp_path):
    """/api/bundle.zip on an empty dir degrades to a clean 404."""
    empty = tmp_path / "empty"
    empty.mkdir(exist_ok=True)
    server, thread = serve_bundle(empty, port=0, in_thread=True)
    try:
        status, _, data = _http("GET", server.port, "/api/bundle.zip")
        assert status == 404
        assert json.loads(data)["ok"] is False
    finally:
        _shutdown(server, thread)
