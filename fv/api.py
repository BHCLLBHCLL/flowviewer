"""flowviewer Python API (P3.3) — thin facade over the model/render layers.

Designed for scripts: open a file, build objects, render to PNG, export.
The same calls the GUI uses, minus the Qt chrome.
"""

from __future__ import annotations

from typing import Optional


def open_file(path: str):
    """Load a field file (FLD/FPH/GPH/CGNS) -> FieldFile."""
    from .model.dataset import load_file
    return load_file(path)


def create_object(ff, kind: str = "surface", **kw):
    """Create a PostObject (surface/plane/... ) with keyword overrides."""
    from .model import objects as om
    makers = {
        "surface": om.SurfaceObject,
        "plane": om.PlaneObject,
        "particle": om.ParticleObject,
        "isosurface": om.IsosurfaceObject,
        "point": om.PointObject,
        "streamline": om.StreamlineObject,
        "volume": om.VolumeObject,
        "colorbar": om.ColorbarObject,
        "cylinder": om.CylinderObject,
        "circle": om.CircleObject,
        "pathline": om.PathlineObject,
        "text": om.TextObject,
        "bitmap": om.BitmapObject,
        "information": om.InformationObject,
        "mirror": om.MirrorCopyObject,
        "grouping": om.GroupingObject,
        "graph": om.GraphObject,
        "timeseries": om.TimeSeriesObject,
        "maxmin": om.MaxMinObject,
        "curve": om.CurveObject,
        "periodical": om.PeriodicalCopyObject,
        "bar": om.BarObject,
        "regionbc": om.RegionBCObject,
        "gradation": om.GradationObject,
        "camera": om.CameraObject,
        "region": om.RegionObject,
        "turbo": om.TurboObject,
        "ufo": om.UFOObject,
        "folder": om.FolderObject,
        "light": om.LightObject,
        "measure": om.MeasureObject,
    }
    maker = makers.get(kind)
    if maker is None:
        raise ValueError(f"unknown object kind: {kind!r}")
    return maker(index=1, **kw)


def build_scene(ff, objects=None, enable_3d: bool = True):
    """Scene with the given objects under a Main node (or defaults)."""
    from .model.objects import MainObject
    from .render.scene import Scene
    main = MainObject.from_field_file(ff, magic=objects is None)
    if objects:
        main.children = list(objects)
    sc = Scene(enable_3d=enable_3d)
    sc.build(ff, main=main)
    return sc, main


def render_png(ff, filename: str, objects=None) -> bool:
    """Headless-friendly scene render to PNG (returns False headless)."""
    from .render.export import snapshot_png
    sc, _ = build_scene(ff, objects=objects)
    return snapshot_png(sc.renderer, filename)


def export_stl(ff, filename: str, surface=None) -> bool:
    """Export the boundary surface (or a SurfaceObject) as STL."""
    from .render.export import export_surface_stl
    return export_surface_stl(ff, filename, obj=surface)


def register_variable(ff, name: str, expr: str):
    """Register a derived variable (see fv.model.varreg)."""
    from .model.varreg import register_variable
    return register_variable(ff, name, expr)


def variables(ff) -> list:
    """Sorted variable names of a FieldFile."""
    return sorted(ff.variables)



def regions(ff) -> list:
    """Boundary region names of a FieldFile."""
    return [r.name for r in ff.boundary_regions()]


def materials(ff):
    """Per-cell material id array (FLD only; None for FPH)."""
    return getattr(ff, "material", None)


def cell_centers(ff):
    """Cell centre coordinates as an (n_cells, 3) array."""
    import numpy as np
    if ff.kind == "fph" and ff.link_data is not None:
        ld = ff.link_data
        face_nodes = np.asarray(ld["face_nodes"], dtype=np.int64)
        face_offsets = np.asarray(ld["face_offsets"], dtype=np.int64)
        verts = np.asarray(ff.vertices, dtype=np.float64)
        out = np.zeros((ff.n_cells, 3))
        for c, pf in ld["cell_owner_faces"].items():
            pts = []
            for fi in pf:
                lo, hi = int(face_offsets[fi]), int(face_offsets[fi + 1])
                pts.extend(face_nodes[lo:hi].tolist())
            if pts and 0 <= c < ff.n_cells:
                out[c] = verts[pts].mean(axis=0)
        return out
    if ff.cell_conn is not None and ff.vertices is not None:
        conn = np.asarray(ff.cell_conn, dtype=np.int64)
        verts = np.asarray(ff.vertices, dtype=np.float64)
        return verts[conn].mean(axis=1)
    return None


