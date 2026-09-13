"""flowviewer: post-processing viewer for Cradle CFD fph/fld files."""

import os
import sys

__version__ = "0.1.0"


def _register_conda_dll_dir() -> None:
    """Expose a conda env's ``Library/bin`` to numpy's delay-loaded BLAS.

    Launching an env's ``python.exe`` directly (without ``conda activate``)
    leaves ``Library/bin`` off ``PATH``. numpy then cannot resolve the
    delay-loaded ``libcblas``/``liblapack`` symbols, so ``np.dot`` and
    ``np.linalg`` on arrays of >=500 elements die with a native
    ``0xC06D007F`` (ERROR_PROC_NOT_FOUND) instead of raising -- e.g. the
    ``np.dot`` that projects vectors onto a cut plane, or ``svd`` in
    POD/DMD. Prepending the directory restores the search path.
    """
    if not sys.platform.startswith("win"):
        return
    bindir = os.path.join(sys.prefix, "Library", "bin")
    if not os.path.isdir(bindir):
        return
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if bindir not in parts:
        os.environ["PATH"] = bindir + os.pathsep + os.environ.get("PATH", "")
    try:
        os.add_dll_directory(bindir)
    except (AttributeError, OSError):
        pass


_register_conda_dll_dir()
