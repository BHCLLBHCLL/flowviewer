"""Particle result rendering for scFLOW FPH files.

'LS_ParticlesPosition' carries one [12][200] (50 float32) block per
coordinate (X, Y, Z); 'LS_ParticleV:<var>' sections carry velocity/
particle variables.  Parsed in 'fv.crdl.fields.parse_particles' and
'fv.crdl.fields.parse_particle_variables'.
"""

from typing import Optional

import numpy as np
import vtk
from vtk.util import numpy_support as _vns

from ..crdl.fields import parse_particles, parse_particle_variables
from ..model.objects import ParticleObject


def build_particle_actors(obj: ParticleObject,
                          ff) -> dict[str, vtk.vtkActor]:
    """Build particle actors -> {'particle': ..., 'vector': ...}.

    Reads positions/velocities directly from the FieldFile buffer
    (ff.path), colouring the points by scalar attribute when
    requested.  The vector variable follows 'obj.vector_var' (default
    VELP) and the scalar variable 'obj.scalar_var' selects a particle
    variable magnitude / component when given (P0.4).
    """
    with open(ff.path, "rb") as fh:
        data = fh.read()
    parsed = parse_particles(data)
    if parsed is None:
        return {}
    positions, _ = parsed

    if positions.shape[0] == 0:
        return {}

    pvars = parse_particle_variables(data)
    # Vector selection: obj.vector_var, falling back to VELP
    velocities = None
    if obj.show_vector:
        want = (obj.vector_var or "VELP").strip() or "VELP"
        if want in pvars:
            velocities = pvars[want]
        elif "VELP" in pvars:
            velocities = pvars["VELP"]

    # Intersection + trim filtering (G3/E2)
    positions, _sel = _filter_intersections(positions, obj)
    positions = _filter_by_trim(positions, velocities, obj)
    if positions.shape[0] == 0:
        return {}

    points = vtk.vtkPoints()
    points.SetData(_vns.numpy_to_vtk(
        np.ascontiguousarray(positions, dtype=np.float64), deep=True))

    polydata = vtk.vtkPolyData()
    polydata.SetPoints(points)

    # Point id scalars: index 0..N-1 (used for "Display particle No."-style
    # scalar colouring and as a default scalar for glyph scaling)
    ids = np.arange(positions.shape[0], dtype=np.float64)
    id_arr = _vns.numpy_to_vtk(ids, deep=True)
    id_arr.SetName("PointId")
    polydata.GetPointData().AddArray(id_arr)

    # Scalar attribute (per-particle value, if a field is available)
    scalar_arr = _attach_scalar(pvars, obj)
    if scalar_arr is not None:
        polydata.GetPointData().SetScalars(scalar_arr)

    actors: dict[str, vtk.vtkActor] = {}

    # Particle points / spheres
    if obj.particle_type in ("Sphere", "Actual"):
        actor = _sphere_actor(polydata, obj)
    else:
        actor = _points_actor(polydata, obj)
    if actor is not None:
        actors["particle"] = actor

    # Vector glyphs
    if velocities is not None:
        vec = _vns.numpy_to_vtk(
            np.ascontiguousarray(velocities, dtype=np.float64), deep=True)
        vec.SetName("Velocity")
        polydata.GetPointData().SetVectors(vec)
        glyph = _glyph_actor(polydata, obj)
        if glyph is not None:
            actors["vector"] = glyph

    # Cloth / String (G3): connect particles in index order
    if getattr(obj, "special_cloth", False):
        cloth = _cloth_actor(polydata, obj)
        if cloth is not None:
            actors["cloth"] = cloth

    return actors


def _attach_scalar(pvars: dict,
                     obj: Optional[ParticleObject] = None
                     ) -> Optional[vtk.vtkDataArray]:
    """Per-particle scalar from 'obj.scalar_var' (P0.4).

    - explicit variable: magnitude when the name is a particle vector
      base (e.g. VELP), or the single component when it ends in X/Y/Z;
    - no selection: VELP velocity magnitude;
    - otherwise None (falls back to the point-id scalar).
    """
    if not pvars:
        return None
    svar = (getattr(obj, "scalar_var", "") or "").strip()
    arr = None
    if svar:
        if svar in pvars:
            arr = np.linalg.norm(pvars[svar], axis=1)
        else:
            comps = [pvars.get(svar + c) for c in "XYZ"]
            if comps[0] is not None:
                arr = np.asarray(comps[0])[:, 0]
    else:
        base = pvars.get("VELP")
        if base is not None:
            arr = np.linalg.norm(base, axis=1)
    if arr is None:
        return None
    out = _vns.numpy_to_vtk(np.ascontiguousarray(arr, dtype=np.float64),
                           deep=True)
    out.SetName("ParticleScalar")
    return out


def _points_actor(polydata, obj) -> Optional[vtk.vtkActor]:
    actor = vtk.vtkActor()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(polydata)
    mapper.ScalarVisibilityOn()
    mapper.SetScalarModeToUsePointData()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetPointSize(int(max(1, obj.size_px)))
    prop.SetColor(*_rgb(obj.mono_color))
    prop.SetOpacity(0.5 if obj.transparent else 1.0)
    return actor


