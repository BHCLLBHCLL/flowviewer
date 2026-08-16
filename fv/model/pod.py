"""Proper Orthogonal Decomposition over cycle sequences (scPOST POD/Clustering).

scPOST ships a POD / Clustering operator that decomposes a cycle series
into U / US / VT matrices.  pod_analysis collects one variable snapshot per
cycle file into a (n_cycles, n_fields) matrix, subtracts the temporal mean
and SVD-decomposes it into orthogonal spatial modes with their energy
fractions.  The time coefficients (the scPOST "U" matrix) and per-mode
energies can be exported to CSV.  cluster_analysis runs k-means over the
cycle snapshots and registers the cluster centroid fields back on a
FieldFile as ordinary variables for visualisation.
"""

from __future__ import annotations

import numpy as np


def collect_snapshots(file_set, var, cache=None):
    """(n_cycles, n_fields) snapshot matrix for var across a FileSet.

    Members are loaded through :func:`fv.model.fileset.load_member` so a
    shared ``{path: FieldFile}`` cache (timeline / ALLCYC) can reuse
    already parsed files.  Load, parse and shape errors propagate
    instead of being silently skipped (P2.5).
    """
    from .fileset import load_member
    rows = []
    cycles = []
    loc = "cell"
    for m in getattr(file_set, "members", []) or []:
        ff = load_member(file_set, m.cycle, cache=cache)
        if ff is None:
            continue
        arr = ff.variable_array(var)
        if arr is None:
            raise ValueError("cycle %s has no variable %r"
                             % (m.cycle, var))
        a = np.asarray(arr, dtype=np.float64)
        if a.ndim != 1:
            raise ValueError("variable %r on cycle %s is not a scalar "
                             "field (ndim=%d)" % (var, m.cycle, a.ndim))
        if rows and a.shape != rows[0].shape:
            raise ValueError("variable %r shape mismatch on cycle %s: "
                             "%s vs %s" % (var, m.cycle, a.shape,
                                           rows[0].shape))
        rows.append(a)
        cycles.append(int(m.cycle))
        vi = ff.variables.get(var)
        loc = getattr(vi, "location", "cell") if vi is not None else loc
    if not rows:
        return None, loc, 0, []
    return np.vstack(rows), loc, int(rows[0].shape[0]), cycles


def pod_decompose(X, n_modes=None):
    """SVD POD of a snapshot matrix X (n_samples, n_fields).

    Returns (mean, modes, energies, singular_values, time_coeffs): modes
    are the orthogonal spatial modes (each length n_fields), energies
    their fractional energy in descending order, time_coeffs the
    (n_samples, k) amplitude of each mode per snapshot (U * S, the
    scPOST "U" matrix -- each column is one mode's time series).
    """
    X = np.asarray(X, dtype=np.float64)
    if X.ndim != 2 or X.shape[0] < 1:
        raise ValueError("snapshots must be a 2D matrix")
    mean = X.mean(axis=0)
    Xc = X - mean
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    ss = float(np.sum(S ** 2))
    energies = (S ** 2) / ss if ss > 0 else S
    k = len(S) if n_modes is None else min(int(n_modes), len(S))
    time_coeffs = (U * S)[:, :k]
    return (mean, [Vt[i].copy() for i in range(k)], energies[:k], S,
            time_coeffs)


def pod_analysis(file_set, var, n_modes=10, cache=None):
    """End-to-end POD of one variable across a cycle FileSet."""
    X, loc, length, cycles = collect_snapshots(file_set, var, cache=cache)
    if X is None or length == 0:
        raise ValueError("no usable snapshots for " + repr(var))
    mean, modes, energies, sv, tc = pod_decompose(X, n_modes)
    return {"mean": mean, "modes": modes, "energies": energies,
            "singular_values": sv, "time_coeffs": tc,
            "location": loc, "length": length,
            "n_cycles": int(X.shape[0]), "cycles": cycles}


def export_pod_csv(res, path):
    """Write POD time coefficients (scPOST U) to a CSV file.

    One row per cycle: ``cycle, t_0, ..., t_{k-1}, energy_0, ...`` where
    ``t_i`` is the amplitude of spatial mode i at that snapshot.
    """
    import csv
    tc = np.asarray(res["time_coeffs"], dtype=np.float64)
    cycles = list(res["cycles"])
    energies = list(res["energies"])
    if tc.ndim != 2 or len(cycles) != tc.shape[0]:
        raise ValueError("time_coeffs rows and cycles mismatch")
    k = tc.shape[1]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cycle"] + ["t_%d" % i for i in range(k)]
                   + ["energy_%d" % i for i in range(k)])
        for r in range(tc.shape[0]):
            w.writerow([cycles[r]] + ["%.9g" % v for v in tc[r]]
                       + ["%.9g" % energies[i] for i in range(k)])
    return str(path)


