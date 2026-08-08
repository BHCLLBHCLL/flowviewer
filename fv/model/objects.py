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
    """Cut plane (scPOST ``CutPlane@pst``) — all tab defaults."""

    kind: str = "plane"
    title: str = "Plane"
    # ── Coordinate tab ────────────────────────────────────────────────
    axis: str = "Z"                    # X | Y | Z | Arbitrary
    coordinate: float = 0.0            # m along axis
    point: tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0)
    arbitrary_enabled: bool = False    # ArbitraryPlaneDefinitionState
    arbitrary_normal_r: float = 1.0    # spherical normal R/T/P
    arbitrary_normal_t: float = 0.0
    arbitrary_normal_p: float = 0.0
    operate_object: bool = False
    # Rotate sub-tab
    rotate_axis: str = "XYZ"           # XYZ | Arb.
    rotate_angle: float = 1.0          # degrees per click
    # Usage Guide sub-tab
    usage_guide: bool = False
    usage_hv: bool = False             # Horz/Vert
    usage_axis: bool = False
    usage_line_paint: bool = False
    usage_color_idx: int = 0
    # Pick sub-tab
    pick_mode: bool = False            # define plane by picking 3 points
    pick_hide: bool = False
    # ── MAT / Volume Region ───────────────────────────────────────────
    display_mats: list[int] = field(default_factory=list)
    display_volume_regions: list[str] = field(default_factory=list)
    # ── Contour tab ───────────────────────────────────────────────────
    show_contour: bool = True
    contour_var: str = ""
    contour_paint: bool = True
    contour_transparent: bool = False
    contour_luster: bool = False
    contour_water: bool = False
    contour_line: bool = False
    contour_line_transparent: bool = False
    contour_broken_line: bool = False
    contour_mono_color: bool = False
    contour_mono_rgb: tuple[float, float, float] = (0.0, 0.0, 0.0)
    contour_value: bool = False
    contour_thickness: int = 1
    # ── Vector tab ────────────────────────────────────────────────────
    show_vector: bool = False
    vector_var: str = ""
    vector_location: str = "Uniform"   # Uniform | Actual | Center | Nodes
    vector_space_u: float = 1.0
    vector_space_v: float = 1.0
    vector_type: str = "Standard"      # Simple | Standard | Triangle | 3D | Animation
    vector_constant_length: bool = False
    vector_transparent: bool = False
    vector_mono_color: bool = False
    vector_mono_rgb: tuple[float, float, float] = (0.0, 0.0, 0.0)
    vector_contour_color: bool = False
    vector_projection: bool = False
    vector_scale_length: float = 1.0
    vector_scale_thickness: float = 1.0
    vector_arrow_angle: float = 1.0
    vector_arrow_size: float = 1.0
    # ── Mesh tab ──────────────────────────────────────────────────────
    show_mesh: bool = True
    mesh_color: tuple[float, float, float] = (0.05, 0.05, 0.08)
    mesh_transparent: bool = False
    mesh_thickness: int = 1
    mesh_paint: bool = False
    mesh_paint_rgb: tuple[float, float, float] = (0.7, 0.7, 0.7)
    mesh_block: bool = False
    mesh_luster: bool = False
    mesh_water: bool = False
    # Boundary
    boundary_line: bool = True
    boundary_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    boundary_transparent: bool = False
    boundary_auto: bool = False
    boundary_broken_line: bool = False
    # Subline
    subline_external: bool = False
    subline_automatic: bool = True
    subline_display_location: bool = False
    # ── Automove tab (CutPlaneAutoMove@pst) ───────────────────────────
    automove_enabled: bool = False
    automove_method: str = "Line"      # Line | Sin | Cos | Rotation | Custom Path
    automove_start_point: tuple = (0.0, 0.0, 0.0)
    automove_start_normal: tuple = (0.0, 0.0, 1.0)
    automove_ref_point: tuple = (1.0, 0.0, 0.0)
    automove_ref_normal: tuple = (0.0, 0.0, 1.0)
    automove_axis_point: tuple = (0.0, 0.0, 0.0)
    automove_axis_dir: tuple = (0.0, 0.0, 1.0)
    automove_loop: bool = False
    automove_standby: bool = False
    automove_frames: int = 10
    automove_angle: float = 90.0       # Rotation only
    automove_offset: float = 0.0       # Rotation only
    # Custom Path
    automove_csv: str = ""
    automove_show_path: bool = False
    automove_path_sync: bool = True    # position at current transient time
    automove_path_distance: float = 0.0
    automove_path_start: float = 0.0
    automove_path_end: float = 1.0
    # ── Trim tab ──────────────────────────────────────────────────────
    trim_objects: list[str] = field(default_factory=list)
    # ── Oil Flow tab (OilFlow@pst) ────────────────────────────────────
    oilflow_display: bool = False
    oilflow_var: str = ""
    oilflow_transparent: bool = False
    oilflow_thickness: float = 1.0
    oilflow_space_u: float = 1.0
    oilflow_space_v: float = 1.0
    oilflow_length: float = 1.0
    oilflow_draw_type: str = "Line"
    oilflow_integration_method: str = "Runge-Kutta"  # Runge-Kutta | Euler
    oilflow_steps: int = 10
    oilflow_accuracy: int = 1
    # ── Clip tab ──────────────────────────────────────────────────────
    clip_enabled: bool = False
    clip_xmin: float = 0.0
    clip_ymin: float = 0.0
    clip_xmax: float = 1.0
    clip_ymax: float = 1.0
    clip_display_region: bool = False
    # ── Pick tab ──────────────────────────────────────────────────────
    pick_scalar: bool = True
    pick_scalar_var: str = ""
    pick_vector: bool = False
    pick_vector_var: str = ""
    pick_ijk: bool = False
    pick_cycle_graph: bool = False
    pick_show_all_vars: bool = False
    pick_show_numbers: bool = False
    pick_color_enabled: bool = False
    pick_shape: str = "Sphere"
    pick_line_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    pick_solid_color: tuple[float, float, float] = (1.0, 1.0, 0.0)
    # ── Scalar / Vector Integration ───────────────────────────────────
    integrate_scalar_enabled: bool = False
    integrate_vector_enabled: bool = False
    integrate_output_file: bool = False
    integrate_output_csv: str = ""
    integrate_include_labels: bool = True
    integrate_beep: bool = False
    integrate_recalc_redraw: bool = False
    # ── Texture tab ───────────────────────────────────────────────────
    texture_enabled: bool = False
    texture_file: str = ""
    texture_method: str = "Plane"
    texture_scale: float = 1.0
    texture_angle: float = 0.0
    texture_pos_u: float = 0.0
    texture_pos_v: float = 0.0
    # ── Font / Others ─────────────────────────────────────────────────
    font_name: str = "MS Gothic"
    font_size: int = 9
    font_float: float = 100.0
    colorbar_contour: str = ""
    colorbar_vector: str = ""
    use_model_coord: bool = True
    no_vector_contour_simultaneous: bool = False
    inter_surface: bool = False
    inter_isosurface: bool = False
    inter_plane: bool = False
    inter_undisplayed: bool = False


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
