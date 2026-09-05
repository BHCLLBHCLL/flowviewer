"""R62 tests: spatial report folded with the R58/R59/R60 field maps.

Pure NumPy, headless, no CGNS, no VTK. Extends the R54 spatial report with an
opt-in ``--field`` that folds the spectral / coherence / spectral-evolution
previews (stats + binned heatmap grids) onto the same single-page HTML; default
output stays byte-identical to R54.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv.spatialreport import (
    build_spatial_report,
    main,
    render_html,
    write_spatial_report,
)

CY = list(range(0, 120))  # fast 6 s sub-window for the field maps


def _grid3() -> np.ndarray:
    return np.array([[i, j, 0.0] for i in range(3) for j in range(3)],
                    dtype=np.float64)


def _art(name="P"):
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)
    v = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)
    v2 = 1.5 + np.sin(2 * np.pi * 1.0 * t + 0.5)
    flat = np.zeros_like(t)
    return {
        "name": name, "cycles": list(t),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0, "xyz": (0.0, 0.0, 0.0),
             "values": list(v)},
            {"query": (2.0, 0.0, 0.0), "node": 2, "xyz": (2.0, 0.0, 0.0),
             "values": list(v2)},
            {"query": (0.0, 2.0, 0.0), "node": 6, "xyz": (0.0, 2.0, 0.0),
             "values": list(flat)},
        ],
    }


def test_default_stays_r54_compatible():
    rep = build_spatial_report(_grid3(), _art(), cycles=CY)
    assert rep["field_maps"]["enabled"] is False
    assert rep["field_maps"]["spectral"] == {}
    h = render_html(rep)
    assert "<canvas" not in h
    assert "Field maps" not in h


def test_field_true_three_panels_populated():
    rep = build_spatial_report(_grid3(), _art(), cycles=CY, field=True, dt=0.05)
    fm = rep["field_maps"]
    assert fm["enabled"] is True
    for n in ("spectral", "coherence", "spectevol"):
        pane = fm[n]
        assert "stats" in pane and "previews" in pane and "meta" in pane
        assert pane["meta"]["n_frames"] > 2
        assert pane["meta"]["n_vertices"] == 9


def test_field_ref_probe_error_forwarded():
    with pytest.raises(ValueError):
        build_spatial_report(_grid3(), _art(), cycles=CY, field=True,
                             ref_probe=99, dt=0.05)


def test_field_empty_graceful():
    art = {"name": "x", "cycles": [], "probes": []}
    rep = build_spatial_report(_grid3(), art, field=True)
    assert rep["field_maps"]["enabled"] is True
    assert rep["field_maps"]["spectral"] == {}
    h = render_html(rep)
    assert "No probes." in h
    assert "Field maps" not in h


def test_render_html_field_canvases_and_escaping():
    rep = build_spatial_report(_grid3(), _art("<script>alert(1)</script>"),
                               cycles=CY, field=True, dt=0.05)
    h = render_html(rep)
    assert "<h2>Field maps</h2>" in h
    assert h.count("<canvas") == 12                 # 4 maps x 3 panels
    for cid in ("cv_spectral_mean", "cv_coherence_phase",
                "cv_spectevol_drift"):
        assert cid in h
    assert "&lt;script&gt;" in h


def test_write_field_true_files_and_slim(tmp_path):
    write_spatial_report(_grid3(), _art("pres sure"), str(tmp_path / "o"),
                         cycles=CY, field=True, dt=0.05)
    out = tmp_path / "o"
    assert (out / "pres_sure_spatial.html").exists()
    assert (out / "pres_sure_spatial.json").exists()
    payload = json.loads((out / "pres_sure_spatial.json")
                         .read_text(encoding="utf-8"))
    assert "field_maps" in payload
    fm = payload["field_maps"]
    assert fm["enabled"] is True
    assert set(fm) >= {"spectral", "coherence", "spectevol"}
    for n in ("spectral", "coherence", "spectevol"):
        assert "previews" in fm[n] and "stats" in fm[n] and "meta" in fm[n]

    def _no_ndarray(x):
        if isinstance(x, dict):
            for val in x.values():
                _no_ndarray(val)
        elif isinstance(x, list):
            for val in x:
                _no_ndarray(val)
        else:
            assert not isinstance(x, np.ndarray)
    _no_ndarray(payload)

    summ = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summ["field_maps"] is True


def test_write_default_omits_field_maps(tmp_path):
    write_spatial_report(_grid3(), _art(), str(tmp_path / "o2"), cycles=CY)
    payload = json.loads((tmp_path / "o2" / "P_spatial.json")
                         .read_text(encoding="utf-8"))
    assert "field_maps" not in payload


def test_cli_roundtrip_and_errors(tmp_path):
    good_trace = tmp_path / "t.json"
    good_trace.write_text(json.dumps(_art()), encoding="utf-8")
    vpath = tmp_path / "v.npy"
    np.save(vpath, _grid3())

    bad = tmp_path / "noprobe.json"
    bad.write_text(json.dumps({"name": "x", "cycles": [0, 1]}), encoding="utf-8")
    assert main([str(bad), str(vpath)]) == 2

    bv = tmp_path / "badv.json"
    bv.write_text(json.dumps([[1.0, 2.0]]), encoding="utf-8")
    assert main([str(good_trace), str(bv)]) == 2

    assert main([str(good_trace), str(vpath), "--cycles", "500:600"]) == 2
    assert main([str(good_trace), str(vpath), "--field", "--ref", "99",
                 "--cycles", "0:80", "--dt", "0.05"]) == 2

    rc = main([str(good_trace), str(vpath), "--field", "--cycles", "0:80",
               "--dt", "0.05", "--out", str(tmp_path / "ok")])
    assert rc == 0
    assert (tmp_path / "ok" / "P_spatial.html").exists()
    summ = json.loads((tmp_path / "ok" / "summary.json")
                      .read_text(encoding="utf-8"))
    assert summ["field_maps"] is True
