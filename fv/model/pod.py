"""Proper Orthogonal Decomposition over cycle sequences (scPOST POD, P3).

scPOST ships a POD / Clustering operator that decomposes a cycle series
into U / US / VT matrices.  pod_analysis collects one variable snapshot per
cycle file into a (n_cycles, n_fields) matrix, subtracts the temporal mean
and SVD-decomposes it into orthogonal spatial modes with their energy
fractions.  The modes can be registered back on a FieldFile as ordinary
variables for visualisation.
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

    Returns (mean, modes, energies, singular_values): modes are the
    orthogonal spatial modes (each length n_fields), energies their
    fractional energy in descending order.
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
    return mean, [Vt[i].copy() for i in range(k)], energies[:k], S


def pod_analysis(file_set, var, n_modes=10, cache=None):
    """End-to-end POD of one variable across a cycle FileSet."""
    X, loc, length, cycles = collect_snapshots(file_set, var, cache=cache)
    if X is None or length == 0:
        raise ValueError("no usable snapshots for " + repr(var))
    mean, modes, energies, sv = pod_decompose(X, n_modes)
    return {"mean": mean, "modes": modes, "energies": energies,
            "singular_values": sv, "location": loc, "length": length,
            "n_cycles": int(X.shape[0]), "cycles": cycles}


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