def adjacent_cells(ff, cell_id: int) -> list:
    """Neighbouring cell ids sharing a face (FPH; [] for FLD)."""
    import numpy as np
    if ff.kind != "fph" or ff.link_data is None:
        return []
    ld = ff.link_data
    owner = np.asarray(ld["owner"], dtype=np.int64)
    neighbour = np.asarray(ld["neighbour"], dtype=np.int64)
    out = []
    for fi in range(len(owner)):
        if int(owner[fi]) == cell_id and int(neighbour[fi]) >= 0:
            out.append(int(neighbour[fi]))
        if int(neighbour[fi]) == cell_id and int(owner[fi]) >= 0:
            out.append(int(owner[fi]))
    return sorted(set(out))

def cycles(ff) -> int:
    """Cycle id of a FieldFile (0 when absent)."""
    return ff.cycle if ff.cycle is not None else 0

# ── turbomachinery / blade post-processing (script facade) ─────────────

def turbo_circumferential_average(ff, var: str, axis: str = "Z",
                                  n_r: int = 64, n_z: int = 64):
    """Circumferential (theta) average of *var* onto (r, z) (r, z, values)."""
    from .render.turbo import circumferential_average as _f
    return _f(ff, var, axis, n_r, n_z)


def turbo_circumferential_mass_average(ff, var: str, axis: str = "Z",
                                       n_r: int = 64, n_z: int = 64):
    """Circumferential mass-flow-weighted (rho |V|) average onto (r, z)."""
    from .render.turbo import circumferential_mass_average as _f
    return _f(ff, var, axis, n_r, n_z)


def turbo_blade_loading_curve(ff, var: str, axis: str = "Z",
                             n_span: int = 32):
    """Blade loading curve: pressure-side minus suction-side vs span."""
    from .render.turbo import blade_loading_curve as _f
    return _f(ff, var, axis, n_span)


def turbo_polar_view_points(ff, axis: str = "Z"):
    """(r, theta) polar coordinates of all vertices."""
    from .render.turbo import polar_view_points as _f
    return _f(ff, axis)


def turbo_meridional_points(ff, axis: str = "Z"):
    """(r, z) meridional coordinates of all vertices."""
    from .render.turbo import meridional_points as _f
    return _f(ff, axis)


def turbo_blade_to_blade_points(ff, radius: float, axis: str = "Z",
                                tol: float = 0.005):
    """(r*theta, z) blade-to-blade unwrap near *radius*."""
    from .render.turbo import blade_to_blade_points as _f
    return _f(ff, radius, axis, tol)


def turbo_pressure_coefficient(ff, p_ref: float, v_ref: float = 1.0,
                               rho: float = 1.0):
    """Pressure coefficient Cp = (p - p_ref) / (0.5 rho v_ref^2)."""
    from .render.turbo import pressure_coefficient as _f
    return _f(ff, p_ref, v_ref, rho)


def turbo_area_average(ff, var: str, axis: str = "Z", n_bins: int = 64):
    """Average of *var* in bins along the axis (axis_centres, values)."""
    from .render.turbo import area_average as _f
    return _f(ff, var, axis, n_bins)


def turbo_mass_flow_average(ff, var: str, axis: str = "Z"):
    """Mass-flow weighted average of *var* (scalar)."""
    from .render.turbo import mass_flow_average as _f
    return _f(ff, var, axis)


# ── deprecated unprefixed aliases (kept for backwards compatibility) ──

def circumferential_average(ff, var, axis="Z", n_r=64, n_z=64):
    """Deprecated alias of turbo_circumferential_average."""
    return turbo_circumferential_average(ff, var, axis, n_r, n_z)


