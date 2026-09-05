"""R63 tests: interactive field maps (hover tooltip / legend / probe overlay).

Pure NumPy, headless, no CGNS, no VTK. The shared ``spectralmap._field_js`` now
drives every field-canvas report (R58/R59/R60 single reports, R61 console, R62
spatial report) with EXTENT (real-space bounds) + PROBES (real probe coords)
injected, plus a colour legend strip and a hover tooltip that maps a canvas
pixel back to the real-space bin centre. This round verifies those.
"""

from __future__ import annotations

import json

import numpy as np
from fv.coherencemap import build_coherence_report
from fv.fieldconsole import build_console
from fv.fieldconsole import render_html as chh
from fv.spatialreport import build_spatial_report
from fv.spectevol import build_spectevol_report
from fv.spectralmap import (
    _field_js,
    _probes_xy,
    build_spectral_report,
    render_html,
)

CY = list(range(0, 120))  # fast 6 s sub-window


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


def _probes_missing_xyz():
    a = _art("Pz")
    a["probes"][1] = {"query": (2.0, 0.0, None), "node": 2,
                      "xyz": (2.0, 0.0, None), "values": a["probes"][1]["values"]}
    return a


def test_reports_carry_extent_and_probes_xy():
    for builder in (build_spectral_report, build_coherence_report,
                    build_spectevol_report, build_console):
        rep = builder(_grid3(), _art(), cycles=CY, dt=0.05)
        assert rep["probes_xy"] == [{"x": 0.0, "y": 0.0},
                                    {"x": 2.0, "y": 0.0},
                                    {"x": 0.0, "y": 2.0}]
        ex = rep["extent"]
        assert (ex["xmin"], ex["xmax"], ex["ymin"], ex["ymax"]) == (0.0, 2.0, 0.0, 2.0)


def test_r58_html_interactive_markers():
    rep = build_spectral_report(_grid3(), _art(), cycles=CY, dt=0.05)
    h = render_html(rep)
    for marker in ("tooltips", "mousemove", "mouseleave", "toExponential",
                   "c.arc(px,py,4,0,7)", "PROBES"):
        assert marker in h, marker
    assert h.count("<canvas") == 4
    # canvas widened to host the legend strip (24*6+32, not 24*6)
    assert 'width="176"' in h and 'width="144"' not in h


def test_console_html_tabs_and_interactive():
    c = build_console(_grid3(), _art(), cycles=CY, dt=0.05)
    h = chh(c)
    assert h.count("<canvas") == 12
    assert "tabs()" in h and "mousemove" in h
    for cid in ("cv_spectral_mean", "cv_coherence_phase", "cv_spectevol_drift"):
        assert cid in h


def test_spatial_report_field_maps_interactive():
    from fv.spatialreport import render_html as shr
    rep = build_spatial_report(_grid3(), _art(), cycles=CY, field=True, dt=0.05)
    assert rep["field_maps"]["enabled"] is True
    assert len(rep["field_maps"]["probes_xy"]) == 3
    html = shr(rep)
    assert "<h2>Field maps</h2>" in html
    assert html.count("<canvas") == 12
    assert "mousemove" in html and "PROBES" in html


def test_probes_missing_xyz_skipped():
    rep = build_spectral_report(_grid3(), _probes_missing_xyz(), cycles=CY, dt=0.05)
    # probes with a usable (x, y) are still exposed for the overlay in real coords
    assert rep["probes_xy"] == [{"x": 0.0, "y": 0.0},
                                {"x": 2.0, "y": 0.0},
                                {"x": 0.0, "y": 2.0}]
    h = render_html(rep)          # z=None must not break build or render
    assert h.count("<canvas") == 4


def test_field_js_produces_panels_js():
    panels = {"": {"names": ["mean"], "maps": {"mean": [[1.0]]},
                   "vm": {"mean": [0.0, 2.0]}}}
    js = _field_js(panels, 4, {"xmin": 0, "xmax": 1, "ymin": 0, "ymax": 1}, [])
    for tok in ("PANELS=", "EXT=", "PROBES=", "LW=32"):
        assert tok in js


def test_probes_xy_helper():
    assert _probes_xy([]) == []
    assert _probes_xy([{"xyz": (1, 2, 3)}, {"query": (4, 5, 6)},
                       {"query": (None, None, None)}]) == [
        {"x": 1.0, "y": 2.0}, {"x": 4.0, "y": 5.0}]
    assert _probes_xy([{"query": (1.0, 2.0)}]) == [{"x": 1.0, "y": 2.0}]


def test_cli_smoke(tmp_path):
    from fv.spectralmap import main
    good = tmp_path / "t.json"
    good.write_text(json.dumps(_art()), encoding="utf-8")
    vp = tmp_path / "v.npy"
    np.save(vp, _grid3())
    rc = main([str(good), str(vp), "--cycles", "0:80", "--dt", "0.05",
               "--out", str(tmp_path / "ok")])
    assert rc == 0
    assert (tmp_path / "ok" / "P_spectral.html").exists()