def _sphere_actor(polydata, obj) -> Optional[vtk.vtkActor]:
    r = max(1e-4, obj.size_px * 1e-3)
    sphere = vtk.vtkSphereSource()
    sphere.SetThetaResolution(12)
    sphere.SetPhiResolution(12)
    g = vtk.vtkGlyph3D()
    g.SetInputData(polydata)
    g.SetSourceConnection(sphere.GetOutputPort())
    g.SetScaleFactor(r)
    g.ScalingOff()
    g.SetVectorModeToUseNormal()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(g.GetOutputPort())
    mapper.ScalarVisibilityOn()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*_rgb(obj.mono_color))
    prop.SetOpacity(0.5 if obj.transparent else 1.0)
    return actor


def _glyph_actor(polydata, obj) -> Optional[vtk.vtkActor]:
    arrow = vtk.vtkArrowSource()
    g = vtk.vtkGlyph3D()
    g.SetInputData(polydata)
    g.SetSourceConnection(arrow.GetOutputPort())
    g.SetScaleFactor(_glyph_scale(polydata))
    g.SetVectorModeToUseVector()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(g.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(0.1, 0.1, 0.1)
    return actor


def _glyph_scale(polydata) -> float:
    vec = polydata.GetPointData().GetVectors()
    if vec is None:
        return 1.0
    # Bounds-based: scale so longest vector is ~3% of the model diagonal
    pts = polydata.GetPoints()
    if pts is None or pts.GetNumberOfPoints() < 2:
        return 1.0
    b = pts.GetBounds()
    diag = np.sqrt((b[1] - b[0]) ** 2 + (b[3] - b[2]) ** 2 + (b[5] - b[4]) ** 2)
    mags = np.linalg.norm(
        _vns.vtk_to_numpy(vec), axis=1) if vec.GetNumberOfTuples() else np.array([1.0])
    peak = float(mags.max()) if mags.size else 1.0
    if peak <= 0:
        return 1.0
    return 0.03 * diag / peak


def _rgb(color) -> tuple[float, float, float]:
    try:
        return (float(color[0]), float(color[1]), float(color[2]))
    except (TypeError, IndexError):
        return (1.0, 0.0, 1.0)
def _cloth_actor(polydata, obj):
    """Polyline connecting particles in index order (Cloth/String, G3)."""
    pts = polydata.GetPoints()
    if pts is None or pts.GetNumberOfPoints() < 2:
        return None
    line = vtk.vtkPolyLine()
    n = pts.GetNumberOfPoints()
    line.GetPointIds().SetNumberOfIds(n)
    for i in range(n):
        line.GetPointIds().SetId(i, i)
    cells = vtk.vtkCellArray();
    cells.InsertNextCell(line)
    pd = vtk.vtkPolyData();
    pd.SetPoints(pts);
    pd.SetLines(cells)
    actor = vtk.vtkActor();
    mapper = vtk.vtkPolyDataMapper();
    mapper.SetInputData(pd);
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    try:
        prop.SetColor(*_rgb(obj.mono_color))
    except (TypeError, IndexError):
        prop.SetColor(0.3, 0.3, 0.6)
    prop.SetLineWidth(max(1, int(getattr(obj, "size_px", 1) or 1)))
    if getattr(obj, "transparent", False):
        prop.SetOpacity(0.5)
    return actor


def _filter_intersections(positions, obj):
    """Keep only particles inside any intersection region (G3).

    Regions are (min, max) coordinate pairs; an empty region list or
    show_intersection_regions=False keeps every particle.
    """
    regions = list(getattr(obj, "intersection_regions", None) or [])
    if not regions or not getattr(obj, "show_intersection_regions", False):
        return positions, None
    keep = np.zeros(len(positions), dtype=bool)
    for lo, hi in regions:
        lo = np.asarray(lo, dtype=np.float64)
        hi = np.asarray(hi, dtype=np.float64)
        inside = (np.all(positions >= lo, axis=1)
                  & np.all(positions <= hi, axis=1))
        keep |= inside
    return positions[keep], keep


def _parse_range(text):
    """Parse 'a-b' / 'a,b,c' / 'a' into a set of ints (E2)."""
    out = set()
    for part in str(text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                lo, hi = part.split("-", 1)
                out.update(range(int(lo), int(hi) + 1))
            except ValueError:
                continue
        else:
            try:
                out.add(int(part))
            except ValueError:
                continue
    return out


def _filter_by_trim(positions, velocities, obj):
    """Particle Trim tab: number / size range filtering (E2)."""
    n = len(positions)
    keep = np.ones(n, dtype=bool)
    nums = _parse_range(getattr(obj, "display_particle_no", ""))
    if nums:
        keep &= np.array([i in nums for i in range(n)], dtype=bool)
    sizes = _parse_range(getattr(obj, "display_particle_size", ""))
    if sizes and velocities is not None and velocities.shape[0] == n:
        mag = np.linalg.norm(velocities, axis=1)
        keep &= np.array([int(round(m)) in sizes for m in mag], dtype=bool)
    return positions[keep]

