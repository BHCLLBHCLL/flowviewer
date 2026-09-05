"""R74 tests: headless report CLI (``fv.report``).

Exposes the R64-R73 batch / bundle / project machinery at a terminal: read a
``verts``+``artifact`` JSON and emit HTML reports to a directory, optionally
with an ``index.html`` and a shareable zip. These tests keep report generation
out of scope by monkeypatching ``run_report_bundle`` / ``run_project`` /
``export_report_bundle``; they exercise only the input parsing, kind selection,
project dispatch, manifest building and exit codes. Pure stdlib, headless.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv import report as report_cli


def _artifact(name="trace") -> dict:
    return {"name": name, "cycles": [0, 1, 2],
            "probes": [{"query": [0, 0, 0], "node": 0, "xyz": [0, 0, 0],
                        "values": [1.0, 2.0, 3.0]}]}


def _write_input(tmp_path) -> str:
    p = tmp_path / "in.json"
    p.write_text(json.dumps({"verts": [[0, 0, 0], [1, 1, 1]],
                             "artifact": _artifact()}), encoding="utf-8")
    return str(p)


def test_as_verts_none_is_empty():
    v = report_cli._as_verts(None)
    assert v.shape == (0, 3)


def test_as_verts_flat_list_reshapes():
    v = report_cli._as_verts([1, 2, 3, 4, 5, 6])
    assert v.shape == (2, 3)
    assert v.tolist() == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]


def test_as_verts_2d_trims_extra_columns():
    v = report_cli._as_verts([[1, 2, 3, 4], [5, 6, 7, 8]])
    assert v.shape == (2, 3)
    assert v.tolist() == [[1.0, 2.0, 3.0], [5.0, 6.0, 7.0]]


def test_as_verts_empty_list_is_empty():
    assert report_cli._as_verts([]).shape == (0, 3)


def test_as_verts_invalid_raises():
    with pytest.raises(ValueError):
        report_cli._as_verts([[1, 2]])


def test_load_input_verts_and_artifact(tmp_path):
    p = tmp_path / "in.json"
    p.write_text(json.dumps({"verts": [[0, 0, 0], [1, 1, 1]],
                             "artifact": _artifact()}), encoding="utf-8")
    verts, artifact = report_cli.load_input(str(p))
    assert verts.shape == (2, 3)
    assert artifact["name"] == "trace"
    assert len(artifact["probes"]) == 1


def test_load_input_artifact_only_defaults_verts(tmp_path):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(_artifact()), encoding="utf-8")
    verts, artifact = report_cli.load_input(str(p))
    assert verts.shape == (0, 3)
    assert artifact["name"] == "trace"


def test_load_input_missing_file_raises(tmp_path):
    with pytest.raises(ValueError):
        report_cli.load_input(str(tmp_path / "nope.json"))


def test_load_input_bad_json_raises(tmp_path):
    p = tmp_path / "in.json"
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError):
        report_cli.load_input(str(p))


def test_load_input_non_object_raises(tmp_path):
    p = tmp_path / "in.json"
    p.write_text(json.dumps([1, 2]), encoding="utf-8")
    with pytest.raises(ValueError):
        report_cli.load_input(str(p))


def test_gui_export_payload_roundtrips(tmp_path):
    """The GUI ``Export Analysis Data Source`` payload round-trips via load_input.

    ``prepare_verts`` returns an ``(N, 3)`` float array; the GUI export writes
    ``{"verts": verts.tolist(), "artifact": ...}`` so the headless CLI can re-run
    the same workload from ``python -m fv.report <path>``.
    """
    verts = np.asarray([[i, j, 0.0] for i in range(3) for j in range(3)],
                       dtype=np.float64)
    artifact = _artifact("grid")
    p = tmp_path / "export.json"
    p.write_text(json.dumps({"verts": verts.tolist(), "artifact": artifact}),
                 encoding="utf-8")
    got_verts, got_artifact = report_cli.load_input(str(p))
    assert got_verts.tolist() == verts.tolist()
    assert got_artifact == artifact


def test_load_params_absent_is_empty():
    assert report_cli.load_params(None) == {}
    assert report_cli.load_params("") == {}


def test_load_params_returns_dict(tmp_path):
    p = tmp_path / "params.json"
    p.write_text(json.dumps({"spectral": {"frames": 3}}), encoding="utf-8")
    assert report_cli.load_params(str(p)) == {"spectral": {"frames": 3}}


def test_load_params_missing_file_raises(tmp_path):
    with pytest.raises(ValueError):
        report_cli.load_params(str(tmp_path / "nope.json"))


def test_load_params_non_object_raises(tmp_path):
    p = tmp_path / "params.json"
    p.write_text(json.dumps([1]), encoding="utf-8")
    with pytest.raises(ValueError):
        report_cli.load_params(str(p))


def test_run_bundle_builds_manifest(monkeypatch, tmp_path):
    out_dir = tmp_path / "reports"
    paths = {"spectral": str(out_dir / "spectral.html"),
             "coherence": str(out_dir / "coherence.html")}
    monkeypatch.setattr(report_cli, "run_report_bundle",
                        lambda v, a, o, **kw: dict(paths))
    manifest = report_cli.run({"input": _write_input(tmp_path),
                               "out_dir": str(out_dir)})
    assert manifest["reports"] == {"spectral": "spectral.html",
                                   "coherence": "coherence.html"}
    assert manifest["index"] == "index.html"
    assert manifest["zip"] is None
    assert manifest["count"] == 2
    assert out_dir.is_dir()


def test_run_bundle_forwards_kinds_params_dt(monkeypatch, tmp_path):
    out_dir = tmp_path / "reports"
    seen = {}

    def fake(v, a, o, **kw):
        seen.update(kw)
        return {"spectral": str(out_dir / "spectral.html")}

    monkeypatch.setattr(report_cli, "run_report_bundle", fake)
    report_cli.run({"input": _write_input(tmp_path),
                    "out_dir": str(out_dir),
                    "kinds": ["spectral"], "params": {"spectral": {"frames": 2}},
                    "dt": 0.5})
    assert seen["kinds"] == ["spectral"]
    assert seen["params"] == {"spectral": {"frames": 2}}
    assert seen["dt"] == 0.5


def test_run_no_reports_has_no_index(monkeypatch, tmp_path):
    monkeypatch.setattr(report_cli, "run_report_bundle",
                        lambda v, a, o, **kw: {})
    manifest = report_cli.run({"input": _write_input(tmp_path),
                               "out_dir": str(tmp_path / "reports")})
    assert manifest["reports"] == {}
    assert manifest["index"] is None
    assert manifest["count"] == 0


def test_run_project_dispatches(monkeypatch, tmp_path):
    out_dir = tmp_path / "reports"
    paths = {"spectral": str(out_dir / "spectral.html")}
    seen = {}

    def fake_project(store, name, verts, artifact, out_dir, *, dt=None):
        seen["name"] = name
        seen["out_dir"] = out_dir
        seen["dt"] = dt
        return dict(paths)

    monkeypatch.setattr(report_cli, "run_project", fake_project)
    manifest = report_cli.run({"input": _write_input(tmp_path),
                               "out_dir": str(out_dir),
                               "project": "my batch", "dt": 0.25})
    assert seen["name"] == "my batch"
    assert seen["dt"] == 0.25
    assert manifest["reports"] == {"spectral": "spectral.html"}
    assert manifest["index"] == "index.html"


def test_run_unknown_project_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(report_cli, "run_project",
                        lambda store, name, v, a, o, *, dt=None: None)
    with pytest.raises(ValueError):
        report_cli.run({"input": _write_input(tmp_path),
                        "out_dir": str(tmp_path / "reports"),
                        "project": "missing"})


def test_run_zip_exported(monkeypatch, tmp_path):
    out_dir = tmp_path / "reports"
    zip_path = tmp_path / "bundle.zip"
    paths = {"spectral": str(out_dir / "spectral.html")}
    monkeypatch.setattr(report_cli, "run_report_bundle",
                        lambda v, a, o, **kw: dict(paths))
    monkeypatch.setattr(report_cli, "export_report_bundle",
                        lambda paths, zp, **kw: zip_path)
    manifest = report_cli.run({"input": _write_input(tmp_path),
                               "out_dir": str(out_dir),
                               "zip": str(zip_path)})
    assert manifest["zip"] == "../bundle.zip"


def test_main_success_exit_zero(monkeypatch, tmp_path, capsys):
    manifest = {"out_dir": str(tmp_path), "reports": {}, "index": None,
                "zip": None, "count": 0}
    monkeypatch.setattr(report_cli, "run", lambda config: dict(manifest))
    rc = report_cli.main([_write_input(tmp_path), "-o", str(tmp_path)])
    out = capsys.readouterr()
    assert rc == 0
    assert json.loads(out.out) == manifest


def test_main_bad_input_exit_one(tmp_path, capsys):
    rc = report_cli.main([str(tmp_path / "missing.json")])
    out = capsys.readouterr()
    assert rc == 1
    assert "fv.report:" in out.err
