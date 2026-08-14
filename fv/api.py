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