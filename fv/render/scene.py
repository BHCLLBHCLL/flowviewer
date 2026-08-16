"""VTK scene builder: FieldFile → wireframe grid + objects + text overlay."""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..model.dataset import FieldFile

try:
    import vtk
    from vtk.util import numpy_support as _vns
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False
    _vns = None


def _build_ugrid_shared(ff):
    """Volume ugrid (FLD hexahedra or CGNS mixed cells) for wireframes."""
    from .plane import _build_fld_ugrid
    return _build_fld_ugrid(ff), False


class Scene:
    """Holds VTK renderer + actors for one dataset.

    ``enable_3d=False`` disables real rendering (headless tests): actors are
    replaced by a placeholder list and every build call is a no-op that still
    records the actor *names*.
    """

    def __init__(self, enable_3d: bool = True):
        self.enable_3d = enable_3d and _HAS_VTK
        self.renderer = None
        self._layer_actors: dict[str, list] = {}
        self._overlay = None
        self._overlay_text = ""
        self._bounds: Optional[tuple] = None
        self._field_file = None
        self._main = None
        self._actor_object: dict = {}          # vtkActor/Prop → (kind, obj)
        self._pick_callback = None
        self._colorbar_obj = None                # global ColorbarObject (P0.2)
        self._name_actor = None                  # object-name billboard (C3)
        self._light_obj = None                   # global LightObject (P0.3)
        if self.enable_3d:
            self.renderer = vtk.vtkRenderer()
            # Light scPOST Draw Window (near-white)
            self.renderer.SetBackground(1.0, 1.0, 1.0)
            self.renderer.SetBackground2(0.92, 0.94, 0.97)
            self.renderer.GradientBackgroundOn()
            self.renderer.GetActiveCamera().ParallelProjectionOn()

    def reset(self) -> None:
        if self.enable_3d and self.renderer is not None:
            for actors in self._layer_actors.values():
                for a in actors:
                    if isinstance(a, str):
                        continue
                    if getattr(a, "IsA", None) and a.IsA("vtkActor2D"):
                        try:
                            self.renderer.RemoveActor2D(a)
                        except Exception:
                            pass
                    else:
                        self.renderer.RemoveActor(a)
            if self._overlay is not None:
                try:
                    self.renderer.RemoveActor2D(self._overlay)
                except Exception:
                    pass
                self._overlay = None
        self._layer_actors = {}
        self._overlay_text = ""
        self._bounds = None
        self._colorbar_obj = None
        self._light_obj = None

    def add_actor(self, layer: str, actor) -> None:
        if self.enable_3d:
            if isinstance(actor, vtk.vtkActor2D) if _HAS_VTK else False:
                self.renderer.AddActor2D(actor)
            else:
                self.renderer.AddActor(actor)
        self._layer_actors.setdefault(layer, []).append(actor)

    def register_actor_object(self, actor, kind: str, obj) -> None:
        """Associate an actor with its source object (for pick resolution)."""
        self._actor_object[actor] = (kind, obj)

    def remove_object_actors(self, obj) -> None:
        """Remove every actor owned by *obj* (renderer + layer registry).

        Works for both real (3D) and headless (placeholder-string) layers so
        :meth:`apply_to_object` can do a single-object incremental rebuild.
        """
        owned = [a for a, (k, o) in self._actor_object.items() if o is obj]
        for a in owned:
            if self.enable_3d and not isinstance(a, str):
                if getattr(a, "IsA", None) and a.IsA("vtkActor2D"):
                    try:
                        self.renderer.RemoveActor2D(a)
                    except Exception:  # pragma: no cover
                        pass
                else:
                    self.renderer.RemoveActor(a)
            self._actor_object.pop(a, None)
        for layer, actors in list(self._layer_actors.items()):
            kept = [a for a in actors if a not in owned]
            if len(kept) != len(actors):
                self._layer_actors[layer] = kept
            if not kept:
                self._layer_actors.pop(layer, None)

    def build_global_colorbar(self, colorbar_obj, range_=None) -> None:
        """Add the global ``vtkScalarBarActor`` (P2.3) to the scene."""
        self._colorbar_obj = colorbar_obj
        if not self.enable_3d or self.renderer is None:
            return
        from .colorbar import ColorbarRegistry, colorbar_actor
        if range_ is not None:
            ColorbarRegistry.lut().SetRange(float(range_[0]),
                                            max(float(range_[1]),
                                                float(range_[0]) + 1e-12))
            ColorbarRegistry.lut().Build()
        sb = colorbar_actor(colorbar_obj, range_=range_)
        if sb is None:
            return
        self.add_actor("colorbar", sb)
        self.register_actor_object(sb, "colorbar", colorbar_obj)

    def apply_global_colorbar(self, mapper) -> None:
        """Point a scalar mapper at the global colorbar LUT (P0.2).

        Fix-mode ranges are pushed into 'mapper.SetScalarRange' so the
        whole scene honours the global Colorbar; Auto mode shares the LUT
        while keeping each mapper's own range.
        """
        cb = self._colorbar_obj
        if cb is None or mapper is None or not self.enable_3d:
            return
        from .colorbar import apply_to_mapper
        apply_to_mapper(mapper, cb)

    def _apply_global_colorbar_all(self) -> None:
        """Apply the global LUT to every rendered object's mapper."""
        if self._colorbar_obj is None or not self.enable_3d:
            return
        for actors in self._layer_actors.values():
            for a in actors:
                if isinstance(a, str):
                    continue
                mapper = getattr(a, "GetMapper", None)
                if mapper is None:
                    continue
                try:
                    self.apply_global_colorbar(mapper())
                except Exception:  # pragma: no cover - vtk quirks
                    pass

    def move_plane_to_pick(self, x: int, y: int, plane_obj=None) -> bool:
        """P2.7: move a plane so it passes through the picked point.

        Picks the world point under display (x, y) and translates the
        plane's point onto it (normal unchanged); the plane actors are
        rebuilt incrementally.  Returns True when moved.
        """
        pt, _owner = self.pick_actor(x, y)
        if pt is None:
            return False
        if plane_obj is None and self._main is not None:
            for o in getattr(self._main, "children", []) or []:
                if getattr(o, "kind", "") == "plane":
                    plane_obj = o;
                    break
        if plane_obj is None or self._field_file is None:
            return False
        plane_obj.point = tuple(pt)
        self.apply_to_object(self._field_file, plane_obj)
        return True

    def apply_gradation(self, grad_obj) -> None:
        """Set the renderer gradient background from a GradationObject (C1)."""
        self._gradation_obj = grad_obj
        if not self.enable_3d or self.renderer is None:
            return
        if not getattr(grad_obj, "enabled", True):
            self.renderer.GradientBackgroundOff()
            return
        self.renderer.GradientBackgroundOn()
        try:
            self.renderer.SetBackground(*getattr(grad_obj, "top_color", (1.0, 1.0, 1.0)))
            self.renderer.SetBackground2(*getattr(grad_obj, "bottom_color", (0.92, 0.94, 0.97)))
        except (TypeError, IndexError):
            pass

    def show_object_name(self, text: str, position=None) -> None:
        """Show a 3D billboard name label (scPOST ObjectNameDisplay, C3)."""
        self._name_text = text
        if not self.enable_3d or self.renderer is None or not text:
            return
        if self._name_actor is None:
            self._name_actor = vtk.vtkBillboardTextActor3D()
            self._name_actor.GetTextProperty().SetFontSize(12)
            self._name_actor.GetTextProperty().SetColor(0.0, 0.0, 0.0)
            self._name_actor.GetTextProperty().SetBold(1)
            self.renderer.AddActor(self._name_actor)
        self._name_actor.SetInput(text)
        if position is not None:
            self._name_actor.SetPosition(float(position[0]), float(position[1]), float(position[2]))
        else:
            lo, hi = self._bounds or ((0, 0, 0), (1, 1, 1))
            self._name_actor.SetPosition(
                (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)
        if hasattr(self, "_refresh"):
            self._refresh()

    def hide_object_name(self) -> None:
        """Remove the name label (C3)."""
        self._name_text = ""
        if self.enable_3d and self._name_actor is not None:
            try:
                self.renderer.RemoveActor(self._name_actor)
            except Exception:
                pass
            self._name_actor = None

    def apply_light(self, light_obj) -> None:
        """Apply a LightObject onto the renderer's key light (P0.3).

        Uses the first light of the renderer (created on demand) and
        mirrors the scPOST Brightness tab: switch, intensity, colour and
        the directional light vector.
        """
        self._light_obj = light_obj
        if not self.enable_3d or self.renderer is None:
            return
        lights = self.renderer.GetLights()
        if lights.GetNumberOfItems() == 0:
            self.renderer.AddLight(vtk.vtkLight())
        light = lights.GetItemAsObject(0)
        light.SetSwitch(1 if getattr(light_obj, "enabled", True) else 0)
        light.SetIntensity(float(getattr(light_obj, "brightness", 1.0)))
        light.SetColor(*getattr(light_obj, "color", (1.0, 1.0, 1.0)))
        pos = getattr(light_obj, "position", (1.0, 1.0, 1.0))
        light.SetPosition(*pos)
        light.SetFocalPoint(0.0, 0.0, 0.0)
        light.PositionalOff()

    def actor_names(self) -> list[str]:
        return [name for name, actors in self._layer_actors.items() if actors]

    def layer_count(self, layer: str) -> int:
        return len(self._layer_actors.get(layer, []))

    def set_layer_visible(self, layer: str, visible: bool) -> None:
        for a in self._layer_actors.get(layer, []):
            if self.enable_3d and not isinstance(a, str):
                a.SetVisibility(1 if visible else 0)

    def fit(self) -> None:
        if self.enable_3d and self.renderer:
            self.renderer.ResetCamera()

    def pick_actor(self, x: int, y: int):
        """Return ``(world_point, (kind, obj) or None)`` at display (x, y).

        Uses ``vtkPropPicker`` so only visible props are picked; the result
        object is resolved from :meth:`register_actor_object`. Returns
        ``(None, None)`` when nothing is picked.
        """
        if not self.enable_3d or self.renderer is None:
            return None, None
        picker = vtk.vtkPropPicker()
        picker.Pick(x, y, 0, self.renderer)
        prop = picker.GetViewProp()
        owner = self._actor_object.get(prop) if prop is not None else None
        if owner is None:
            return None, None
        return tuple(float(v) for v in picker.GetPickPosition()), owner

    # ── Automove animation driver (P3.10) ────────────────────────────────

    def _remove_layer_prefix(self, prefix: str) -> None:
        """Remove actors whose layer key starts with ``prefix``."""
        stale = [k for k in self._layer_actors if k.startswith(prefix)]
        for k in stale:
            for a in self._layer_actors.pop(k, []):
                if self.enable_3d and not isinstance(a, str):
                    try:
                        self.renderer.RemoveActor(a)
                    except Exception:
                        pass

    def animate(self, t: float, *, fps: int = 0) -> None:
        """Advance automove-enabled Planes and particle frames to ``t``.

        ``t`` is a frame index (0-based); ``fps`` (if > 0) divides it to a
        normalised [0, 1] time via :func:`fv.render.plane.automove_coordinate`
        (which also honours ``automove_loop`` and frame counts). Each moving
        plane's ``point``/``normal`` is updated and its cut-plane actors are
        rebuilt in place. Particle objects advance to the corresponding
        time frame of the multi-frame particle sections (P0.5), looping
        over however many frames the file carries.
        """
        if not _HAS_VTK or self._field_file is None:
            return
        if self._main is None:
            return
        planes = [o for o in getattr(self._main, "children", [])
                  if getattr(o, "kind", "") == "plane"
                  and getattr(o, "automove_enabled", False)]
        particles = [o for o in getattr(self._main, "children", [])
                     if getattr(o, "kind", "") == "particle"]
        if not planes and not particles:
            return
        if planes:
            from .plane import automove_coordinate, build_plane_actors
            for obj in planes:
                point, normal = automove_coordinate(obj, t, frames=fps)
                obj.point = tuple(point)
                obj.normal = tuple(normal)
                self._remove_layer_prefix("plane:")
                actors = build_plane_actors(self._field_file, obj)
                for key, actor in actors.items():
                    self.add_actor(f"plane:{key}", actor)
            self._apply_global_colorbar_all()
        # Particle frames (P0.5): t selects the frame, looping over the
        # file's frames (count recorded by build_particle_actors in meta).
        if particles:
            from .particle import build_particle_actors
            n_frames = int(getattr(self._field_file, "meta", {}).get(
                "particle_frames", 0) or 0)
            for obj in particles:
                if n_frames > 1:
                    obj.frame_index = int(t) % n_frames
                self._remove_layer_prefix("particle:")
                actors = build_particle_actors(
                    obj, self._field_file,
                    frame_index=obj.frame_index if n_frames else None)
                for key, actor in actors.items():
                    self.add_actor(f"particle:{key}", actor)

    # ── overlay (File / Cycle / Time) ─────────────────────────────────────

    def set_overlay(self, file_name: str, cycle=None, time=None) -> None:
        """Top-left Draw Window info matching scPOST."""
        cyc = "—" if cycle is None else str(cycle)
        if time is None:
            tim = "—"
        else:
            tim = f"{time:.6g}"
        text = f"File : {file_name}\nCycle : {cyc}\nTime : {tim}"
        self._overlay_text = text
        if not self.enable_3d or self.renderer is None:
            return
        if self._overlay is None:
            self._overlay = vtk.vtkTextActor()
            tp = self._overlay.GetTextProperty()
            tp.SetFontFamilyToCourier()
            tp.SetFontSize(14)
            tp.SetBold(1)
            tp.SetColor(0.0, 0.0, 0.0)
            tp.SetLineSpacing(1.15)
            self._overlay.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
            self._overlay.SetPosition(0.02, 0.92)
            self.renderer.AddActor2D(self._overlay)
        self._overlay.SetInput(text)

    def overlay_text(self) -> str:
        return self._overlay_text

    # ── builders ───────────────────────────────────────────────────────────

    def build(self, ff: FieldFile, main=None) -> None:
        """Rebuild actors: wireframe grid + default Surface/Plane[/Particle]."""
        self.reset()
        from pathlib import Path
        self.set_overlay(
            Path(ff.path).name,
            getattr(ff, "cycle", None),
            getattr(ff, "time", None),
        )

        if not self.enable_3d:
            self._layer_actors["grid"] = ["wireframe"]
            self._layer_actors["surface"] = ["surface_1"]
            self._layer_actors["plane"] = ["plane_1"]
            for kind in ("isosurface", "point", "streamline", "volume",
                         "colorbar", "light", "pathline", "cylinder", "circle", "text", "bitmap", "information", "mirror", "curve", "periodical", "bar", "gradation", "turbo", "region", "ufo"):
                if any(o.kind == kind for o in
                       getattr(main, "children", []) or []):
                    self._layer_actors[kind] = [f"{kind}_1"]
            if getattr(ff, "has_particles", False) or (
                    main is not None and getattr(main, "has_particles", False)):
                self._layer_actors["particle"] = ["particle_1"]
            self._field_file = ff
            self._main = main
            return

        if ff.poly:
            self._build_fph_wireframe(ff)
        elif ff.kind == "neutral":
            self._build_neutral_wireframe(ff)
        else:
            self._build_fld_wireframe(ff)

        # Default objects (Magic-open style)
        children = list(getattr(main, "children", []) or [])
        if not children:
            from ..model.objects import MainObject
            children = MainObject.from_field_file(ff).children
        for obj in children:
            if not obj.visible:
                continue
            self._dispatch_object(ff, obj)
        self._apply_global_colorbar_all()
        self._field_file = ff
        self._main = main

    def _dispatch_object(self, ff: FieldFile, obj) -> None:
        """Build the actors for one child object (dispatch switch)."""
        if obj.kind == "surface":
            self._add_surface_actors(ff, obj)
        elif obj.kind == "plane":
            self._add_plane_actors(ff, obj)
        elif obj.kind == "particle":
            self._add_particle_actors(ff, obj)
        elif obj.kind == "isosurface":
            self._add_isosurface_actors(ff, obj)
        elif obj.kind == "point":
            self._add_point_actors(ff, obj)
        elif obj.kind == "streamline":
            self._add_streamline_actors(ff, obj)
        elif obj.kind == "volume":
            self._add_volume_actors(ff, obj)
        elif obj.kind == "pathline":
            self._add_pathline_actors(ff, obj)
        elif obj.kind in ("cylinder", "circle"):
            self._add_cut_actors(ff, obj)
        elif obj.kind == "text":
            self._add_text_actor(obj)
        elif obj.kind == "bitmap":
            self._add_bitmap_actor(obj)
        elif obj.kind == "information":
            self._add_information_actor(obj)
        elif obj.kind == "mirror":
            self._add_mirror_actor(ff, obj)
        elif obj.kind == "curve":
            self._add_curve_actor(ff, obj)
        elif obj.kind == "periodical":
            self._add_periodical_actor(ff, obj)
        elif obj.kind == "bar":
            self._add_bar_actor(ff, obj)
        elif obj.kind == "gradation":
            self.apply_gradation(obj)
        elif obj.kind == "colorbar":
            mode = getattr(obj, "range_mode", "Auto") or "Auto"
            rng = (obj.min, obj.max) if str(mode).lower() == "fix" else None
            self.build_global_colorbar(obj, range_=rng)
        elif obj.kind == "light":
            self.apply_light(obj)
        elif obj.kind == "turbo":
            self._add_turbo_actor(ff, obj)
        elif obj.kind == "region":
            self._add_region_actor(ff, obj)
        elif obj.kind == "ufo":
            self._add_ufo_actor(ff, obj)
        # timeseries / maxmin / graph / grouping / measure / folder / regionbc
        # are dialog-only (no scene actors).

    def apply_to_object(self, ff: FieldFile, obj) -> None:
        """Incrementally rebuild a single object without a full scene rebuild.

        Removes *obj*'s existing actors then re-dispatchs its pipeline; the
        grid/overlay and sibling objects stay untouched.  Falls back to a full
        rebuild if the object was never rendered.
        """
        if self._field_file is None or self._main is None:
            self.build(ff, main=getattr(ff, "_main", None))
            return
        self.remove_object_actors(obj)
        if getattr(obj, "visible", True):
            self._dispatch_object(ff, obj)
        self._apply_global_colorbar_all()

    def _polydata_boundary(self, ff: FieldFile):
        ld = ff.link_data
        if ld is None or ff.vertices is None:
            return None
        face_nodes = np.asarray(ld["face_nodes"], dtype=np.int64)
        face_offsets = np.asarray(ld["face_offsets"], dtype=np.int64)
        neighbour = np.asarray(ld["neighbour"], dtype=np.int64)
        verts = np.asarray(ff.vertices, dtype=np.float64)
        self._bounds = (
            tuple(verts.min(axis=0).tolist()),
            tuple(verts.max(axis=0).tolist()),
        )

        bnd = np.flatnonzero(neighbour == -1)
        if bnd.size == 0:
            bnd = np.arange(max(0, len(face_offsets) - 1))
        bnd = np.asarray(bnd, dtype=np.int64)

        points = vtk.vtkPoints()
        points.SetData(_vns.numpy_to_vtk(verts, deep=True))
        polys = vtk.vtkCellArray()
        ids = vtk.vtkIdList()
        for fi in bnd:
            lo = int(face_offsets[fi])
            hi = int(face_offsets[fi + 1])
            ids.Reset()
            for vi in face_nodes[lo:hi]:
                ids.InsertNextId(int(vi))
            polys.InsertNextCell(ids)
        pd = vtk.vtkPolyData()
        pd.SetPoints(points)
        pd.SetPolys(polys)
        return pd

    def _build_neutral_wireframe(self, ff: FieldFile) -> None:
        """Neutral surface mesh (OBJ/STL) -> boundary polydata edges (1)."""
        if ff.vertices is None or not ff.faces:
            return
        verts = np.asarray(ff.vertices, dtype=np.float64)
        self._bounds = (tuple(verts.min(axis=0).tolist()),
                        tuple(verts.max(axis=0).tolist()))
        points = vtk.vtkPoints()
        points.SetData(_vns.numpy_to_vtk(verts, deep=True))
        polys = vtk.vtkCellArray()
        ids = vtk.vtkIdList()
        for f in ff.faces:
            ids.Reset()
            for vi in f:
                ids.InsertNextId(int(vi))
            polys.InsertNextCell(ids)
        pd = vtk.vtkPolyData()
        pd.SetPoints(points)
        pd.SetPolys(polys)
        edges = vtk.vtkExtractEdges()
        edges.SetInputData(pd)
        edges.Update()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(edges.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(0.05, 0.05, 0.08)
        prop.SetLineWidth(1.0)
        self.add_actor("grid", actor)

    def _build_fph_wireframe(self, ff: FieldFile) -> None:
        pd = self._polydata_boundary(ff)
        if pd is None:
            return
        # Extract edges for crisp black wireframe (scPOST mesh lines)
        edges = vtk.vtkExtractEdges()
        edges.SetInputData(pd)
        edges.Update()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(edges.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(0.05, 0.05, 0.08)
        prop.SetLineWidth(1.0)
        prop.SetRepresentationToWireframe()
        self.add_actor("grid", actor)

    def _build_fld_wireframe(self, ff: FieldFile) -> None:
        if ff.vertices is None or ff.cell_conn is None:
            return
        verts = np.asarray(ff.vertices, dtype=np.float64)
        conn = np.asarray(ff.cell_conn, dtype=np.int64)
        self._bounds = (
            tuple(verts.min(axis=0).tolist()),
            tuple(verts.max(axis=0).tolist()),
        )
        ugrid, _ = _build_ugrid_shared(ff)
        if ugrid is None:
            return
        edges = vtk.vtkExtractEdges()
        edges.SetInputData(ugrid)
        edges.Update()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(edges.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(0.05, 0.05, 0.08)
        prop.SetLineWidth(1.0)
        self.add_actor("grid", actor)

    def _add_surface_actors(self, ff: FieldFile, obj) -> None:
        """Boundary-surface pipeline: contour / vector / mesh actors from
        :func:`fv.render.surface.build_surface_actors`.
        """
        from . import surface as surface_render
        actors = surface_render.build_surface_actors(ff, obj)
        if not actors:
            # Fallback: share the boundary wireframe already in the grid
            # layer so the Surface stays visible when nothing is enabled.
            self._layer_actors.setdefault("surface", [])
            if self._layer_actors.get("grid"):
                self._layer_actors["surface"] = list(
                    self._layer_actors["grid"])
            return
        for key, actor in actors.items():
            self.add_actor(f"surface:{key}", actor)

    def _add_plane_actors(self, ff: FieldFile, obj) -> None:
        """Cut-plane pipeline: contour / vector / mesh / boundary / subline
        actors from :func:`fv.render.plane.build_plane_actors`, plus a
        semi-transparent base rectangle for orientation.
        """
        from . import plane as plane_render
        siblings = list(getattr(self._main, "children", []) or [])
        actors = plane_render.build_plane_actors(ff, obj, siblings=siblings)
        for key, actor in actors.items():
            self.add_actor(f"plane:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, "plane", obj)
        if "contour" not in actors and self._bounds is not None:
            lo, hi = self._bounds
            axis = (obj.axis or "Z").upper()
            c = float(obj.coordinate)
            src = vtk.vtkPlaneSource()
            if axis == "X":
                src.SetOrigin(c, lo[1], lo[2])
                src.SetPoint1(c, hi[1], lo[2])
                src.SetPoint2(c, lo[1], hi[2])
            elif axis == "Y":
                src.SetOrigin(lo[0], c, lo[2])
                src.SetPoint1(hi[0], c, lo[2])
                src.SetPoint2(lo[0], c, hi[2])
            else:
                src.SetOrigin(lo[0], lo[1], c)
                src.SetPoint1(hi[0], lo[1], c)
                src.SetPoint2(lo[0], hi[1], c)
            src.SetResolution(1, 1)
            src.Update()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(src.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            prop = actor.GetProperty()
            color = getattr(obj, "mesh_color", (0.8, 0.2, 0.5))
            prop.SetColor(*color)
            prop.SetOpacity(0.35)
            prop.EdgeVisibilityOn()
            prop.SetEdgeColor(*color)
            self.add_actor("plane", actor)

    def _add_particle_actors(self, ff, obj) -> None:
        """Build particle actors from the file's particle sections."""
        from .particle import build_particle_actors
        actors = build_particle_actors(obj, ff,
                                       frame_index=getattr(obj, "frame_index", 0))
        if not actors:
            return
        for key, actor in actors.items():
            self.add_actor(f"particle:{key}", actor)
        self._layer_actors.setdefault("particle", ["particle_1"])

    def _add_isosurface_actors(self, ff, obj) -> None:
        """Iso-surface contour / line / vector actors (P2.4)."""
        from . import isosurface as iso_render
        actors = iso_render.build_isosurface_actors(ff, obj)
        for key, actor in actors.items():
            self.add_actor(f"isosurface:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, "isosurface", obj)

    def _add_point_actors(self, ff, obj) -> None:
        """Point probe marker + value label (P2.5)."""
        from . import point as point_render
        actors = point_render.build_point_actors(ff, obj)
        for key, actor in actors.items():
            self.add_actor(f"point:{key}", actor)
            if key == "point" and not isinstance(actor, str):
                self.register_actor_object(actor, "point", obj)

    def _add_streamline_actors(self, ff, obj) -> None:
        """Streamlines seeded from a plane (P2.6)."""
        from . import streamline as sl_render
        actors = sl_render.build_streamline_actors(ff, obj)
        for key, actor in actors.items():
            self.add_actor(f"streamline:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, "streamline", obj)

    def _add_turbo_actor(self, ff, obj) -> None:
        """Turbo 2D view scatter (7a)."""
        from .turbo import build_turbo_actors
        actors = build_turbo_actors(ff, obj)
        for key, actor in actors.items():
            self.add_actor(f"turbo:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, "turbo", obj)

    def _add_region_actor(self, ff, obj) -> None:
        """Independent boundary-region surface (5d)."""
        from .surface import build_surface_polydata
        from ..model.objects import SurfaceObject
        s = SurfaceObject(index=1)
        s.selected_regions = [getattr(obj, "region_name", "")] if getattr(obj, "region_name", "") else []
        pd, cc, _ = build_surface_polydata(ff, s)
        if pd is None or pd.GetNumberOfCells() == 0:
            return
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(pd)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        try:
            actor.GetProperty().SetColor(*getattr(obj, "color", (0.3, 0.6, 0.9)))
        except (TypeError, IndexError):
            actor.GetProperty().SetColor(0.3, 0.6, 0.9)
        if getattr(obj, "transparent", False):
            actor.GetProperty().SetOpacity(0.5)
        self.add_actor("region", actor)
        self.register_actor_object(actor, "region", obj)

    def _add_ufo_actor(self, ff, obj) -> None:
        """UFO generic point-cloud scatter (7b)."""
        from .ufo import build_ufo_actors
        actors = build_ufo_actors(ff, obj)
        for key, actor in actors.items():
            self.add_actor(f"ufo:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, "ufo", obj)

    def _add_bar_actor(self, ff, obj) -> None:
        """Bar line coloured by a sampled variable (A4)."""
        from .bar import build_bar_actors
        actors = build_bar_actors(ff, obj)
        for key, actor in actors.items():
            self.add_actor(f"bar:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, "bar", obj)

    def _add_periodical_actor(self, ff, obj) -> None:
        """Periodic rotated copies of a surface sibling (A2)."""
        from .periodical import build_periodical_actors
        siblings = list(getattr(self._main, "children", []) or [])
        actors = build_periodical_actors(ff, obj, siblings=siblings)
        for key, actor in actors.items():
            self.add_actor(f"periodical:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, "periodical", obj)

    def _add_curve_actor(self, ff, obj) -> None:
        """Curve line coloured by a sampled variable (A1)."""
        from .curve import build_curve_actors
        actors = build_curve_actors(ff, obj)
        for key, actor in actors.items():
            self.add_actor(f"curve:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, "curve", obj)

    def _add_mirror_actor(self, ff, obj) -> None:
        """Mirrored copy of a surface sibling (P2.6)."""
        from .mirror import build_mirror_actors
        siblings = list(getattr(self._main, "children", []) or [])
        actors = build_mirror_actors(ff, obj, siblings=siblings)
        for key, actor in actors.items():
            self.add_actor(f"mirror:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, "mirror", obj)

    def _add_information_actor(self, obj) -> None:
        """Information probe marker (P2.4)."""
        from .information import marker_actor
        a = marker_actor(obj, bounds=self._bounds)
        if a is not None:
            self.add_actor("information", a)
            self.register_actor_object(a, "information", obj)

    def _add_text_actor(self, obj) -> None:
        """Text annotation overlay (P2.3)."""
        from .text import text_actor
        a = text_actor(obj)
        if a is not None:
            self.add_actor("text", a)
            self.register_actor_object(a, "text", obj)

    def _add_bitmap_actor(self, obj) -> None:
        """Bitmap image overlay (P2.3)."""
        from .text import bitmap_actor
        a = bitmap_actor(obj)
        if a is not None:
            self.add_actor("bitmap", a)
            self.register_actor_object(a, "bitmap", obj)

    def _add_cut_actors(self, ff, obj) -> None:
        """Cylinder / Circle cut-surface actors (P2.1)."""
        from .cylinder import build_circle_actors, build_cylinder_actors
        fn = build_cylinder_actors if obj.kind == "cylinder" else \
            build_circle_actors
        actors = fn(ff, obj)
        for key, actor in actors.items():
            self.add_actor(f"{obj.kind}:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, obj.kind, obj)

    def _add_pathline_actors(self, ff, obj) -> None:
        """Pathline actors across the object's cycle files (P1.5)."""
        from .pathline import build_pathline_actors
        files = getattr(obj, "files", None) or []
        actors = build_pathline_actors(obj, list(files), ff0=ff)
        for key, actor in actors.items():
            self.add_actor(f"pathline:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, "pathline", obj)

    def _add_volume_actors(self, ff, obj) -> None:
        """Whole-domain volume scalar/vector actors (P2.7)."""
        from . import volume as vol_render
        actors = vol_render.build_volume_actors(ff, obj)
        for key, actor in actors.items():
            self.add_actor(f"volume:{key}", actor)
            if not isinstance(actor, str):
                self.register_actor_object(actor, "volume", obj)


def numpy_to_vtk_array(arr: np.ndarray, name: str):
    """Convert a 1-D array to a vtkFloatArray for PointData/CellData."""
    fa = _vns.numpy_to_vtk(np.ascontiguousarray(arr, dtype=np.float64), deep=True)
    fa.SetName(name)
    return fa
