"""scPOST-style post objects: Main / Surface / Plane / Particle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional



@dataclass
class GlobalWindow:
    """Global objects container (scPOST Global Window, 5a).

    Holds the process-wide Colorbar / Gradation / Camera / Light objects
    that appear under the tree's "Global Objects" node.
    """

    colorbar: object = None
    gradation: object = None
    camera: object = None
    light: object = None

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
    contour_luster: bool = False               # P1.4 specular highlight
    contour_water: bool = False                # P1.4 wet look
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
    mesh_luster: bool = False                  # P1.4
    mesh_water: bool = False                   # P1.4
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
    limited: bool = False
    limited_size: float = 1.0
    limited_width: float = 1.0      # finite rectangle width  (in-plane u)
    limited_height: float = 1.0     # finite rectangle height (in-plane v)
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
    # Coordinate-range trimming (None = not trimmed on that side)
    trim_xmin: Optional[float] = None
    trim_xmax: Optional[float] = None
    trim_ymin: Optional[float] = None
    trim_ymax: Optional[float] = None
    trim_zmin: Optional[float] = None
    trim_zmax: Optional[float] = None
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
    # Multi-frame animation (P0.5): current particle time frame
    frame_index: int = 0


@dataclass
class IsosurfaceObject(PostObject):
    """Iso-scalar surfaces (scPOST Isosurface)."""

    kind: str = "isosurface"
    title: str = "Isosurface"
    # Contour tab — scalar variable + iso values
    show_contour: bool = True
    contour_var: str = ""
    contour_number: int = 5                    # number of auto levels
    contour_values: list[float] = field(default_factory=list)  # explicit values
    contour_auto: bool = True                  # True → distribute over range
    contour_value: float = 0.0
    contour_transparent: bool = False
    contour_line: bool = False                 # surface mesh lines on iso
    contour_mono_color: bool = False
    contour_mono_rgb: tuple[float, float, float] = (0.8, 0.3, 0.5)
    # Vector tab
    show_vector: bool = False
    vector_var: str = ""
    vector_scale_length: float = 1.0
    vector_space: float = 1.0
    # Font / Others
    font_name: str = "MS Gothic"
    font_size: int = 9
    font_float: float = 100.0
    colorbar: str = ""


@dataclass
class PointObject(PostObject):
    """Probe point (scPOST Point) — coordinate → local scalar/vector values."""

    kind: str = "point"
    title: str = "Point"
    # Coordinate
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # Display
    shape: str = "Sphere"                      # Sphere | Cross | Plus
    size: float = 5.0
    color: tuple[float, float, float] = (1.0, 0.0, 0.0)
    transparent: bool = False
    # Probe tab
    probe_scalar: bool = True
    probe_scalar_var: str = ""
    probe_vector: bool = False
    probe_vector_var: str = ""
    probe_show_values: bool = True
    pick_show_numbers: bool = False
    # Font / Others
    font_name: str = "MS Gothic"
    font_size: int = 9
    font_float: float = 100.0


@dataclass
class StreamlineObject(PostObject):
    """Streamlines seeded from a plane (scPOST Streamline)."""

    kind: str = "streamline"
    title: str = "Streamline"
    # Seed
    seed_center: tuple[float, float, float] = (0.0, 0.0, 0.0)
    seed_normal: tuple[float, float, float] = (0.0, 0.0, 1.0)
    seed_axis: str = "Arbitrary"               # X | Y | Z | Arbitrary
    seed_coordinate: float = 0.0
    seed_density_u: int = 10                   # grid resolution
    seed_density_v: int = 10
    seed_spacing: float = 1.0
    # Direction field
    vector_var: str = ""
    direction: str = "Forward"                 # Forward | Backward | Both
    constant_length: bool = False
    length: float = 1.0
    # Integration
    integration_method: str = "Runge-Kutta"    # Runge-Kutta | Euler
    max_steps: int = 200
    step_size: float = 0.01
    # Display
    draw_type: str = "Line"                    # Line | Triangle | Tube
    color_var: str = ""                        # scalar var to color by
    mono_color: tuple[float, float, float] = (0.2, 0.4, 0.9)
    transparent: bool = False
    thickness: float = 1.0
    # Font
    font_name: str = "MS Gothic"
    font_size: int = 9
    font_float: float = 100.0


@dataclass
class VolumeObject(PostObject):
    """Volume scalar/vector display (scPOST Volume) — optional translucent."""

    kind: str = "volume"
    title: str = "Volume"
    display_mats: list[int] = field(default_factory=list)
    display_volume_regions: list[str] = field(default_factory=list)
    draw_type: str = "Solid"                   # Solid | Transparent | Sampled
    show_scalar: bool = True
    scalar_var: str = ""
    scalar_opacity: float = 1.0
    scalar_mono_color: bool = False
    scalar_mono_rgb: tuple[float, float, float] = (0.6, 0.7, 0.8)
    transparent: bool = False
    show_vector: bool = False
    vector_var: str = ""
    vector_scale_length: float = 1.0
    vector_space: float = 1.0
    sampling: int = 1                          # sampling accuracy
    font_name: str = "MS Gothic"
    font_size: int = 9
    font_float: float = 100.0
    colorbar: str = ""


@dataclass
class LightObject(PostObject):
    """Global light (scPOST Light): brightness / colour / direction.

    Rendered as the scene's first (key) light so the whole Draw Window is
    lit consistently; enabled=False switches it off (P0.3).
    """

    kind: str = "light"
    title: str = "Light"
    enabled: bool = True
    brightness: float = 1.0                 # 0.0 … 2.0 intensity
    color: tuple = (1.0, 1.0, 1.0)          # RGB 0–1
    position: tuple = (1.0, 1.0, 1.0)       # directional light vector















@dataclass
class CameraObject(PostObject):
    """Camera settings / image save (scPOST Camera, 5b)."""

    kind: str = "camera"
    title: str = "Camera"
    position: tuple = (0.0, 0.0, 1.0)
    focal_point: tuple = (0.0, 0.0, 0.0)
    view_up: tuple = (0.0, 1.0, 0.0)
    parallel_projection: bool = True
    keyframes: list = field(default_factory=list)   # [pose, ...] for sequences
    frame_count: int = 24                            # frames per keyframe run

@dataclass
class GradationObject(PostObject):
    """Gradient background (scPOST Gradation/Sky, C1)."""

    kind: str = "gradation"
    title: str = "Gradation"
    enabled: bool = True
    top_color: tuple = (1.0, 1.0, 1.0)
    bottom_color: tuple = (0.92, 0.94, 0.97)


@dataclass
class RegionObject(PostObject):
    """Independent boundary-region display (scPOST Region, 5d)."""

    kind: str = "region"
    title: str = "Region"
    region_name: str = ""
    color: tuple = (0.3, 0.6, 0.9)
    transparent: bool = False



@dataclass
class UFOObject(PostObject):
    """Universal field object (scPOST UFO, 7b) — generic point cloud."""

    kind: str = "ufo"
    title: str = "UFO"
    data: dict = field(default_factory=dict)   # {"points":Nx3, "values":N, "cells":Mx3}
    variable: str = ""                          # colour-by variable at nodes/cells
    mode: str = "points"                        # "points" (scatter) | "surface" (triangles)
    point_size: float = 3.0
    color: tuple = (0.2, 0.2, 0.8)

@dataclass
class TurboObject(PostObject):
    """Turbomachinery meridional / blade-to-blade views (scPOST Turbo, 7a)."""

    kind: str = "turbo"
    title: str = "Turbo"
    view: str = "Meridional"              # Meridional | Blade-to-Blade | Polar
    axis: str = "Z"
    radius: float = 0.05
    tolerance: float = 0.005
    variable: str = ""
    n_r: int = 64                         # heatmap grid resolution (P1.3)
    n_z: int = 64

@dataclass
class RegionBCObject(PostObject):
    """Boundary region names + BC attributes (scPOST RegionBC, A5)."""

    kind: str = "regionbc"
    title: str = "Region BC"
    show_names: bool = False
    font_name: str = "MS Gothic"
    font_size: int = 9

@dataclass
class BarObject(PostObject):
    """Variable distribution along a two-point bar (scPOST Bar, A4)."""

    kind: str = "bar"
    title: str = "Bar"
    point1: tuple = (0.0, 0.0, 0.0)
    point2: tuple = (1.0, 0.0, 0.0)
    variable: str = ""
    samples: int = 32
    color: tuple = (0.2, 0.4, 0.9)
    thickness: int = 2
    font_name: str = "MS Gothic"
    font_size: int = 9

@dataclass
class CurveObject(PostObject):
    """Curve through control points, sampling a variable along it (A1)."""

    kind: str = "curve"
    title: str = "Curve"
    points: list = field(default_factory=list)   # [(x,y,z), ...] control pts
    variable: str = ""
    samples: int = 64
    show_curve: bool = True
    show_values: bool = False
    color: tuple = (0.9, 0.2, 0.2)
    thickness: int = 2
    font_name: str = "MS Gothic"
    font_size: int = 9


@dataclass
class FolderObject(PostObject):
    """Folder grouping objects in the tree (scPOST Folder, A3)."""

    kind: str = "folder"
    title: str = "Folder"
    member_labels: list = field(default_factory=list)

@dataclass
class GroupingObject(PostObject):
    """Group visibility of member objects (scPOST Grouping, P2.5)."""

    kind: str = "grouping"
    title: str = "Grouping"
    member_labels: list = field(default_factory=list)
    subgroups: list = field(default_factory=list)   # nested grouping labels (9)


def grouping_members(grouping, objects_by_label: dict):
    """Recursively resolve a grouping tree into ordered leaf labels (9).

    ``objects_by_label`` maps an object label to its object.  Nested
    groupings (``grouping.subgroups``) are expanded in order, and each
    direct ``member_labels`` entry is appended (deduplicated, first-wins).
    """
    seen = set()
    out = []

    def _walk(g, stack):
        key = getattr(g, "label", None) or id(g)
        if key in stack:
            return
        for sub in getattr(g, "subgroups", []) or []:
            child = objects_by_label.get(sub)
            if child is not None:
                _walk(child, stack | {key})
        for m in getattr(g, "member_labels", []) or []:
            if m not in seen:
                seen.add(m)
                out.append(m)

    _walk(grouping, set())
    return out

@dataclass
class GraphObject(PostObject):
    """1D graph over a variable (scPOST Graph, P2.2)."""

    kind: str = "graph"
    title: str = "Graph"
    variable: str = ""
    x_mode: str = "Index"                # Index | Cycle | Curve
    files: list = field(default_factory=list)
    curve_label: str = ""                  # 6: arc-length X source
    title_text: str = ""

@dataclass
class TimeSeriesObject(PostObject):
    """Cycle/time series imported from a CSV (scPOST Time Series, P2.10)."""

    kind: str = "timeseries"
    title: str = "Time Series"
    file: str = ""
    cycles: list = field(default_factory=list)
    times: list = field(default_factory=list)


@dataclass
class MaxMinObject(PostObject):
    """Max/Min values per variable (scPOST Max and Min, P2.10)."""

    kind: str = "maxmin"
    title: str = "Max and Min"
    file: str = ""
    values: dict = field(default_factory=dict)   # var -> (min, max)


@dataclass
class PeriodicalCopyObject(PostObject):
    """Periodic copies of a surface about an axis (scPOST Periodical Copy, A2)."""

    kind: str = "periodical"
    title: str = "Periodical Copy"
    source_label: str = ""
    source_labels: list = field(default_factory=list)  # multi-source (8)
    axis: str = "Z"
    axis_point: tuple = (0.0, 0.0, 0.0)
    copies: int = 6
    keep_original: bool = True
    color: tuple = (0.4, 0.4, 0.4)
    transparent: bool = False

@dataclass
class MirrorCopyObject(PostObject):
    """Mirrored copy of a surface object (scPOST Mirror Copy, P2.6)."""

    kind: str = "mirror"
    title: str = "Mirror Copy"
    source_label: str = ""
    source_labels: list = field(default_factory=list)  # multi-source (8)
    mirror_plane: str = "YZ"              # YZ | ZX | XY (normal axis X|Y|Z)
    keep_original: bool = True
    color: tuple = (0.4, 0.4, 0.4)
    transparent: bool = False


@dataclass
class MeasureObject(PostObject):
    """Distance / angle measurement (scPOST Measure, C2)."""

    kind: str = "measure"
    title: str = "Measure"
    mode: str = "Distance"                # Distance | Angle
    points: list = field(default_factory=list)   # picked (x,y,z) tuples
    result: str = ""
    compare_label: str = ""               # other Measure to ratio against (9)
    ratio_value: float = 0.0

@dataclass
class InformationObject(PostObject):
    """Probe information at a point (scPOST Information, P2.4)."""

    kind: str = "information"
    title: str = "Information"
    position: tuple = (0.0, 0.0, 0.0)
    show_marker: bool = True
    marker_color: tuple = (1.0, 0.0, 0.0)
    font_name: str = "MS Gothic"
    font_size: int = 9

@dataclass
class TextObject(PostObject):
    """Draw Window text annotation (scPOST Text, P2.3)."""

    kind: str = "text"
    title: str = "Text"
    text: str = "Text"
    position: tuple = (0.1, 0.85)         # normalized display coords
    font_name: str = "MS Gothic"
    font_size: int = 14
    color: tuple = (0.0, 0.0, 0.0)
    background: bool = False


@dataclass
class BitmapObject(PostObject):
    """Bitmap image pasted into the Draw Window (scPOST Bitmap, P2.3)."""

    kind: str = "bitmap"
    title: str = "Bitmap"
    file: str = ""
    position: tuple = (0.05, 0.05)        # normalized display coords
    scale: float = 1.0
    transparent: bool = False
    uv_scale: tuple = (1.0, 1.0)          # texture tiling (u, v) (9)
    uv_offset: tuple = (0.0, 0.0)         # texture offset (u, v) (9)

@dataclass
class CylinderObject(PostObject):
    """Cut-cylinder surface (scPOST Cylinder, P2.1)."""

    kind: str = "cylinder"
    title: str = "Cylinder"
    axis: str = "Z"
    center: tuple = (0.0, 0.0, 0.0)
    radius: float = 0.1
    height: float = 1.0                 # half-height clipped by two planes
    show_contour: bool = True
    contour_var: str = ""
    contour_transparent: bool = False
    contour_mono_color: bool = False
    contour_mono_rgb: tuple = (0.6, 0.7, 0.8)
    contour_luster: bool = False
    contour_water: bool = False
    contour_value: bool = False
    contour_thickness: int = 1
    show_vector: bool = False
    vector_var: str = ""
    vector_scale_length: float = 1.0
    show_mesh: bool = True
    mesh_color: tuple = (0.1, 0.1, 0.1)
    mesh_thickness: int = 1
    mesh_transparent: bool = False
    display_mats: list = field(default_factory=list)
    display_volume_regions: list = field(default_factory=list)
    font_name: str = "MS Gothic"
    font_size: int = 9
    font_float: float = 100.0


@dataclass
class CircleObject(PostObject):
    """Circle on a plane (scPOST Circle, P2.1)."""

    kind: str = "circle"
    title: str = "Circle"
    axis: str = "Z"
    coordinate: float = 0.0
    center: tuple = (0.0, 0.0, 0.0)
    radius: float = 0.1
    show_contour: bool = True
    contour_var: str = ""
    contour_transparent: bool = False
    contour_mono_color: bool = False
    contour_mono_rgb: tuple = (0.6, 0.7, 0.8)
    contour_luster: bool = False
    contour_water: bool = False
    contour_value: bool = False
    contour_thickness: int = 1
    show_vector: bool = False
    vector_var: str = ""
    vector_scale_length: float = 1.0
    show_mesh: bool = True
    mesh_color: tuple = (0.1, 0.1, 0.1)
    mesh_thickness: int = 1
    mesh_transparent: bool = False
    display_mats: list = field(default_factory=list)
    display_volume_regions: list = field(default_factory=list)
    font_name: str = "MS Gothic"
    font_size: int = 9
    font_float: float = 100.0

@dataclass
class PathlineObject(PostObject):
    """Particle pathlines across a cycle sequence (scPOST PCL, P1.5)."""

    kind: str = "pathline"
    title: str = "Pathline"
    files: list = field(default_factory=list)   # cycle paths in time order
    # Seed tab
    seed_axis: str = "Z"
    seed_coordinate: Optional[float] = None
    density_u: int = 8
    density_v: int = 8
    # Direction tab
    vector_var: str = "VEL"
    direction: str = "Forward"                # Forward | Backward
    steps_per_cycle: int = 10
    step_size: float = 0.001                  # integration step (P1.2)
    # Display tab
    color_var: str = ""                       # scalar var to color by (P1.2)
    draw_type: str = "Line"                   # Line | Triangle | Tube
    thickness: float = 1.0
    mono_color: tuple = (0.1, 0.1, 0.8)
    transparent: bool = False
    font_name: str = "MS Gothic"
    font_size: int = 9
    font_float: float = 100.0

@dataclass
class ColorbarObject(PostObject):
    """Global colorbar (scPOST Colorbar) shared across field files."""

    kind: str = "colorbar"
    title: str = "Colorbar"
    gradation: int = 256
    color_map: str = "Rainbow"                 # Rainbow | Gray | Spectrum | Invert
    range_mode: str = "Auto"                   # Auto | Fix
    min: float = 0.0
    max: float = 1.0
    title: str = ""
    show_title: bool = True
    orientation: str = "Horizontal"            # Horizontal | Vertical
    font_name: str = "MS Gothic"
    font_size: int = 9
    font_float: float = 100.0
    visible: bool = True
    position: tuple[float, float] = (0.12, 0.03)


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