def kmeans(X, n_clusters=3, seed=0, max_iter=200, tol=1e-9):
    """Lloyd k-means over the rows of X (n_samples, n_features).

    Returns (labels, centroids, inertia, iterations): labels assign each
    row to a cluster 0..n_clusters-1, centroids are the k cluster means,
    inertia the within-cluster sum of squared distances at convergence.
    Deterministic for a fixed *seed*; empty clusters keep their previous
    centroid (no relocation step).
    """
    X = np.asarray(X, dtype=np.float64)
    n = X.shape[0]
    if X.ndim != 2 or n < 1:
        raise ValueError("cluster input must be a 2D matrix")
    k = int(n_clusters)
    if not 1 <= k <= n:
        raise ValueError("n_clusters must satisfy 1 <= k <= n_samples")
    rng = np.random.default_rng(seed)
    centroids = X[rng.choice(n, size=k, replace=False)].copy()
    labels = np.zeros(n, dtype=np.int64)
    prev = None
    for it in range(1, max_iter + 1):
        d2 = ((X[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=-1)
        labels = d2.argmin(axis=1)
        for j in range(k):
            m = labels == j
            if m.any():
                centroids[j] = X[m].mean(axis=0)
        inertia = float(d2[np.arange(n), labels].sum())
        if prev is not None and abs(prev - inertia) <= tol * (1.0 + abs(prev)):
            return labels, centroids, inertia, it
        prev = inertia
    return labels, centroids, float(prev), max_iter


def cluster_analysis(file_set, var, n_clusters=3, cache=None, seed=0):
    """k-means clustering of the cycle snapshots of *var* (scPOST Clustering).

    Each cycle's field is one point in the n_fields-dim space, so the
    clusters group cycles with similar instantaneous fields.  Returns a
    dict with per-cycle labels, the k centroid fields, cluster sizes,
    inertia and iteration count; *n_clusters* is capped at the number of
    snapshots.
    """
    X, loc, length, cycles = collect_snapshots(file_set, var, cache=cache)
    if X is None or length == 0:
        raise ValueError("no usable snapshots for " + repr(var))
    k = min(int(n_clusters), X.shape[0])
    labels, centroids, inertia, iters = kmeans(X, k, seed=seed)
    return {"labels": [int(v) for v in labels],
            "centroids": [c.copy() for c in centroids],
            "sizes": [int(v) for v in np.bincount(labels, minlength=k)],
            "inertia": float(inertia), "iterations": int(iters),
            "n_clusters": int(k), "n_cycles": int(X.shape[0]),
            "cycles": cycles, "location": loc, "length": int(length)}


def register_cluster_fields(file_set, ff0, var, n_clusters=3, cache=None,
                            seed=0):
    """Register cluster centroid fields (CLUSTER_i) on *ff0*.

    Each centroid is a representative field of one cluster; the per-cycle
    labels stay available through the returned dict / export_cluster_csv.
    """
    from .dataset import FIELD_KIND_SCALAR, VarInfo
    res = cluster_analysis(file_set, var, n_clusters, cache=cache, seed=seed)
    for i, c in enumerate(res["centroids"]):
        ff0.variables["CLUSTER_" + str(i)] = VarInfo(
            name="CLUSTER_" + str(i), kind=FIELD_KIND_SCALAR,
            location=res["location"], array=c)
    return res


def export_cluster_csv(res, path):
    """Write per-cycle cluster assignment as ``cycle, cluster`` CSV."""
    import csv
    cycles = list(res["cycles"])
    labels = list(res["labels"])
    if len(cycles) != len(labels):
        raise ValueError("labels and cycles mismatch")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cycle", "cluster"])
        for c, lb in zip(cycles, labels):
            w.writerow([c, lb])
    return str(path)


def register_pod_modes(file_set, ff0, var, n_modes=5):
    """Register POD mean + modes on ff0 (POD_MEAN, POD_MODE_i)."""
    from .dataset import FIELD_KIND_SCALAR, VarInfo
    res = pod_analysis(file_set, var, n_modes)
    ff0.variables["POD_MEAN"] = VarInfo(
        name="POD_MEAN", kind=FIELD_KIND_SCALAR, location=res["location"],
        array=res["mean"])
    for i, m in enumerate(res["modes"]):
        ff0.variables["POD_MODE_" + str(i)] = VarInfo(
            name="POD_MODE_" + str(i), kind=FIELD_KIND_SCALAR,
            location=res["location"], array=m)
    return res
