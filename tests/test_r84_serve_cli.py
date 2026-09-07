"""R84 tests: headless CLI ``--serve`` (one-shot generate + publish).

R64-R81 give ``fv.report`` the report-family CLI; R82 adds an HTTP bundle server
(``fv.web.report_server``) and R83 puts it on ``AutomationSession`` — but the CLI
``run()`` still had no way to publish the bundle it produced. R84 adds
``--serve`` (plus ``--serve-port`` / ``--serve-host``) so ``python -m fv.report
in.json -o reports --serve`` renders the bundle and then blocks serving it, with
the manifest augmented by a ``serve`` object carrying the bound port and url.

Report generation stays out of scope (real ``run_report_bundle`` / ``run`` are
monkeypatched); the tests exercise ``_serve_info`` against a synthetic bundle and
the ``main`` ``--serve`` wiring with a fake server.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fv import report as report_cli


def _write_report(dirpath: Path, name: str, body: str) -> Path:
    out = dirpath / name
    out.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{name}</title></head><body>{body}</body></html>\n",
        encoding="utf-8")
    return out


def _make_bundle(dirpath: Path) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    _write_report(dirpath, "spectral_report.html", "<h1>spectral</h1>")
    _write_report(dirpath, "coherence_report.html", "<h1>coherence</h1>")
    (dirpath / "index.html").write_text(
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        "<title>my analysis bundle</title></head><body>"
        "<h1>my analysis bundle</h1><p>2 report(s) generated.</p>"
        "<ul><li><a href=\"spectral_report.html\">Spectral analysis</a></li>"
        "<li><a href=\"coherence_report.html\">Coherence analysis</a></li>"
        "</ul></body></html>\n", encoding="utf-8")
    return dirpath


def _http(port, path):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


class _FakeServer:
    """A server stand-in whose serve_forever / server_close are no-ops."""

    port = 8099

    def serve_forever(self):
        return None

    def server_close(self):
        return None


def _start_serving(server):
    """Run ``serve_forever`` in a daemon thread so a live server is testable."""
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


# ── _serve_info ─────────────────────────────────────────────────────────────


def test_serve_info_returns_live_server(tmp_path):
    """_serve_info returns a real HTTP server on the bundle dir."""
    bundle = _make_bundle(tmp_path / "b")
    info, server = report_cli._serve_info(str(bundle))
    _start_serving(server)
    try:
        assert info["bundle"] == str(bundle.resolve())
        assert info["host"] == "127.0.0.1"
        assert info["port"] == server.port
        assert info["url"] == f"http://127.0.0.1:{server.port}/"
        status, _, data = _http(server.port, "/api/list")
        assert status == 200
        body = json.loads(data)
        assert body["title"] == "my analysis bundle"
        assert len(body["reports"]) == 2
    finally:
        server.shutdown()
        server.server_close()


def test_serve_info_honours_host_and_port(tmp_path):
    """--serve-port/--serve-host are reflected in the info dict."""
    bundle = _make_bundle(tmp_path / "b")
    info, server = report_cli._serve_info(str(bundle), port=0,
                                          host="0.0.0.0")
    _start_serving(server)
    try:
        assert info["host"] == "0.0.0.0"
        assert info["port"] == server.port
        assert info["url"].startswith(f"http://0.0.0.0:{server.port}/")
    finally:
        server.shutdown()
        server.server_close()


def test_serve_info_rejects_non_dir(tmp_path):
    """_serve_info on a missing / non-directory path raises ValueError."""
    with pytest.raises(ValueError):
        report_cli._serve_info(str(tmp_path / "missing"))


# ── main --serve wiring ─────────────────────────────────────────────────────


def test_main_serve_augments_manifest(monkeypatch, tmp_path, capsys):
    """main with --serve prints a manifest carrying the serve object."""
    out_dir = str(tmp_path / "reports")
    manifest = {"out_dir": out_dir, "reports": {"spectral": "spectral.html"},
                "index": "index.html", "zip": None, "count": 1}
    info = {"bundle": out_dir, "host": "127.0.0.1", "port": 8099,
            "url": "http://127.0.0.1:8099/"}
    monkeypatch.setattr(report_cli, "run", lambda config: dict(manifest))
    monkeypatch.setattr(report_cli, "_serve_info",
                        lambda out, port=0, host="127.0.0.1": (info,
                                                               _FakeServer()))
    rc = report_cli.main([str(tmp_path / "in.json"), "-o", out_dir, "--serve"])
    out = capsys.readouterr()
    assert rc == 0
    body = json.loads(out.out)
    assert body["serve"] == info
    assert body["count"] == 1


def test_main_serve_bad_bundle_exit_one(monkeypatch, tmp_path, capsys):
    """A serve failure (bad bundle dir) exits 1 and reports to stderr."""
    manifest = {"out_dir": str(tmp_path / "reports"), "reports": {},
                "index": None, "zip": None, "count": 0}
    monkeypatch.setattr(report_cli, "run", lambda config: dict(manifest))

    def bad(out, port=0, host="127.0.0.1"):
        raise ValueError("not a bundle directory")

    monkeypatch.setattr(report_cli, "_serve_info", bad)
    rc = report_cli.main([str(tmp_path / "in.json"), "-o",
                          str(tmp_path / "reports"), "--serve"])
    out = capsys.readouterr()
    assert rc == 1
    assert "fv.report:" in out.err
