#!/usr/bin/env python3
"""flowviewer benchmark harness (R22 packaging/perf).

Times the hot paths over the sample files: dataset load, ugrid build
(first call vs cached), and a scalar variable registration. Prints a small
table.

Usage:
    python scripts/benchmark.py [file ...]
    # defaults to the bundled example FPH sample when present.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULTS = [r"D:\training\cgns\examples\tr03_9.fph"]


def _t(fn, *a):
    t0 = time.perf_counter()
    r = fn(*a)
    return time.perf_counter() - t0, r


def bench(path: str):
    row = []
    from fv.model.dataset import load_file
    dt, ff = _t(load_file, path)
    nv = len(ff.vertices) if ff.vertices is not None else 0
    row.append(("load", "%.3fs" % dt, "%d cells / %d verts" % (ff.n_cells, nv)))

    try:
        from fv.render.plane import build_ugrid
        # clear any prior cache so we measure a cold build
        try:
            ff._ugrid_cache = None
        except Exception:
            pass
        dt, (ug, _cc) = _t(build_ugrid, ff)
        row.append(("ugrid build", "%.3fs" % dt, "%d cells" % ug.GetNumberOfCells()))
        dt, _ = _t(build_ugrid, ff)
        row.append(("ugrid cached", "%.3fs" % dt, "cache hit"))
    except Exception as e:  # vtk absent
        row.append(("ugrid", "skip", "%s" % e))

    from fv.model.varreg import register_variable
    if "PRES" in ff.variables:
        dt, _ = _t(register_variable, ff, "BENCH_DP", "PRES * 2.0")
        row.append(("register var", "%.3fs" % dt, "PRES * 2.0"))

    return row


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    paths = argv or [p for p in DEFAULTS if Path(p).exists()]
    if not paths:
        print("no sample file found; pass paths on the command line")
        return 1
    print("%-16s %-10s %-20s" % ("sample", "phase", "seconds / note"))
    print("-" * 50)
    for p in paths:
        try:
            rows = bench(p)
        except Exception as e:
            print("%-16s %-10s %s" % (Path(p).name, "error", e))
            continue
        for phase, secs, note in rows:
            print("%-16s %-10s %-20s" % (Path(p).name, phase, secs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
