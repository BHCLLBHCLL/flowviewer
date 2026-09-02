"""R32 - web presentation + collaboration automation (section 9.12).

S1: headless HTTP data service (`fv/web/server.py`) - info / open / windowed
fields (raw float64 or JSON) / render over the R31 streaming handle. S2:
self-contained interactive HTML report (`fv/web/report.py`). S3:
`AutomationSession` (`fv/automation.py`) unified open/query/render/report/serve.
All data paths are headless-safe; render honestly degrades to 503 when no
display is available. Non-stream defaults stay byte-for-byte unchanged (R31).
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("h5py")

from fv.model.dataset import open_stream_cgns  # noqa: E402

# reuse the R28 synthetic two-zone CGNS builder
from test_r28_lazy import _make_two_zone  # noqa: E402,F401


@pytest.fixture
def two_zone(tmp_path):
    path = str(tmp_path / "r32.cgns")
    _make_two_zone(path)
    return path


# ── tiny HTTP client helpers (stdlib only) ────────────────────────────────


def _http(method, port, path, body=None, headers=None):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, data=body, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:  # non-2xx is still a response
        return exc.code, exc.headers, exc.read()


def _open_session(two_zone):
    return open_stream_cgns(two_zone, budget_bytes=1 << 22)


# ── S1: HTTP data service ─────────────────────────────────────────────────


def test_api_info(two_zone):
    from fv.web.server import serve_session
    handle, _ = _open_session(two_zone)
    server, thread = serve_session(handle, port=0, in_thread=True)
    try:
        status, headers, data = _http("GET", server.port, "/api/info")
        assert status == 200
        body = json.loads(data)
        assert body["ok"] is True and "caps" in body
        assert "render" in body["caps"] and "fields" in body["caps"]
    finally:
        _shutdown(server, thread)


def test_api_fields_window_matches_handle(two_zone):
    """/api/fields raw float64 bytes equal StreamCgnsHandle.read_window."""
    from fv.web.server import serve_session
    handle, _ = _open_session(two_zone)
    server, thread = serve_session(handle, port=0, in_thread=True)
    try:
        name = sorted(handle.field_names())[0]
        total = int(handle.field_len(name))
        lo, ref = handle.read_window(name, 0, min(total, 9))
        status, headers, data = _http(
            "GET", server.port,
            f"/api/fields/{urllib.parse.quote(name)}?lo={lo}&hi={min(total, 9)}")
        assert status == 200
        assert int(headers["X-Total"]) == total
        got = np.frombuffer(data, dtype=np.float64)
        assert got.shape == ref.shape
        assert np.allclose(got, ref, equal_nan=True)
    finally:
        _shutdown(server, thread)


def test_api_fields_json(two_zone):
    from fv.web.server import serve_session
    handle, _ = _open_session(two_zone)
    server, thread = serve_session(handle, port=0, in_thread=True)
    try:
        name = sorted(handle.field_names())[0]
        lo, ref = handle.read_window(name, 0, min(handle.field_len(name), 5))
        status, _, data = _http(
            "GET", server.port,
            f"/api/fields/{urllib.parse.quote(name)}?lo=0&hi=5&fmt=json")
        assert status == 200
        body = json.loads(data)
        assert body["ok"] is True
        assert np.allclose(np.asarray(body["values"]), ref, equal_nan=True)
    finally:
        _shutdown(server, thread)


def test_api_open_endpoint(two_zone):
    """POST /api/open mints a streaming session; fields listed zero-payload."""
    from fv.web.server import WebViewerServer, _Session
    handle_ref, _ = _open_session(two_zone)
    server = WebViewerServer(("127.0.0.1", 0), _Session(1 << 22))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps({"path": two_zone, "budget_mb": 4}).encode()
        status, _, data = _http("POST", server.port, "/api/open", payload,
                                {"Content-Type": "application/json"})
        assert status == 200
        body = json.loads(data)
        assert body["ok"] is True and body["fields"]
        names = {f["name"] for f in body["fields"]}
        assert names == set(handle_ref.field_names())
    finally:
        _shutdown(server, thread)


def test_api_render_degrades_cleanly(two_zone):
    """Render endpoint returns PNG when a display exists, else a clean 503."""
    from fv.web.server import serve_session
    handle, _ = _open_session(two_zone)
    server, thread = serve_session(handle, port=0, in_thread=True)
    try:
        status, headers, data = _http("GET", server.port, "/api/render")
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            assert status == 503            # honest headless degrade
            body = json.loads(data)
            assert body["ok"] is False
        else:
            assert status == 200
            assert headers.get("Content-Type", "").startswith("image/png")
            assert b"\x89PNG" in data[:8]
    finally:
        _shutdown(server, thread)


# ── S2: self-contained HTML report ────────────────────────────────────────


def test_report_baked_embedded_values_match_handle(two_zone, tmp_path):
    from fv.web.report import render_report
    handle, mesh = _open_session(two_zone)
    out = str(tmp_path / "report.html")
    assert render_report(handle, out, embed_window=32, mesh=mesh,
                         source_name=two_zone) is True
    text = Path(out).read_text(encoding="utf-8")
    names = set(handle.field_names())
    assert "<canvas" in text and "report.js" not in text  # single file, no deps
    # parse the embedded metadata blob back and validate it end to end
    marker = "const M = "
    start = text.index(marker) + len(marker)
    end = text.index(";\n", start)
    meta = json.loads(text[start:end])
    assert set(meta["fields"]) == names
    # live=False bakes a sample window matching the handle for every field
    for n in sorted(names):
        stats = meta["fields"][n]
        assert stats["n"] == handle.field_len(n)
        assert stats["min"] <= stats["max"]
        sample = np.asarray(stats["sample"], dtype=np.float64)
        _, ref = handle.read_window(n, 0, min(handle.field_len(n), 32))
        assert np.allclose(sample, ref, equal_nan=True)
    assert meta["n_vertices"] == int(mesh["n_vertices"])


def test_report_headless_bounded_scan(two_zone, tmp_path):
    """min/max scan uses bounded tiles; report is written for any field list."""
    from fv.web.report import render_report
    handle, _ = _open_session(two_zone)
    out = str(tmp_path / "r.html")
    assert render_report(handle, out, mesh=None) is True
    assert Path(out).stat().st_size > 0


# ── S3: AutomationSession ─────────────────────────────────────────────────


def test_automation_session_chain(two_zone, tmp_path):
    """open -> fields -> query -> render -> export_report -> serve all work."""
    from fv.automation import AutomationSession
    report = str(tmp_path / "a.html")
    png = str(tmp_path / "shot.png")
    with AutomationSession(budget_mb=4) as a:
        a.open(two_zone, stream=True)
        names = a.fields()
        assert names
        name = sorted(names)[0]
        lo, data = a.query(name, 0, min(a.handle.field_len(name), 5))
        assert data.shape[0] >= 1
        assert a.export_report(report, live=False) is True
        assert Path(report).stat().st_size > 0
        # render: headless -> False (honest), interactive -> True
        ok = a.render(png)
        assert ok is (os.environ.get("QT_QPA_PLATFORM") != "offscreen")
        # collaboration RPC over localhost
        port = a.serve(port=0)
        status, _, _ = _http("GET", port, "/api/info")
        assert status == 200
    # after close the server/thread are gone
    assert a._server is None


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
