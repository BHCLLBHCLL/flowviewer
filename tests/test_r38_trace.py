"""R38 tests: monitoring-point time traces (probe history).

Headless and dependency-light: no VTK, no h5py/CGNS. A minimal fake streaming
handle (``field_names``/``field_len``/``iter_tiles``) and a fake mesh stand in
for ``StreamCgnsHandle`` / the streaming CGNS mesh, so the whole round verifies
in any environment (mirroring R36/R37).
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv.trace import (
    field_probe_values,
    resolve_probe_nodes,
    time_trace,
    write_traces,
)

# ── fakes ──────────────────────────────────────────────────────────────────

class FakeHandle:
    """Minimal streaming handle: node fields as plain arrays."""

    def __init__(self, fields):
        # name -> full node array
        self._f = {k: np.asarray(v, dtype=np.float64) for k, v in fields.items()}

    def field_names(self):
        return list(self._f)

    def field_len(self, name):
        return int(self._f[name].size)

    def iter_tiles(self, name, tile=0):
        data = self._f[name]
        n = int(data.size)
        tsize = int(tile) if tile > 0 else max(1, (n + 3) // 4)
        for start in range(0, n, tsize):
            yield start, data[start:start + tsize]


def _mesh(verts):
    return {"vertices": np.asarray(verts, dtype=np.float64)}


_MESH = _mesh([[0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0],
               [0.0, 0, 1], [5.0, 5, 5], [8.0, 8, 8]])


def _handle(cycle):
    # 1D node fields, faithfully mirroring StreamCgnsHandle (iter_tiles yields
    # 1D windows over node-index ranges regardless of field kind).
    return FakeHandle({
        "P": [float(cycle) * 10 + i for i in range(6)],
        "V": [float(cycle) for _ in range(6)],
    })


def _timeline(cycles=(1, 2, 3)):
    for c in cycles:
        yield c, _handle(c), _MESH


# ── probe → node binding ───────────────────────────────────────────────────

def test_resolve_probe_nodes_picks_nearest():
    probes = [(0.95, 0.05, 0.0), (7.9, 8.1, 7.9)]
    nodes = resolve_probe_nodes(_MESH, probes)
    assert nodes[0]["node"] == 1          # (1,0,0)
    assert nodes[0]["xyz"] == pytest.approx((1.0, 0.0, 0.0))
    assert nodes[1]["node"] == 5          # (8,8,8)
    assert nodes[0]["query"] == pytest.approx((0.95, 0.05, 0.0))


def test_resolve_probe_nodes_empty_mesh_yields_minus_one():
    nodes = resolve_probe_nodes(_mesh([]), [(0.0, 0.0, 0.0)])
    assert nodes[0]["node"] == -1
    assert nodes[0]["xyz"] is None


# ── per-node field read ────────────────────────────────────────────────────

def test_field_probe_values_reads_node_value():
    assert field_probe_values(_handle(2), "P", 3) == pytest.approx(23.0)
    assert field_probe_values(_handle(2), "P", 5) == pytest.approx(25.0)


def test_field_probe_values_surfaces_missing_and_oob():
    h = _handle(1)
    assert np.isnan(field_probe_values(h, "NOT_A_FIELD", 0))
    assert np.isnan(field_probe_values(h, "P", 999))   # out of range
    assert np.isnan(field_probe_values(h, "P", -1))


# ── time trace walk ────────────────────────────────────────────────────────

def test_time_trace_records_series_over_cycles():
    probes = [(0.95, 0.05, 0.0), (7.9, 8.1, 7.9)]   # node 1 and node 5
    rep = time_trace(_timeline(), probes, ["P", "V"])
    assert set(rep["fields"]) == {"P", "V"}
    p = rep["fields"]["P"]
    assert p["cycles"] == [1, 2, 3]
    assert len(p["probes"]) == 2
    # probe 0 -> node 1: P[node1] = cycle*10 + 1
    assert p["probes"][0]["values"] == pytest.approx([11.0, 21.0, 31.0])
    # probe 1 -> node 5: P[node5] = cycle*10 + 5
    assert p["probes"][1]["values"] == pytest.approx([15.0, 25.0, 35.0])
    # vector field stores its first component at the node row
    v = rep["fields"]["V"]
    assert v["probes"][0]["values"] == pytest.approx([1.0, 2.0, 3.0])


def test_time_trace_binding_once_from_first_cycle():
    # mesh changes only by cycle; binding follows the first cycle's mesh
    rep = time_trace(_timeline((1, 2)), [(0.95, 0.05, 0.0)], ["P"])
    assert rep["fields"]["P"]["probes"][0]["node"] == 1
    assert rep["fields"]["P"]["cycles"] == [1, 2]


def test_time_trace_reports_nan_for_missing_field():
    rep = time_trace(_timeline((1, 2)), [(0.0, 0.0, 0.0)], ["GHOST"])
    g = rep["fields"]["GHOST"]
    assert all(np.isnan(v) for v in g["probes"][0]["values"])


# ── I/O ────────────────────────────────────────────────────────────────────

def test_write_traces_emits_per_field_json_and_manifest(tmp_path):
    rep = time_trace(_timeline((1, 2, 3)), [(0.0, 0.0, 0.0)], ["P", "V"])
    man = write_traces(rep, str(tmp_path))
    assert set(man["fields"]) == {"P", "V"}
    assert (tmp_path / "manifest.json").exists()
    # node 0 sample value check on disk
    pfile = tmp_path / "P.json"
    assert pfile.exists()
    with open(pfile, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["cycles"] == [1, 2, 3]
    assert data["probes"][0]["values"] == pytest.approx([10.0, 20.0, 30.0])


def test_write_traces_sanitises_weird_field_names(tmp_path):
    rep = {"fields": {"pres sure": {"name": "pres sure",
                                     "cycles": [1], "probes": []}}}
    man = write_traces(rep, str(tmp_path))
    assert (tmp_path / "pres_sure.json").exists()
    assert man["fields"]["pres sure"]["file"] == "pres_sure.json"
