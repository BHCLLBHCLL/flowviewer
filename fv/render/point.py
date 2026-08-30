"""Point probe object (scPOST Point) — coordinate → local values.

Renders a small marker at ``obj.position`` and (optionally) probes the
scalar/vector fields at that exact point, labelling the values via a
``vtkTextActor`` overlay actor.
"""

from typing import Optional

try:
    import vtk
    from vtk.util import numpy_support as _vns
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False
    _vns = None

from ..model.dataset import FieldFile


def build_point_actors(ff: FieldFile, obj,
                       ugrid=None, cell_centered=None) -> dict:
    """Point marker + optional value labels → ``{"point", "label"}``."""
    out: dict = {}
    if not _HAS_VTK:
        return out
    pos = tuple(float(v) for v in getattr(obj, "position", (0.0, 0.0, 0.0)))

    pts = vtk.vtkPoints()
    pts.InsertNextPoint(*pos)
    pd = vtk.vtkPolyData()
    pd.SetPoints(pts)

    marker = _marker_actor(pd, obj)
    if marker is not None:
        out["point"] = marker

    probe = _probe(ff, obj, pos, ugrid, cell_centered)
    if probe and getattr(obj, "probe_show_values", True):
        text = "\n".join(_format_lines(probe, pos, obj))
        label = _label_actor(text, obj)
        if label is not None:
            out["label"] = label
    return out


def _probe(ff: FieldFile, obj, pos, ugrid, cell_centered):
    """Probe scalar/vector at ``pos`` → dict with ``scalar``/``vector``.

    For FLD (node-centred grids) ``vtkProbeFilter`` is unsafe on the built
    hexahedra (VTK heap corruption), so a plain nearest-node lookup over the
    numpy arrays is used instead — still exact at nodes.
    """
    scalar_var = getattr(obj, "probe_scalar_var", "") or ""
    vector_var = getattr(obj, "probe_vector_var", "") or ""
    return probe_at(
        ff, pos, scalar_var, vector_var,
        scalar_on=getattr(obj, "probe_scalar", True),
        vector_on=getattr(obj, "probe_vector", False),
        ugrid=ugrid, cell_centered=cell_centered,
    )


def probe_at(ff: FieldFile, point, scalar_var: str = "", vector_var: str = "",
             *, scalar_on: bool = True, vector_on: bool = False,
             ugrid=None, cell_centered=None) -> dict:
    """Generic point probe for explicit variable names (R1.1).

    Shared by Point objects and left-click picking across every object
    kind. Returns ``{"scalar": (name, value), "vector": (name, (x,y,z))}`` —
    keys omitted when disabled or unknown.
    """
    scalar_var = scalar_var or ""
    vector_var = vector_var or ""
    if not scalar_var and not vector_var:
        return {}
    if ff.kind == "fld":
        return _probe_fld(ff, point, scalar_var, vector_var,
                          scalar_on, vector_on)
    return _probe_vtk(ff, point, scalar_var, vector_var,
                      scalar_on, vector_on, ugrid, cell_centered)


def _probe_fld(ff: FieldFile, pos, scalar_var: str, vector_var: str,
               scalar_on: bool, vector_on: bool):
    """Nearest-node lookup on an FLD node-centred field file."""
    import numpy as np
    out: dict = {}
    verts = np.asarray(ff.vertices, dtype=np.float64)
    if verts is None or len(verts) == 0:
        return out
    d = verts - np.asarray(pos, dtype=np.float64)
    node = int(np.argmin(np.einsum("ij,ij->i", d, d)))
    if scalar_var and scalar_on:
        arr = ff.variable_array(scalar_var)
        if arr is not None and node < len(arr):
            out["scalar"] = (scalar_var, float(arr[node]))
    if vector_var and vector_on:
        comps = []
        for suff in ("X", "Y", "Z"):
            arr = ff.variable_array(f"{vector_var}{suff}")
            comps.append(float(arr[node]) if arr is not None and node < len(arr)
                         else 0.0)
        out["vector"] = (vector_var, tuple(comps))
    return out


