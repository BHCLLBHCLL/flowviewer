"""R60 tests: spatio-temporal spectral-evolution (non-stationarity) field map.

Pure NumPy, headless, no CGNS, no VTK. Lifts R43's spectrogram summary to the
whole mesh: slides a short-time spectral window over every vertex's reconstructed
frame sequence and maps spectral centroid / bandwidth / centroid drift /
intermittency. Reuses R57 ``reconstruct_sequence`` and R41 ``mean_dt``.
"""

from __future__ import annotations

import json

import numpy as np
from fv.spectevol import (
    build_spectevol_report,
    main,
    render_html,
    spectral_evolution_field,
    write_spectevol_report,
)


def _grid3() -> np.ndarray:
    return np.array([[i, j, 0.0] for i in range(3) for j in range(3)],
                    dtype=np.float64)


def _art(name="P"):
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)                       # 400 cycles
    v = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)        # 1 Hz tone
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


def _frames():
    M = 400
    t = np.arange(M) * 0.05
    tone = np.sin(2 * np.pi * 1.0 * t)                 # steady 1 Hz
    const = np.full(M, 3.0)                            # no fluctuation
    c = np.linspace(0.5, 2.0, M)                       # chirp f: .5 -> 2 Hz
    chirp = np.sin(2 * np.pi * (0.5 * t + 0.5 * ((c - 0.5) / 1.5) / 20.0 * t * t))
    return np.stack([tone, const, chirp], axis=1), M


def test_spectral_evolution_field_steady_const_chirp():
    frames, _ = _frames()
    sf = spectral_evolution_field(frames, dt=0.05)
    assert sf["centroid"].shape == (3,) and sf["intermittency"].shape == (3,)
    assert sf["nwin"] >= 1 and sf["nyquist"] > 9.9
    # steady tone: centroid ~1 Hz, narrow, stationary, uniform energy
    assert 0.8 < sf["centroid"][0] < 1.2
    assert 0.0 < sf["bandwidth"][0] < 0.6
    assert abs(sf["drift"][0]) < 0.15
    assert abs(sf["intermittency"][0]) < 0.15
    # constant column: zero energy -> NaN centroid, ~0 intermittency
    assert np.isnan(sf["centroid"][1])
    assert abs(sf["intermittency"][1]) < 1e-9


def test_spectral_evolution_field_chirp_drift():
    frames, _ = _frames()
    sf = spectral_evolution_field(frames, dt=0.05, nperseg=128)
    # chirp: centroid migrates across windows -> more drift than steady tone
    assert 0.5 < sf["centroid"][2] < 2.0
    assert sf["drift"][2] > sf["drift"][0]             # chirp > steady tone
    assert sf["drift"][2] > 0.01
    assert sf["nwin"] >= 3


def test_spectral_evolution_field_degenerate():
    degen = spectral_evolution_field(np.zeros((1, 4)), dt=1.0)  # M<2
    assert np.isnan(degen["centroid"]).all()
    short = spectral_evolution_field(np.zeros((4, 3)), dt=1.0, nperseg=1)
    assert np.isnan(short["centroid"]).all()          # nperseg<2


def test_build_report_maps_and_tone_centroid():
    rep = build_spectevol_report(_grid3(), _art(), dt=0.05)
    assert rep["n_frames"] > 2 and rep["n_vertices"] == 9
    assert rep["nwin"] >= 1 and rep["dt"] == 0.05
    for m in ("centroid", "bandwidth", "drift", "intermittency"):
        assert rep["maps"][m].shape == (9,)
        assert m in rep["stats"] and m in rep["previews"]
    assert rep["previews"]["centroid"].shape == (24, 24)
    # node 0 is the probe carrying the steady 1 Hz tone
    assert 0.5 < rep["maps"]["centroid"][0] < 1.5

    # dt inferred via mean_dt
    rep2 = build_spectevol_report(_grid3(), _art())
    assert abs(rep2["dt"] - 0.05) < 1e-9


def test_build_report_empty_graceful():
    art = {"name": "x", "cycles": [], "probes": []}
    empty = build_spectevol_report(_grid3(), art)
    assert empty["n_probes"] == 0 and empty["n_frames"] == 0
    assert np.isnan(empty["maps"]["centroid"]).all()
    assert empty["stats"]["centroid"]["coverage"] == 0


def test_render_html_sections_and_escaping():
    art = _art("<script>alert(1)</script>")
    rep = build_spectevol_report(_grid3(), art, dt=0.05)
    h = render_html(rep)
    for title in ("Spectral centroid", "Centroid drift", "Energy intermittency"):
        assert title in h
    assert h.count("<canvas") == 4
    assert "<script>" in h
    assert "&lt;script&gt;" in h


def test_render_html_empty():
    art = {"name": "x", "cycles": [], "probes": []}
    h = render_html(build_spectevol_report(_grid3(), art))
    assert "No data." in h


def test_write_report_files_slim_and_csv(tmp_path):
    write_spectevol_report(_grid3(), _art("pres sure"), str(tmp_path / "o"),
                           dt=0.05)
    out = tmp_path / "o"
    for f in ("pres_sure_spectevol.html", "pres_sure_spectevol.json",
              "pres_sure_spectevol_nodes.csv", "summary.json"):
        assert (out / f).exists()
    payload = json.loads((out / "pres_sure_spectevol.json")
                         .read_text(encoding="utf-8"))
    assert "maps" not in payload
    assert payload["stats"]["centroid"]["coverage"] > 0
    csv_head = (out / "pres_sure_spectevol_nodes.csv").read_text(
        encoding="utf-8").splitlines()[0]
    assert csv_head == "node,x,y,z,centroid,bandwidth,drift,intermittency"


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

    rc = main([str(good_trace), str(vpath), "--cycles", "0:120",
               "--dt", "0.05", "--nperseg", "64", "--out", str(tmp_path / "ok")])
    assert rc == 0
    assert (tmp_path / "ok" / "P_spectevol.html").exists()