def circumferential_mass_average(ff, var, axis="Z", n_r=64, n_z=64):
    """Deprecated alias of turbo_circumferential_mass_average."""
    return turbo_circumferential_mass_average(ff, var, axis, n_r, n_z)


def blade_loading_curve(ff, var, axis="Z", n_span=32):
    """Deprecated alias of turbo_blade_loading_curve."""
    return turbo_blade_loading_curve(ff, var, axis, n_span)


def polar_view_points(ff, axis="Z"):
    """Deprecated alias of turbo_polar_view_points."""
    return turbo_polar_view_points(ff, axis)


def meridional_points(ff, axis="Z"):
    """Deprecated alias of turbo_meridional_points."""
    return turbo_meridional_points(ff, axis)


def blade_to_blade_points(ff, radius, axis="Z", tol=0.005):
    """Deprecated alias of turbo_blade_to_blade_points."""
    return turbo_blade_to_blade_points(ff, radius, axis, tol)


def pressure_coefficient(ff, p_ref, v_ref=1.0, rho=1.0):
    """Deprecated alias of turbo_pressure_coefficient."""
    return turbo_pressure_coefficient(ff, p_ref, v_ref, rho)


def area_average(ff, var, axis="Z", n_bins=64):
    """Deprecated alias of turbo_area_average."""
    return turbo_area_average(ff, var, axis, n_bins)


def mass_flow_average(ff, var, axis="Z"):
    """Deprecated alias of turbo_mass_flow_average."""
    return turbo_mass_flow_average(ff, var, axis)

# ── topology queries (scPOST FLD-class accessors, P0.2) ────────────────

def node_count(ff) -> int:
    """Number of vertices (GetNodeCount)."""
    from .model import topology
    return topology.node_count(ff)


def element_count(ff) -> int:
    """Number of cells (GetElementCount)."""
    from .model import topology
    return topology.element_count(ff)


def node_xyz(ff, node_id):
    """(x, y, z) of a vertex (GetNodeXYZ)."""
    from .model import topology
    return topology.node_xyz(ff, node_id)


def nodes_of_element(ff, cell_id) -> list:
    """Vertex ids of a cell (GetNodesOfElement)."""
    from .model import topology
    return topology.nodes_of_element(ff, cell_id)


def node_count_of_element(ff, cell_id) -> int:
    """Number of vertices of a cell (GetNodeCountOfElement)."""
    from .model import topology
    return topology.node_count_of_element(ff, cell_id)


def faces_of_cell(ff, cell_id) -> list:
    """Faces of a cell: FPH face ids / FLD face vertex groups."""
    from .model import topology
    return topology.faces_of_cell(ff, cell_id)


def face_count_of_element(ff, cell_id) -> int:
    """Number of faces of a cell (GetFaceCountOfElement)."""
    from .model import topology
    return topology.face_count_of_element(ff, cell_id)


def face_nodes(ff, face_id) -> list:
    """Vertex ids of a face (GetNodesOfFace)."""
    from .model import topology
    return topology.face_nodes(ff, face_id)


def cells_of_face(ff, face_id):
    """(owner, neighbour) cells sharing a face (GetAdjacentElementOfFace)."""
    from .model import topology
    return topology.cells_of_face(ff, face_id)


def elements_of_region(ff, region_name) -> list:
    """Cell ids in a volume region (GetElementsOfVolumeRegion)."""
    from .model import topology
    return topology.elements_of_region(ff, region_name)


def nodes_of_region(ff, region_name) -> list:
    """Vertex ids used by a volume region (GetNodesOfVolumeRegion)."""
    from .model import topology
    return topology.nodes_of_region(ff, region_name)


def nodes_of_surface_region(ff, region_name) -> list:
    """Vertex ids of a boundary region (GetNodesOfSurfaceRegion)."""
    from .model import topology
    return topology.nodes_of_surface_region(ff, region_name)


def area_of_face(ff, face_id) -> float:
    """Area of a face (GetAreaOfFace)."""
    from .model import topology
    return topology.area_of_face(ff, face_id)


def volume_of_element(ff, cell_id) -> float:
    """Volume of a cell (GetVolumeOfElement)."""
    from .model import topology
    return topology.volume_of_element(ff, cell_id)