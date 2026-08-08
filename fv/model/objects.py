"""scPOST-style post objects: Main / Surface / Plane / Particle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PostObject:
    """Base for objects that appear under a Main (field file) node."""

    kind: str                          # surface | plane | particle | light | …
    index: int = 1                     # Surface (1) → index 1
    visible: bool = True
    title: str = ""

    @property
    def label(self) -> str:
        base = self.title or self.kind.capitalize()
        return f"{base} ({self.index})"


@dataclass
class SurfaceObject(PostObject):
    """Boundary surface display (scPOST Surface)."""

    kind: str = "surface"
    title: str = "Surface"
    # Region tab
    selected_regions: list[str] = field(default_factory=list)
    region_mode: str = "Standard"      # Original | Standard | Name Tree | Select one
    # MAT tab
    display_mats: list[int] = field(default_factory=list)  # empty = all
    # Volume Region tab
    display_volume_regions: list[str] = field(default_factory=list)
    # Contour tab
    show_contour: bool = True
    contour_var: str = ""
    contour_paint_front: bool = True
    contour_paint_back: bool = True
    contour_transparent: bool = False
    # Vector tab
    show_vector: bool = False
    vector_var: str = ""
    # Mesh tab
    show_mesh: bool = True
    mesh_color: tuple[float, float, float] = (0.1, 0.1, 0.1)
    mesh_front: bool = True
    mesh_back: bool = True
    mesh_thickness: int = 1
    mesh_transparent: bool = False
    # Trim tab
    trim_xmin: bool = False
    trim_xmax: bool = False
    trim_ymin: bool = False
    trim_ymax: bool = False
    trim_zmin: bool = False
    trim_zmax: bool = False
    # Scalar Integration tab
    integrate_scalar: bool = False
    projected_area: bool = False
    # Others / Pick / Font
    font_name: str = "MS Gothic"
    font_size: int = 9
    font_float: float = 100.0


@dataclass
class PlaneObject(PostObject):
    """Cut plane (scPOST Plane) — Coordinate tab defaults."""

    kind: str = "plane"
    title: str = "Plane"
    axis: str = "Z"                    # X | Y | Z | Arbitrary
    coordinate: float = 0.0            # m along axis
    point: tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0)
    show_mesh: bool = True
    color: tuple[float, float, float] = (1.0, 0.4, 0.7)
    # MAT / Volume Region
    display_mats: list[int] = field(default_factory=list)
    display_volume_regions: list[str] = field(default_factory=list)
    # Contour / Vector
    show_contour: bool = True
    contour_var: str = ""
    show_vector: bool = False
    vector_var: str = ""
    # Mesh tab
    boundary_line: bool = True
    boundary_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    boundary_transparent: bool = False
    # Automove tab
    automove_method: str = "Line"      # Line | Sin | Cos | Rotation | Custom Path
    automove_enabled: bool = False
    # Trim tab
    trim_objects: list[str] = field(default_factory=list)


@dataclass
class ParticleObject(PostObject):
    """Particle result display (scPOST Particle)."""

    kind: str = "particle"
    title: str = "Particle"
    # Scalar tab
    show_scalar: bool = False
    scalar_var: str = ""
    show_scalar_value: bool = False
    mono_color: tuple[float, float, float] = (1.0, 0.0, 1.0)
    particle_type: str = "Points"      # Points | Sphere | Specify | Actual
    size_px: float = 7.0
    transparent: bool = False
    # Vector tab
    show_vector: bool = False
    vector_var: str = ""
    show_vector_value: bool = False
    # Intersection tab
    intersection_regions: list[tuple[tuple, tuple]] = field(default_factory=list)
    show_intersection_regions: bool = False
    # Trim tab
    display_particle_no: str = ""
    display_attribute_no: str = ""
    display_particle_size: str = ""
    trim_objects: list[str] = field(default_factory=list)
    # Font / Others / Special
    font_name: str = "MS Gothic"
    font_size: int = 9
    font_float: float = 100.0
    use_model_coord: bool = True
    special_cloth: bool = False
    special_variable_generalization: bool = False


@dataclass
class LightObject(PostObject):
    kind: str = "light"
    title: str = "Light"


@dataclass
class MainObject:
    """One opened field file (Main) with default child objects."""

    path: str
    display_name: str
    cycle: Optional[int] = None
    time: Optional[float] = None
    has_particles: bool = False
    children: list[PostObject] = field(default_factory=list)

    @classmethod
    def from_field_file(cls, ff, *, magic: bool = True) -> "MainObject":
        """Build Main + default Surface(1)/Plane(1)[/Particle(1)] like Magic open."""
        path = str(ff.path)
        display = _short_display_path(path)
        main = cls(
            path=path,
            display_name=display,
            cycle=getattr(ff, "cycle", None),
            time=getattr(ff, "time", None),
            has_particles=bool(getattr(ff, "has_particles", False)),
        )
        if not magic:
            return main

        # Surface (1): select all registered surface regions / MAT boundary
        regions = []
        if ff.surface_regions:
            regions = [n for n, _ in ff.surface_regions]
        elif ff.bc_plan:
            regions = [n for n, _, c in ff.bc_plan if c]
        surf = SurfaceObject(index=1, selected_regions=list(regions))
        main.children.append(surf)

        # Plane (1): mid-span along Z (or longest axis)
        lo, hi, axis, mid = _default_plane(ff)
        plane = PlaneObject(
            index=1,
            axis=axis,
            coordinate=mid,
            point=_point_on_axis(axis, mid),
            normal=_normal_for_axis(axis),
        )
        main.children.append(plane)

        if main.has_particles:
            main.children.append(ParticleObject(index=1))

        return main


def _short_display_path(path: str) -> str:
    """scPOST-like shortened path (``..folder\\file.fph``)."""
    from pathlib import Path
    p = Path(path)
    try:
        rel = p.resolve().relative_to(Path.cwd().resolve())
        parts = rel.parts
        if len(parts) >= 2:
            return str(Path("..") / parts[-2] / parts[-1])
        return str(Path("..") / parts[-1])
    except Exception:
        pass
    parts = p.parts
    if len(parts) >= 2:
        return str(Path("..") / parts[-2] / parts[-1])
    return p.name


def _bounds(ff) -> Optional[tuple[tuple[float, float, float],
                                  tuple[float, float, float]]]:
    import numpy as np
    if ff.vertices is None or len(ff.vertices) == 0:
        return None
    v = np.asarray(ff.vertices, dtype=np.float64)
    return tuple(v.min(axis=0)), tuple(v.max(axis=0))


def _default_plane(ff) -> tuple[float, float, str, float]:
    b = _bounds(ff)
    if b is None:
        return 0.0, 0.0, "Z", 0.0
    lo, hi = b
    spans = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    axis_i = max(range(3), key=lambda i: spans[i])
    axis = "XYZ"[axis_i]
    mid = 0.5 * (lo[axis_i] + hi[axis_i])
    return lo[axis_i], hi[axis_i], axis, mid


def _point_on_axis(axis: str, coord: float) -> tuple[float, float, float]:
    if axis == "X":
        return (coord, 0.0, 0.0)
    if axis == "Y":
        return (0.0, coord, 0.0)
    return (0.0, 0.0, coord)


def _normal_for_axis(axis: str) -> tuple[float, float, float]:
    if axis == "X":
        return (1.0, 0.0, 0.0)
    if axis == "Y":
        return (0.0, 1.0, 0.0)
    return (0.0, 0.0, 1.0)
