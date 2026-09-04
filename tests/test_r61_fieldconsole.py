"""R61 tests: unified spectral-field console (Spectral / Coherence / Evolution).

Pure NumPy, headless, no CGNS, no VTK. Folds R58/R59/R60 field reports into one
tabbed self-contained HTML page; reuses those builds' maps/stats/previews.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv.fieldconsole import (
    build_console,
    main,
    render_html,
    write_console,
)

CY = list(range(0, 120))  # fast 6 s sub-window


def _grid3() -> np.ndarray:
    return np.array([[i, j, 0.0] for i in range(3) for j in range(3)],
                    dtype=np.float64)


def _art(name="P"):
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)                       # 400 cycles
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


def test_build_console_default_three_panels():
    c = build_console(_grid3(), _art(), cycles=CY, dt=0.05)
    assert c["kind"] == "fieldconsole"
    assert c["field"] == "P" and c["n_probes"] == 3
    assert c["panel_order"] == ["spectral", "coherence", "spectevol"]
    for name in ("spectral", "coherence", "spectevol"):
        pane = c["panels"][name]
        assert pane["meta"]["n_frames"] > 2
        assert "stats" in pane and "previews" in pane
    # coherence panel metadata carries ref-related/depth info
    assert c["panels"]["coherence"]["meta"]["n_vertices"] == 9


def test_build_console_subset_and_order():
    c = build_console(_grid3(), _art(), panels=("spectral",), cycles=CY, dt=0.05)
    assert c["panel_order"] == ["spectral"]
    assert set(c["panels"]) == {"spectral"}
    c2 = build_console(_grid3(), _art(), panels=("spectevol", "coherence"),
                       cycles=CY, dt=0.05)
    assert c2["panel_order"] == ["spectevol", "coherence"]
    c3 = build_console(_grid3(), _art(), panels=("bogus", "spectral"), cycles=CY, dt=0.05)
    assert c3["panel_order"] == ["spectral"]


def test_build_console_ref_probe_error_forwarded():
    with pytest.raises(ValueError):
        build_console(_grid3(), _art(), ref_probe=99, cycles=CY, dt=0.05)  # coherence hits OOR


def test_build_console_empty_graceful_and_dt_inference():
    art = {"name": "x", "cycles": [], "probes": []}
    c = build_console(_grid3(), art)
    assert c["n_probes"] == 0
    # default dt inferred by the sub-reports matches explicit value
    c2 = build_console(_grid3(), _art())
    assert abs(c2["panels"]["spectral"]["meta"]["dt"] - 0.05) < 1e-9


def test_render_html_tabs_and_canvases_and_escaping():
    c = build_console(_grid3(), _art("<script>alert(1)</script>"), cycles=CY, dt=0.05)
    h = render_html(c)
    for title in ("Spectral (R58)", "Coherence (R59)", "Evolution (R60)"):
        assert title in h
    assert h.count("<canvas") == 12               # 4 maps × 3 panels
    assert "cv_spectral_mean" in h and "cv_coherence_phase" in h
    assert "cv_spectevol_drift" in h
    assert "&lt;script&gt;" in h
    assert "<h2>Summary</h2>" in h


def test_render_html_subset_canvases():
    c = build_console(_grid3(), _art(), panels=("coherence",), cycles=CY, dt=0.05)
    h = render_html(c)
    assert h.count("<canvas") == 4


def test_render_html_empty():
    art = {"name": "x", "cycles": [], "probes": []}
    h = render_html(build_console(_grid3(), art))
    assert "No data." in h


def test_write_console_files_slim_and_summary(tmp_path):
    write_console(_grid3(), _art("pres sure"), str(tmp_path / "o"), cycles=CY, dt=0.05)
    out = tmp_path / "o"
    assert (out / "pres_sure_fieldconsole.html").exists()
    assert (out / "pres_sure_fieldconsole.json").exists()
    assert (out / "summary.json").exists()
    payload = json.loads((out / "pres_sure_fieldconsole.json")
                         .read_text(encoding="utf-8"))
    assert payload["field"] == "pres sure"
    assert set(payload["panels"]) == {"spectral", "coherence", "spectevol"}
    for pane in payload["panels"].values():
        assert "maps" not in pane                     # no (N,) node arrays
        assert "previews" in pane and "stats" in pane
    summ = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summ["panels"] == ["spectral", "coherence", "spectevol"]


def test_cli_error_cases(tmp_path):
    good_trace = tmp_path / "t.json"
    good_trace.write_text(json.dumps(_art()), encoding="utf-8")
    vpath = tmp_path / "v.npy"
    np.save(vpath, _grid3())

    bad_trace = tmp_path / "no_probe.json"
    bad_trace.write_text(json.dumps({"name": "x", "cycles": [0, 1, 2]}),
                         encoding="utf-8")
    assert main([str(bad_trace), str(vpath)]) == 2

    badv = tmp_path / "badv.json"
    badv.write_text(json.dumps([[1.0, 2.0]]), encoding="utf-8")
    assert main([str(good_trace), str(badv)]) == 2

    assert main([str(good_trace), str(vpath), "--cycles", "500:600"]) == 2
    assert main([str(good_trace), str(vpath), "--panels", "nope"]) == 2
    assert main([str(good_trace), str(vpath), "--ref", "99"]) == 2

    rc = main([str(good_trace), str(vpath), "--cycles", "0:80", "--dt", "0.05",
               "--panels", "spectral,coherence", "--out", str(tmp_path / "ok")])
    assert rc == 0
    assert (tmp_path / "ok" / "P_fieldconsole.html").exists()
