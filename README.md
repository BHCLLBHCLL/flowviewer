# flowviewer

Post-processing viewer for Cradle CFD `fph` / `fld` / `cgns` files.
Reads, renders, cuts, and post-processes Cradle STREAM/SCFLOW/FLOW results,
with a CradleViewer (`cvw`) byte-faithful export path.

## Requirements

- Python 3.9+
- `numpy>=1.24`
- `vtk>=9.3` (plane-cut/ugrid features)
- `PyQt5>=5.15` (GUI)

> **VTK version note:** VTK 9.4.2 and newer trigger an access violation
> (`0xC0000005`) in `vtkCutter` for `vtkConvexPointSet` grids.
> Install `pip install --user vtk==9.3.1` if plane-cut tests crash.
> Check `python -c "import vtk; print(vtk.VTK_VERSION)"` first.

## Installation

```bash
pip install -e .
# or, in a virtualenv
pip install .
```

After installing, the `flowviewer` command-line entry point is available:

```bash
flowviewer            # launch the GUI
flowviewer file.fph   # open a result file at startup
flowviewer --version  # print the version and exit
```

Without installing, you can run from the source tree:

```bash
python fv_gui.py file.fph
```

## Usage

- Load `fph` / `fld` / `cgns` result files.
- Render scalars/vectors on cuts, surfaces, streamlines, isosurfaces, etc.
- Register derived variables with user-defined functions (R18).
- Vortex identification presets: vorticity, Q-criterion, lambda-2,
  helicity and the velocity-gradient components (R23).
- Compare two datasets and generate scalar-statistics CSV reports (R20).
- Export cuts/scenes; CradleViewer `cvw` round-trips preserve `fph`
  (104 regions) and `fld` (13 regions) structure.

## Testing

```bash
pip install -e .[dev]
python -m pytest
```

## Benchmarks

```bash
python scripts/benchmark.py [file ...]
```

Times the hot paths (dataset load, cold/cached ugrid build, scalar variable
registration, Green-Gauss velocity gradient) over the bundled sample files.

## Development map

- R17 - CradleViewer (`cvw`) format reverse-engineering, loader and byte-faithful writer.
- R18 - variable registration: derived expressions, user-defined functions, vector auto-scalarization.
- R19 - plane-cut performance: batched FPH ugrid build + mesh-fingerprint cache.
- R20 - multi-dataset statistics and automated CSV reports.
- R21 - rendering depth: DST colormap / isosurface animation.
- R22 - packaging engineering: `pyproject.toml`, CLI entry point, benchmarks.
- R23 - vortex-identification presets: Green-Gauss gradient kernel,
  vorticity / Q-criterion / lambda-2 / helicity, VGRAD component library.
