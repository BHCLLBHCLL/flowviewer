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


def cycles(ff) -> int:
    """Cycle id of a FieldFile (0 when absent)."""
    return ff.cycle if ff.cycle is not None else 0