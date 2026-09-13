"""Regression: numpy's BLAS/LAPACK must resolve without conda activation.

Launching a conda env's ``python.exe`` directly (without ``conda activate``)
leaves the env's ``Library/bin`` off ``PATH``. numpy is built with
delay-loaded ``libcblas``/``liblapack`` symbols, so on any array of >=500
elements the BLAS dispatch fails with the native code ``0xC06D007F``
(ERROR_PROC_NOT_FOUND) instead of raising a Python error -- killing the
process. That is what crashed projecting cell vectors onto a cut plane
(``np.dot`` in ``fv.render.plane``) and POD/DMD (``np.linalg.svd``).

``fv`` registers the directory at import, so these BLAS-backed operations
must work with no caller-side PATH setup.
"""
from __future__ import annotations

import os
import sys

import fv
import numpy as np


def test_conda_library_bin_registered():
    fv._register_conda_dll_dir()
    if not sys.platform.startswith("win"):
        return
    bindir = os.path.join(sys.prefix, "Library", "bin")
    if not os.path.isdir(bindir):
        return
    parts = os.environ.get("PATH", "").split(os.pathsep)
    assert bindir in parts


def test_large_blas_dot_resolves():
    rng = np.random.default_rng(0)
    arr = rng.standard_normal((800, 3))
    n = np.array([0.0, 0.0, 1.0])
    out = arr - np.outer(np.dot(arr, n), n)
    assert out.shape == arr.shape
    assert np.isfinite(out).all()
    assert np.allclose(out[:, 2], 0.0)


def test_large_linalg_svd_resolves():
    rng = np.random.default_rng(0)
    m = rng.standard_normal((64, 32))
    _, s, _ = np.linalg.svd(m, full_matrices=False)
    assert s.shape == (32,)
    assert np.isfinite(s).all()