def _probe_vtk(ff: FieldFile, pos, scalar_var: str, vector_var: str,
               scalar_on: bool, vector_on: bool, ugrid, cell_centered):
    """vtkProbeFilter probe (FPH cell-centred / node-centred)."""
    out: dict = {}
    from .plane import build_ugrid
    if ugrid is None or cell_centered is None:
        ugrid, cell_centered = build_ugrid(ff)
    if ugrid is None:
        return out

    from .plane import attach_scalar, attach_vector
    if scalar_var and scalar_on:
        attach_scalar(ugrid, ff, scalar_var, cell_centered)
    if vector_var and vector_on:
        attach_vector(ugrid, ff, vector_var, cell_centered)

    work = ugrid
    if cell_centered:
        c2p = vtk.vtkCellDataToPointData()
        c2p.SetInputData(ugrid)
        c2p.PassCellDataOn()
        c2p.Update()
        work = c2p.GetOutput()

    pts = vtk.vtkPoints()
    pts.InsertNextPoint(*pos)
    pt_pd = vtk.vtkPolyData()
    pt_pd.SetPoints(pts)
    probe = vtk.vtkProbeFilter()
    probe.SetInputData(pt_pd)
    probe.SetSourceData(work)
    probe.Update()
    pout = probe.GetOutput()

    if scalar_var:
        arr = pout.GetPointData().GetArray(scalar_var)
        if arr is not None:
            out["scalar"] = (scalar_var, float(arr.GetTuple1(0)))
    if vector_var:
        arr = pout.GetPointData().GetArray(vector_var)
        if arr is None:
            arr = pout.GetPointData().GetVectors(vector_var)
        if arr is not None:
            out["vector"] = (vector_var,
                             tuple(float(v) for v in arr.GetTuple3(0)))
    return out


def _marker_actor(pd, obj) -> Optional["vtk.vtkActor"]:
    if not _HAS_VTK:
        return None
    shape = (getattr(obj, "shape", "Sphere") or "Sphere")
    r = max(1e-4, float(getattr(obj, "size", 5.0) or 5.0) * 1e-3)
    if shape == "Cross":
        src = vtk.vtkRegularPolygonSource()
        src.SetNumberOfSides(4)
        src.InnerRadiusOn()
        src.SetRadius(r)
    elif shape == "Plus":
        src = vtk.vtkLineSource()
        src.SetPoints2(0, r, 0)
        src = vtk.vtkLineSource()
    else:
        src = vtk.vtkSphereSource()
        src.SetThetaResolution(12)
        src.SetPhiResolution(12)
        src.SetRadius(r)
    g = vtk.vtkGlyph3D()
    g.SetInputData(pd)
    g.SetSourceConnection(src.GetOutputPort())
    g.SetScaleFactor(1.0)
    g.ScalingOff()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(g.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    try:
        prop.SetColor(*obj.color)
    except (AttributeError, TypeError):
        prop.SetColor(1.0, 0.0, 0.0)
    if getattr(obj, "transparent", False):
        prop.SetOpacity(0.5)
    return actor


def _label_actor(text: str, obj) -> Optional["vtk.vtkActor2D"]:
    ta = vtk.vtkTextActor()
    ta.SetInput(text)
    tp = ta.GetTextProperty()
    tp.SetFontFamilyToCourier()
    tp.SetFontSize(max(9, int(getattr(obj, "font_size", 9) or 9)))
    tp.SetBold(1)
    tp.SetColor(0.0, 0.0, 0.0)
    ta.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
    # R0.7: stagger labels vertically by object index so several Point
    # probes don't overwrite each other at the same corner slot.
    idx = max(1, int(getattr(obj, "index", 1) or 1))
    ta.SetPosition(0.02, 0.84 - ((idx - 1) % 10) * 0.06)
    return ta


def _format_lines(probe: dict, pos: tuple, obj) -> list[str]:
    lines = [f"Point ({pos[0]:.4g}, {pos[1]:.4g}, {pos[2]:.4g})"]
    if "scalar" in probe:
        name, val = probe["scalar"]
        lines.append(f"  {name} = {val:.6g}")
    if "vector" in probe:
        name, (vx, vy, vz) = probe["vector"]
        lines.append(f"  {name} = ({vx:.6g}, {vy:.6g}, {vz:.6g})")
    return lines
