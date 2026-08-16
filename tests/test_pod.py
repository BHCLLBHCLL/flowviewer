# -*- coding: utf-8 -*-
"""POD / Clustering tests (scPOST POD operator, P3)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

FPH = r"D:\training\cgns\examples\tr03_9.fph"



def test_pod_decompose():
    """POD SVD decomposition: orthogonal modes + energy fractions (P3)."""
    import numpy as np
    from fv.model.pod import pod_decompose
    rng = np.random.default_rng(7)
    X = rng.standard_normal((12, 50))
    mean, modes, energies, sv, tc = pod_decompose(X, 6)
    assert mean.shape == (50,)
    assert len(modes) == 6 and len(energies) == 6
    assert tc.shape == (12, 6)  # one time-coefficient column per mode
    assert np.all(energies >= 0) and energies.sum() <= 1.0 + 1e-12
    assert np.all(np.diff(energies) <= 1e-12)  # descending energy
    _, modes_full, e_full, _, tc_full = pod_decompose(X)
    np.testing.assert_allclose(tc_full @ np.vstack(modes_full),
                               X - X.mean(axis=0), atol=1e-8)
    assert abs(e_full.sum() - 1.0) < 1e-9    # modes are orthonormal
    M = np.vstack(modes)
    gram = M @ M.T
    assert np.allclose(gram, np.eye(6), atol=1e-9)
    # rank-deficient data -> exactly one non-zero mode
    Xr = np.tile(rng.standard_normal(50), (5, 1))
    _, modes_r, energies_r, _, _ = pod_decompose(Xr, 3)
    assert energies_r[0] > 0.999


def test_pod_analysis_fileset(tmp_path):
    """POD across a cycle FileSet registers POD_MEAN / POD_MODE_i (P3)."""
    import shutil
    from pathlib import Path
    from fv import api
    from fv.model.fileset import scan_sequence
    base = Path(tmp_path)
    for stale in base.glob("*.fph"):
        stale.unlink()
    for cyc in (1, 2, 3):
        shutil.copyfile(FPH, str(base / f"flow_{cyc}.fph"))
    fs = scan_sequence(str(base / "flow_1.fph"))
    ff0 = api.open_file(FPH)
    res = api.register_pod_modes(fs, ff0, "PRES", 3)
    assert res["n_cycles"] == 3
    assert res["mean"].shape == (ff0.n_cells,)
    assert len(res["modes"]) == 3
    assert "POD_MEAN" in ff0.variables
    assert "POD_MODE_0" in ff0.variables and "POD_MODE_2" in ff0.variables


def test_pod_allcyc_cache_and_no_swallow(tmp_path):
    """POD/ALLCYC share a member cache and surface errors (P2.5)."""
    import shutil
    from pathlib import Path
    from fv import api
    from fv.model.fileset import scan_sequence
    from fv.model.pod import collect_snapshots
    base = Path(tmp_path)
    for stale in base.glob("*.fph"):
        stale.unlink()
    for cyc in (1, 2, 3):
        shutil.copyfile(FPH, str(base / ("flow_" + str(cyc) + ".fph")))
    fs = scan_sequence(str(base / "flow_1.fph"))
    assert len(fs) == 3

    # shared cache: each member parsed once and reused across POD/ALLCYC
    cache = {}
    res = api.pod_analysis(fs, "PRES", 2, cache=cache)
    assert res["cycles"] == [1, 2, 3]
    assert len(cache) == 3
    out = api.register_var_all_cycles(fs, "PP3", "PRES + 2.0", cache=cache)
    assert [c for c, _ in out] == [1, 2, 3]
    assert len(cache) == 3          # no re-parse of cached members
    assert all("PP3" in ff.variables for ff in cache.values())

    # missing variable is an explicit error, not a silent skip
    with pytest.raises(ValueError):
        collect_snapshots(fs, "NO_SUCH_VAR")

    # a corrupt member must propagate, not be swallowed
    (base / "flow_2.fph").write_bytes(b"garbage: not a field file")
    with pytest.raises(Exception):
        collect_snapshots(fs, "PRES")


def test_pod_time_coeffs_and_export(tmp_path):
    """POD time coefficients (U matrix) + CSV export (P3-1)."""
    import csv
    import shutil
    from pathlib import Path
    import numpy as np
    from fv import api
    from fv.model.fileset import scan_sequence
    from fv.model.pod import export_pod_csv
    base = Path(tmp_path)
    for stale in base.glob("*.fph"):
        stale.unlink()
    for cyc in (1, 2, 3):
        shutil.copyfile(FPH, str(base / ("flow_" + str(cyc) + ".fph")))
    fs = scan_sequence(str(base / "flow_1.fph"))
    res = api.pod_analysis(fs, "PRES", 2)
    assert res["time_coeffs"].shape == (3, 2)
    assert res["n_cycles"] == 3
    out = tmp_path / "pod_u.csv"
    export_pod_csv(res, str(out))
    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines()))
    assert rows[0] == ["cycle", "t_0", "t_1", "energy_0", "energy_1"]
    assert [int(r[0]) for r in rows[1:]] == [1, 2, 3]
    assert all(np.isfinite(float(r[1])) for r in rows[1:])


def test_cluster_analysis_and_fields(tmp_path):
    """k-means Clustering: labels / centroids / CSV + API wiring (P3-1)."""
    import csv
    import shutil
    from pathlib import Path
    import numpy as np
    from fv import api
    from fv.model.fileset import scan_sequence
    from fv.model.pod import export_cluster_csv, kmeans
    # separable 2-D data -> both clusters are found
    X = np.array([[0., 0.], [0.1, 0.05], [-0.05, 0.1],
                  [10., 10.], [9.9, 10.1], [10.2, 9.8]])
    labels, cent, inertia, it = kmeans(X, 2, seed=1)
    assert sorted(set(labels.tolist())) == [0, 1]
    assert len(set(labels[:3].tolist())) == 1   # first group together
    assert len(set(labels[3:].tolist())) == 1   # second group together
    assert labels[0] != labels[3]
    assert inertia > 0 and it >= 1
    with pytest.raises(ValueError):
        kmeans(np.zeros((0, 5)), 2)
    # end-to-end across a cycle FileSet (identical snapshots stay stable)
    base = Path(tmp_path)
    for stale in base.glob("*.fph"):
        stale.unlink()
    for cyc in (1, 2, 3):
        shutil.copyfile(FPH, str(base / ("flow_" + str(cyc) + ".fph")))
    fs = scan_sequence(str(base / "flow_1.fph"))
    res = api.cluster_analysis(fs, "PRES", 2)
    assert res["n_clusters"] == 2 and res["n_cycles"] == 3
    assert len(res["labels"]) == 3 and all(0 <= lb < 2 for lb in res["labels"])
    assert sum(res["sizes"]) == 3
    assert len(res["centroids"]) == 2
    assert res["centroids"][0].shape == res["centroids"][1].shape
    # deterministic for a fixed seed
    assert api.cluster_analysis(fs, "PRES", 2)["labels"] == res["labels"]
    # cluster count is capped by the number of snapshots
    assert api.cluster_analysis(fs, "PRES", 9)["n_clusters"] == 3
    # centroid fields register back onto a FieldFile
    ff0 = api.open_file(FPH)
    api.register_cluster_fields(fs, ff0, "PRES", 2)
    assert "CLUSTER_0" in ff0.variables and "CLUSTER_1" in ff0.variables
    assert ff0.variables["CLUSTER_0"].array.shape == (ff0.n_cells,)
    # per-cycle assignment exports as CSV
    out = tmp_path / "clusters.csv"
    export_cluster_csv(res, str(out))
    rows = list(csv.reader(out.read_text(encoding="utf-8").splitlines()))
    assert rows[0] == ["cycle", "cluster"]
    assert [int(r[0]) for r in rows[1:]] == [1, 2, 3]
