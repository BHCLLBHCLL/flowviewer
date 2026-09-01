#!/usr/bin/env python3
"""flowviewer benchmark harness (R22 packaging/perf + R24 thresholds).

Times the hot paths over the sample files: dataset load, ugrid build
(first call vs cached), scalar variable registration and the R23
Green-Gauss velocity gradient. Prints a small table.

Mode ``--check`` also asserts each measurement against the thresholds in
``scripts/benchmarks.json`` (a "permissive-multiple" gate so CI speed
differences do not cause false failures) and exits non-zero (2) when a
threshold is exceeded.

Usage:
    python scripts/benchmark.py [file ...] [--check] [--thresholds path]
    # defaults to the bundled example FPH sample when present.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULTS = [r"D:\training\cgns\examples\tr03_9.fph"]
_DEFAULT_THRESHOLDS = str(Path(__file__).with_name("benchmarks.json"))

# measured phase key -> human label
_PHASES = ["load", "ugrid_build", "ugrid_cached", "register_var",
           "vortex_grad", "plane_cut_cold", "plane_cut_warm",
           "cgns_load_serial", "cgns_load_parallel", "cgns_load_thread"]


def _ensure_multi_zone_cgns(path: Path) -> bool:
    """Write a synthetic multi-zone CGNS-HDF5 for the S2 loader phase."""
    try:
        import h5py
        import numpy as np
    except Exception:
        return False
    if path.exists():
        return True
    nx, ny, nz = 8, 8, 8
    xx, yy, zz = np.meshgrid(np.arange(nx), np.arange(ny), np.arange(nz),
                             indexing="ij")
    coords = np.stack([xx, yy, zz], axis=-1).astype(np.float64)
    with h5py.File(str(path), "w") as f:
        base = f.create_group("Base")
        for i in range(4):
            z = base.create_group("Zone%d" % i)
            zt = z.create_group("ZoneType")
            zt.create_dataset(" data", data=np.array([b"Structured"]))
            gc = z.create_group("GridCoordinates")
            for ax, idx in zip(("CoordinateX", "CoordinateY", "CoordinateZ"),
                               range(3)):
                g = gc.create_group(ax)
                g.create_dataset(" data", data=coords[..., idx] + i * 10.0)
    return True


def _t(fn, *a):
    t0 = time.perf_counter()
    r = fn(*a)
    return time.perf_counter() - t0, r


def bench(path: str) -> list:
    """Return [(phase_key, seconds, note), ...] for one sample file."""
    row = []
    from fv.model.dataset import load_file
    dt, ff = _t(load_file, path)
    nv = len(ff.vertices) if ff.vertices is not None else 0
    row.append(("load", dt, "%d cells / %d verts" % (ff.n_cells, nv)))

    try:
        from fv.render.plane import build_ugrid
        try:                      # clear any prior cache for a cold build
            ff._ugrid_cache = None
        except Exception:
            pass
        dt, (ug, _cc) = _t(build_ugrid, ff)
        row.append(("ugrid_build", dt, "%d cells" % ug.GetNumberOfCells()))
        dt, _ = _t(build_ugrid, ff)
        row.append(("ugrid_cached", dt, "cache hit"))

        # R26-S1: cold (cache miss) vs warm (LRU hit) plane cut
        from fv.model.objects import PlaneObject
        from fv.render.plane import clear_cut_cache, cut_grid
        clear_cut_cache()
        obj = PlaneObject(point=(0.5, 0.5, 0.5), normal=(0.0, 0.0, 1.0))
        dt, _ = _t(cut_grid, ug, obj)
        row.append(("plane_cut_cold", dt, "vtkCutter miss"))
        dt, _ = _t(cut_grid, ug, obj)
        row.append(("plane_cut_warm", dt, "LRU hit"))
    except Exception as e:        # vtk absent
        row.append(("ugrid_build", 0.0, "skip: %s" % e))
        row.append(("ugrid_cached", 0.0, "skip"))
        row.append(("plane_cut_cold", 0.0, "skip: %s" % e))
        row.append(("plane_cut_warm", 0.0, "skip"))

    from fv.model.varreg import register_variable
    if "PRES" in ff.variables:
        dt, _ = _t(register_variable, ff, "BENCH_DP", "PRES * 2.0")
        row.append(("register_var", dt, "PRES * 2.0"))

    try:                          # R23 gradient kernel hot path
        from fv.model.derived import velocity_gradient
        dt, _ = _t(velocity_gradient, ff)
        row.append(("vortex_grad", dt, "Green-Gauss VEL"))
    except Exception as e:
        row.append(("vortex_grad", 0.0, "skip: %s" % e))

    # R26-S2: multi-zone CGNS load, serial vs process-pool worker count
    try:
        import tempfile
        from fv.crdl.cgns import read_cgns
        multi = Path(tempfile.gettempdir()) / "flowviewer_bench_multi.cgns"
        if _ensure_multi_zone_cgns(multi):
            dt, m0 = _t(read_cgns, str(multi), 0)
            n = m0["n_cells"] if m0 else 0
            row.append(("cgns_load_serial", dt, "workers=0 %d cells" % n))
            dt, _ = _t(read_cgns, str(multi), 4)
            row.append(("cgns_load_parallel", dt, "workers=4 proc"))
            dt, _ = _t(read_cgns, str(multi), 4, True)
            row.append(("cgns_load_thread", dt, "workers=4 thread"))
        else:
            row.append(("cgns_load_serial", 0.0, "skip: no h5py"))
            row.append(("cgns_load_parallel", 0.0, "skip"))
            row.append(("cgns_load_thread", 0.0, "skip"))
    except Exception as e:
        row.append(("cgns_load_serial", 0.0, "skip: %s" % e))
        row.append(("cgns_load_parallel", 0.0, "skip"))
        row.append(("cgns_load_thread", 0.0, "skip"))

    return row


def _load_thresholds(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv
    if check:
        argv.remove("--check")
    th_path = _DEFAULT_THRESHOLDS
    if "--thresholds" in argv:
        i = argv.index("--thresholds")
        th_path = argv[i + 1]
        del argv[i:i + 2]
    paths = argv or [p for p in DEFAULTS if Path(p).exists()]
    if not paths:
        print("no sample file found; pass paths on the command line")
        return 1

    thresholds = _load_thresholds(th_path) if check else None
    perfile = None
    if thresholds is not None:
        perfile = thresholds.get("default", {})

    print("%-14s %-14s %-10s %s" % ("sample", "phase", "seconds", "note"))
    print("-" * 60)
    failed = False
    for p in paths:
        try:
            rows = bench(p)
        except Exception as e:
            print("%-14s %-14s %-10s %s" % (Path(p).name, "error", "-", e))
            failed = True
            continue
        base = thresholds.get(Path(p).name, perfile) if check else None
        for phase, secs, note in rows:
            th = None
            if base is not None:
                th = base.get(phase)
            mark = "OK  " if th is None or secs <= th else "FAIL"
            if th is not None and secs > th:
                failed = True
            if th is not None:
                note = "%s (limit %.2fs)" % (note, th)
            print("%-14s %-14s %-10.3f %s %s"
                  % (Path(p).name, phase, secs, mark, note))
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))