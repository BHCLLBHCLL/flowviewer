"""R67 tests: Analysis report parameter panel (pure parameter layer).

R66 made the Analysis menu run reports, but every report used defaults — the
``dt/cycles/step/frames/k/p/neighbors/ref_probe/nperseg/blocksize/top/cycle/
dmd/field/preview/source/panels`` tunables were all hard-wired. R67 introduces a
pure, headless-testable parameter layer in ``fv.gui.analysis``: a ``Param``
metadata object drives a per-kind schema (``report_params``), a default snapshot
(``default_params``), a coercing/clamping normaliser (``normalize_params``) and a
status-bar summary (``param_summary``); ``run_report`` now accepts and forwards
all of those tunables. These tests exercise the schema/coercion matrix and smoke
the expanded ``run_report`` forwarding on the tiny-mesh fixtures R63-R66 used.

Pure NumPy, headless — no display, no PyQt widgets are instantiated.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from fv.gui.analysis import (
    REPORTS,
    Param,
    _coerce,
    default_params,
    normalize_params,
    param_summary,
    report_params,
    run_report,
)

CY = list(range(0, 60))

_ALL_TYPES = ("int", "float", "bool", "choice", "str", "str_opt", "tuple")


def _grid3() -> np.ndarray:
    return np.array([[i, j, 0.0] for i in range(3) for j in range(3)],
                    dtype=np.float64)


def _art(name="P"):
    dt = 0.05
    t = np.arange(0.0, 10.0, dt)
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


def test_report_params_for_every_kind_unique_and_typed():
    for kind in REPORTS:
        ps = report_params(kind)
        assert ps
        keys = [p.key for p in ps]
        assert len(keys) == len(set(keys))
        for p in ps:
            assert p.key and p.label and p.type
            assert p.type in _ALL_TYPES
            assert isinstance(p.default, (str, int, float, bool, type(None), tuple))


def test_report_params_unknown_raises():
    with pytest.raises(ValueError):
        report_params("nope")


def test_report_params_field_family():
    spec = report_params("spectral")
    coh = report_params("coherence")
    evo = report_params("evolution")
    con = report_params("console")
    assert [p.key for p in spec] == [
        "source", "cycles", "dt", "step", "frames", "k", "p", "neighbors", "preview"]
    assert coh[:len(spec)] == spec
    assert [p.key for p in coh[len(spec):]] == ["ref_probe", "nperseg", "blocksize"]
    assert [p.key for p in evo] == [p.key for p in coh]
    assert [p.key for p in con[len(coh):]] == ["panels"]
    src = next(p for p in spec if p.key == "source")
    assert src.type == "choice" and set(src.choices) == {"pod", "dmd"}


def test_report_params_spatial_family():
    pod = report_params("spatial_pod")
    dmd = report_params("spatial_dmd")
    field = report_params("spatial_field")
    assert pod[0].key == "cycles" and pod[-1].key == "preview"
    assert [p.key for p in dmd[:len(pod)]] == [p.key for p in pod]
    assert [p.key for p in dmd[len(pod):]] == ["dmd_top"]
    assert [p.key for p in field[len(pod):]] == ["ref_probe", "nperseg", "blocksize", "source"]


def test_default_params_uses_param_defaults():
    for kind in REPORTS:
        d = default_params(kind)
        ps = report_params(kind)
        assert set(d) == {p.key for p in ps}
        for p in ps:
            assert d[p.key] == p.default


def test_normalize_params_drops_unknown_and_fills_missing():
    d = normalize_params("spectral", {"bogus": 123})
    assert set(d) == {p.key for p in report_params("spectral")}
    assert d == default_params("spectral")


def test_normalize_params_int_clamp():
    d = normalize_params("spectral", {"step": 0, "neighbors": 9999})
    assert d["step"] == 1
    assert d["neighbors"] == 9999
    assert d["preview"] == 24


def test_normalize_params_float_blank_to_default():
    assert normalize_params("spectral", {"dt": ""})["dt"] is None
    assert normalize_params("spectral", {"dt": "0.1"})["dt"] == 0.1
    assert normalize_params("spectral", {"dt": "abc"})["dt"] is None


def test_normalize_params_choice_invalid_to_default():
    assert normalize_params("spectral", {"source": "bogus"})["source"] == "pod"
    assert normalize_params("spectral", {"source": "dmd"})["source"] == "dmd"


def test_normalize_params_str_opt_blank_to_none():
    assert normalize_params("spectral", {"cycles": "0:100"})["cycles"] == "0:100"
    assert normalize_params("spectral", {"cycles": "  "})["cycles"] is None


def test_normalize_params_tuple_from_list_and_csv():
    assert normalize_params("console", {"panels": ["spectral", "coherence"]})["panels"] == (
        "spectral", "coherence")
    assert normalize_params("console", {"panels": "spectral,coherence"})["panels"] == (
        "spectral", "coherence")
    assert normalize_params("console", {"panels": ""})["panels"] == (
        "spectral", "coherence", "spectevol")


def test_normalize_params_json_serializable():
    for kind in ("spectral", "console", "spatial_field"):
        d = normalize_params(kind, {"dt": 0.05, "panels": "spectral,coherence",
                                    "cycles": "0:100", "source": "dmd"})
        json.dumps(d)


def test_coerce_bool_contract():
    b = Param("flag", "Flag", "bool", False)
    assert _coerce(b, True) is True
    assert _coerce(b, 1) is True
    assert _coerce(b, 0) is False
    assert _coerce(b, "yes") is True
    assert _coerce(b, "off") is False
    assert _coerce(b, None) is False


def test_param_summary_defaults():
    assert param_summary("spectral", default_params("spectral")) == "defaults"
    assert param_summary("spectral", None) == "defaults"


def test_param_summary_marks_nondefaults():
    d = default_params("spectral")
    d["k"] = 6
    d["source"] = "dmd"
    s = param_summary("spectral", d)
    assert "k=6" in s and "source=dmd" in s
    assert "neighbors=" not in s


def test_run_report_forwards_extra_kwargs(tmp_path):
    v = _grid3()
    a = _art()
    spec = run_report("spectral", v, a, str(tmp_path), dt=0.05, cycles=CY,
                      preview=8, k=4, p=3.0, neighbors=6, source="pod")
    assert spec and spec.endswith(".html") and Path(spec).exists()

    coh = run_report("coherence", v, a, str(tmp_path), dt=0.05, cycles=CY,
                     preview=8, ref_probe=1, nperseg=64, blocksize=512)
    assert coh and Path(coh).exists()

    con = run_report("console", v, a, str(tmp_path), dt=0.05, cycles=CY,
                     preview=8, ref_probe=1, panels=("spectral", "coherence"))
    assert con and Path(con).exists()

    dmd = run_report("spatial_dmd", v, a, str(tmp_path), dt=0.05, cycles=CY,
                     top=3, cycle=2, dmd_top=4, p=1.5, neighbors=6)
    assert dmd and Path(dmd).exists()

    field = run_report("spatial_field", v, a, str(tmp_path), dt=0.05, cycles=CY,
                       top=3, cycle=1, source="dmd", ref_probe=0, preview=12)
    assert field and Path(field).exists()
