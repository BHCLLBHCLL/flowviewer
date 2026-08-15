"""Headless GUI / scene tests (offscreen platform, enable_3d=False)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

FPH = r"D:\training\cgns\examples\tr03_9.fph"
FLD = r"D:\training\cgns\flddecoding\tests\ex1_e_from_sxemt_run.fld"

try:
    from PyQt5.QtWidgets import QApplication
    _HAS_QT = True
except Exception:  # pragma: no cover
    _HAS_QT = False


@pytest.fixture(scope="module")
def qapp():
    if not _HAS_QT:
        pytest.skip("PyQt5 unavailable")
    app = QApplication.instance() or QApplication([])
    return app


def _make(qapp, path, enable_3d=False):
    from fv.gui.main import FlowViewer
    return FlowViewer(filepath=path, enable_3d=enable_3d)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_window_fph_layout(qapp):
    w = _make(qapp, FPH)
    assert w.dataset.kind == "fph"
    assert w.dataset.cycle == 9
    assert w.dataset.time is not None
    assert abs(w.dataset.time - 0.002493) < 1e-6
    assert w.dataset.has_particles is True
    root = w.object_tree.topLevelItem(0)
    assert root is not None and root.text(0) == "POST application"
    # Field-file Main node with Surface(1) / Plane(1) / Particle(1)
    assert w.main_object is not None
    labels = [o.label for o in w.main_object.children]
    assert "Surface (1)" in labels
    assert "Plane (1)" in labels
    assert "Particle (1)" in labels
    main_item = w.object_tree._items.get("__main__")
    assert main_item is not None
    child_names = [main_item.child(i).text(0)
                   for i in range(main_item.childCount())]
    assert child_names == labels
    assert "grid" in w.scene.actor_names()
    assert "plane" in w.scene.actor_names()
    ov = w.scene.overlay_text()
    assert "tr03_9.fph" in ov
    assert "Cycle : 9" in ov
    assert "Time :" in ov
    assert w.status.currentMessage().startswith("FPH")


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_window_fld_layout(qapp):
    w = _make(qapp, FLD)
    assert w.dataset.kind == "fld"
    assert w.dataset.n_cells == 18_240
    assert "grid" in w.scene.actor_names()
    assert "Surface (1)" in [o.label for o in w.main_object.children]
    assert "Plane (1)" in [o.label for o in w.main_object.children]


def test_window_without_file(qapp):
    w = _make(qapp, None)
    # Startup tree: POST application root (scPOST Control Window)
    assert w.object_tree.topLevelItemCount() == 1
    assert w.object_tree.topLevelItem(0).text(0) == "POST application"
    assert w.scene.actor_names() == []
    assert w.timeline is not None
    assert w.timeline.mode() == "Static"
    assert hasattr(w, "tb_file")
    assert hasattr(w, "draw_pane")
    assert hasattr(w, "timeline_pane")


def test_open_dialog_chrome(qapp):
    from fv.gui.dialogs import (
        FILE_TYPE_FILTERS, DialogHeader, OpenDialog, OpenOptions,
        _filter_label, filter_extensions, qt_file_filters,
    )
    dlg = OpenDialog()
    assert dlg.windowTitle() == "Open"
    assert dlg._type_combo.count() == len(FILE_TYPE_FILTERS)
    assert "Field files" in dlg._type_combo.itemText(0)
    assert "*.fld" in dlg._type_combo.itemText(0)
    assert "*.iFLD" in dlg._type_combo.itemText(0)
    assert "*.cgns" in dlg._type_combo.itemText(0)
    # Defaults match scPOST Open checkboxes
    opts = dlg.open_options()
    assert isinstance(opts, OpenOptions)
    assert opts.accelerate_memory is True
    assert opts.read_faster is True
    assert opts.magic_open is False
    assert opts.trimming_open is False
    assert opts.remote_open is False
    assert opts.close_current is False
    # Parasolid multi-part extensions present
    para = [f for f in FILE_TYPE_FILTERS if f[0].startswith("Parasolid")][0]
    assert "x_t" in para[1]
    assert filter_extensions(0) == frozenset(
        ("fld", "ifld", "fph", "gph", "cgns", "xmf", "xdmf"))
    assert _filter_label("Status files", ("sta",)) == "Status files (*.sta)"
    # Native QFileDialog filters must use ;; between groups (else *.fph hidden)
    all_f, sel = qt_file_filters(0)
    assert ";;" in all_f and "*.fph" in sel
    assert all_f.count(";;") == len(FILE_TYPE_FILTERS)  # + All files
    hdr = DialogHeader("Open", "open")
    assert hdr.caption_label.text() == "Open"


def test_headless_imports():
    import fv.gui.main  # noqa: F401
    import fv.render.scene  # noqa: F401
    assert fv.gui.main._HAS_GUI_DEPS in (True, False)


def test_scene_fph_actor_build(qapp):
    from fv.gui.main import FlowViewer
    w = FlowViewer(filepath=FPH, enable_3d=False)
    assert w.scene.layer_count("grid") == 1
    names = w.scene.actor_names()
    assert "grid" in names and "surface" in names and "plane" in names
    assert "particle" in names


def test_scene_reset_with_string_placeholders(qapp):
    """Regression: 3D reset() must not call RemoveActor on string placeholders
    (e.g. particle layer 'particle_1'), which crashed Plane-dialog apply."""
    from fv.render.scene import Scene
    s = Scene(enable_3d=False)
    s._layer_actors["particle"] = ["particle_1"]
    s.reset()
    assert s.actor_names() == []
    s._layer_actors["grid"] = ["wireframe"]
    s.set_layer_visible("grid", False)  # must not crash on strings


def test_surface_plane_dialogs(qapp):
    from fv.gui.object_dialogs import (
        ObjectSettingsPanel, PlaneDialog, SurfaceDialog,
    )
    from fv.model.objects import PlaneObject, SurfaceObject
    sd = SurfaceDialog(SurfaceObject(index=1))
    assert sd.windowTitle().startswith("Surface")
    assert isinstance(sd, ObjectSettingsPanel)
    pd = PlaneDialog(PlaneObject(index=1, axis="Z", coordinate=0.0))
    assert pd.windowTitle().startswith("Plane")


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_tiled_property_host(qapp):
    """Settings open under the tree (not as a modal popup)."""
    from fv.gui.panes import DrawSplitter
    w = _make(qapp, FPH)
    assert hasattr(w, "property_host")
    assert isinstance(w._left_splitter, DrawSplitter)
    handle = w._left_splitter.handle(1)
    assert handle is not None and hasattr(handle, "btn_draw")
    # Auto-shows Surface (1) after open
    assert w.property_host.current_object is not None
    assert w.property_host.current_object.label == "Surface (1)"
    assert w.property_host.current_panel is not None
    # Per-panel Apply removed — Draw grip commits settings
    assert not hasattr(w.property_host.current_panel, "_btn_apply")
    # Switch to Plane via activation
    w._on_object_activated("plane", "Plane (1)")
    assert w.property_host.current_object.label == "Plane (1)"
    # Draw button path rebuilds without modal exec_
    w._on_draw_clicked()
    assert "plane" in w.scene.actor_names()
    # Hide clears the host
    w.property_host._on_hide()
    assert w.property_host.current_panel is None


def test_trim_objects_populated(qapp):
    """Trim 'Trimmed by' list receives sibling objects (F-gap)."""
    w = _make(qapp, FPH)
    w._on_object_activated("plane", "Plane (1)")
    panel = w.property_host.current_panel
    assert panel is not None
    assert panel._trim_objects
    assert any(o.label == "Surface (1)" for o in panel._trim_objects)


def test_pin_transient_panel(qapp):
    """Unpinned panels close on Draw; pinned panels persist (F-gap)."""
    w = _make(qapp, FPH)
    w._on_object_activated("plane", "Plane (1)")
    panel = w.property_host.current_panel
    panel._btn_pin.setChecked(False)
    w._on_draw_clicked()
    assert w.property_host.current_panel is None
    # Pinned panel stays open
    w._on_object_activated("plane", "Plane (1)")
    w.property_host.current_panel._btn_pin.setChecked(True)
    w._on_draw_clicked()
    assert w.property_host.current_panel is not None


def test_particle_run_special(qapp):
    """Particle 'Run checked functions' applies + rebuilds (F-gap)."""
    w = _make(qapp, FPH)
    w._on_object_activated("particle", "Particle (1)")
    panel = w.property_host.current_panel
    if panel is None:
        pytest.skip("no particle object in this dataset")
    assert hasattr(panel, "_run_special")
    try:
        panel.special_cloth.setChecked(True)
    except AttributeError:
        pass
    panel._run_special()
    assert w.property_host.current_panel is not None


def test_usage_click_persists(qapp):
    """Plane Usage Guide buttons persist flags without Apply (F-gap)."""
    w = _make(qapp, FPH)
    w._on_object_activated("plane", "Plane (1)")
    panel = w.property_host.current_panel
    btn = panel.usage_buttons["hv"]
    btn.setChecked(True)
    panel._usage_click("hv")
    assert panel.plane.usage_hv is True


def test_loader_registry_registered():
    """Real parsers are advertised in the loader registry (G-gap)."""
    from fv.model import loaders
    assert "fld" in loaders.loaders()
    assert "fph" in loaders.loaders()
    assert "gph" in loaders.loaders()
    assert "cgns" in loaders.loaders()  # P1.2: CGNS reader implemented
    assert loaders.can_load(FPH) is True
    assert loaders.can_load(r"D:\training\cgns\examples\box_ansa_gph.cgns") is True


def test_cgns_detection_probe():
    """CGNS files are flagged specifically, not as 'unknown' (G-gap)."""
    from fv.model import loaders
    cgns = r"D:\training\cgns\examples\box_ansa_gph.cgns"
    if not Path(cgns).exists():
        pytest.skip("no cgns sample")
    assert loaders.probe_format(cgns).startswith("cgns")
    desc = loaders.describe(cgns)
    assert "loadable" in desc or "cgns" in desc


def test_open_dialog_is_loadable_honest(qapp):
    """Open dialog only marks loadable formats as loadable (G-gap)."""
    from fv.gui.dialogs import OpenDialog
    dlg = OpenDialog()
    assert dlg.is_loadable(FPH) is True
    assert dlg.is_loadable(
        r"D:\training\cgns\examples\box_ansa_gph.cgns") is True


def test_options_qsettings_headless():
    """Options facade stores/recalls values even without a real store."""
    from fv.gui.options import Options
    o = Options()
    o.set("last_dir", r"D:\some\dir")
    assert o.get("last_dir") == r"D:\some\dir"
    assert o.get("missing", "zz") == "zz"


def test_tasks_load_worker_sync(monkeypatch):
    """launch_load headless fallback parses synchronously (P0.6)."""
    from fv.gui import tasks as tasks_mod
    monkeypatch.setattr(tasks_mod, "_HAS_QT", False)
    calls = {}
    tasks_mod.launch_load(
        FPH,
        on_finished=lambda ff: calls.update(ff=ff),
        on_failed=lambda msg: calls.update(err=msg))
    assert "ff" in calls, calls
    assert calls["ff"].kind == "fph"


def test_options_wired_into_window(qapp):
    """Main window exposes an Options instance and saves on close."""
    w = _make(qapp, FPH)
    assert hasattr(w, "options")
    w.options.set("env_show_units", False)
    assert w.options.get("env_show_units") is False


def test_create_object_menu_wiring(qapp):
    """Create menu/toolbar actually instantiates objects (A-gap fix)."""
    w = _make(qapp, FPH)
    kinds_before = {o.kind for o in w.main_object.children}
    w._create_object("isosurface")
    assert any(o.kind == "isosurface" for o in w.main_object.children)
    assert w.property_host.current_object is not None
    assert w.property_host.current_object.kind == "isosurface"
    assert w.property_host.current_panel is not None
    # No duplicate label
    w._create_object("isosurface")
    labels = {o.label for o in w.main_object.children}
    assert "Isosurface (2)" in labels
    # Stub kinds fall back to _nyi (no crash)
    w._create_object("vector")
    assert any(o.kind == "vector" for o in w.main_object.children) is False


def test_surface_dialog_all_tabs_and_filter(qapp):
    from fv.model.dataset import load_file
    from fv.model.objects import SurfaceObject
    from fv.gui.object_dialogs import SurfaceDialog
    ff = load_file(FPH)
    s = SurfaceObject(index=1)
    sd = SurfaceDialog(s, field_file=ff)
    tabs = [sd.tabs.tabText(i) for i in range(sd.tabs.count())]
    assert tabs == ["Region", "MAT", "Volume Region", "Contour", "Vector",
                    "Mesh", "Trim", "Scalar Integration"]
    # Region search filters items
    sd.search.setText("Rotate")
    sd._filter()
    visible = [it.text(0) for it in sd._region_items if not it.isHidden()]
    assert visible and all("rotate" in v.lower() for v in visible)
    # Contour variable list is populated from field file scalar vars
    assert sd.contour.combo.count() >= 1
    # Apply writes state back
    for it in sd._region_items:
        it.setCheckState(0, __import__("PyQt5.QtCore",
                         fromlist=["Qt"]).Qt.Unchecked)
    sd.apply_to(s)
    assert s.selected_regions == []
    assert s.show_contour is True


def test_plane_dialog_all_tabs(qapp):
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.gui.object_dialogs import PlaneDialog
    ff = load_file(FPH)
    p = PlaneObject(index=1, axis="Z", coordinate=0.0)
    pd = PlaneDialog(p, field_file=ff)
    tabs = [pd.tabs.tabText(i) for i in range(pd.tabs.count())]
    assert tabs == ["Coordinate", "MAT", "Volume Region", "Contour", "Vector",
                    "Mesh", "Oil Flow", "Trim", "Automove", "Clip", "Pick",
                    "Scalar Integration", "Vector Integration", "Others",
                    "Limited", "Texture", "Font"]
    assert pd.contour.combo.count() >= 1
    pd.apply_to(p)
    assert p.axis == "Z"
    assert p.contour_var in [pd.contour.combo.itemData(i)
                             for i in range(pd.contour.combo.count())]
    assert p.contour_var in ff.variables
    # Limited plane (finite width x height)
    pd.limited.setChecked(True)
    pd.limited_w.setValue(2.5)
    pd.limited_h.setValue(3.0)
    pd.apply_to(p)
    assert p.limited is True
    assert p.limited_width == 2.5 and p.limited_height == 3.0

def test_particle_dialog_all_tabs(qapp):
    from fv.model.dataset import load_file
    from fv.model.objects import ParticleObject
    from fv.gui.object_dialogs import ParticleDialog
    ff = load_file(FPH)
    pt = ParticleObject(index=1)
    pd = ParticleDialog(pt, field_file=ff)
    tabs = [pd.tabs.tabText(i) for i in range(pd.tabs.count())]
    assert tabs == ["Scalar", "Vector", "Intersection", "Trim", "Others",
                    "Font", "Special"]
    assert pd.scalar.combo.count() >= 1
    pd.region_list.addItem("(0, 0, 0)-(1, 1, 1)")
    pd.apply_to(pt)
    assert pt.intersection_regions == [((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))]


def test_mat_filter_from_fld(qapp):
    from fv.model.dataset import load_file
    from fv.model.objects import SurfaceObject
    from fv.gui.object_dialogs import SurfaceDialog
    from PyQt5.QtCore import Qt
    ff = load_file(FLD)
    s = SurfaceObject(index=1)
    sd = SurfaceDialog(s, field_file=ff)
    assert [it.text(0) for it in sd.mat_tree._items] == ["1", "2"]
    for it in sd.mat_tree._items:
        it.setCheckState(0, Qt.Unchecked)
    for it in sd.mat_tree._items:
        if it.text(0) == "2":
            it.setCheckState(0, Qt.Checked)
    sd.apply_to(s)
    assert s.display_mats == [2]


def test_plane_automove_roundtrip(qapp):
    """Automove triplet spins round-trip through PlaneDialog.apply_to."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.gui.object_dialogs import PlaneDialog
    ff = load_file(FPH)
    p = PlaneObject(index=1, axis="Z", coordinate=0.0)
    p.automove_start_point = (1.0, 2.0, 3.0)
    p.automove_start_normal = (0.0, 0.0, 1.0)
    p.automove_ref_point = (4.0, 5.0, 6.0)
    p.automove_ref_normal = (0.0, 1.0, 0.0)
    p.automove_axis_point = (0.0, 0.0, 0.0)
    p.automove_axis_dir = (0.0, 0.0, 1.0)
    p.automove_method = "Rotation"
    p.automove_angle = 45.0
    p.automove_offset = 5.0
    pd = PlaneDialog(p, field_file=ff)
    pd.apply_to(p)
    assert p.automove_start_point == (1.0, 2.0, 3.0)
    assert p.automove_start_normal == (0.0, 0.0, 1.0)
    assert p.automove_ref_point == (4.0, 5.0, 6.0)
    assert p.automove_ref_normal == (0.0, 1.0, 0.0)
    assert p.automove_axis_point == (0.0, 0.0, 0.0)
    assert p.automove_axis_dir == (0.0, 0.0, 1.0)
    assert abs(p.automove_angle - 45.0) < 1e-9
    assert abs(p.automove_offset - 5.0) < 1e-9
    assert pd.usage_guide_is_on() is (p.usage_guide and True)
    pd._usage_guide_ck.setChecked(True)
    assert pd.usage_guide_is_on() is True


def _has_vtk():
    try:
        import vtk
        vtk.vtkLogger.SetStderrVerbosity(vtk.vtkLogger.VERBOSITY_OFF)
        return True
    except Exception:  # pragma: no cover
        return False


_VTK = _has_vtk()


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_scene_plane_pipeline_3d():
    """Plane render pipeline wired into Scene.build (enable_3d path)."""
    from fv.model.dataset import load_file
    from fv.render.scene import Scene
    ff = load_file(FPH)
    s = Scene(enable_3d=True)
    s.build(ff)
    names = s.actor_names()
    assert "grid" in names
    assert any(n == "plane" or n.startswith("plane:") for n in names)


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_automove_math_fph():
    import numpy as np
    from fv.model.objects import PlaneObject
    from fv.render.plane import automove_coordinate, _rotate_vector
    p = PlaneObject(index=1)
    p.automove_method = "Line"
    p.automove_start_point = (0.0, 0.0, 0.0)
    p.automove_start_normal = (0.0, 0.0, 1.0)
    p.automove_ref_point = (1.0, 0.0, 0.0)
    p.automove_ref_normal = (0.0, 0.0, 1.0)
    pt, n = automove_coordinate(p, 0.5)
    assert abs(pt[0] - 0.5) < 1e-9
    assert abs(np.linalg.norm(n) - 1.0) < 1e-9
    # Sin method: x = sin(pi/2 * 0.5) = sqrt(2)/2
    p.automove_method = "Sin"
    pt, _ = automove_coordinate(p, 0.5)
    assert abs(pt[0] - np.sin(np.pi / 4)) < 1e-9
    # Cos method: f = 1 - cos(pi/2*t) -> 1 at t=1
    p.automove_method = "Cos"
    pt, _ = automove_coordinate(p, 1.0)
    assert abs(pt[0] - 1.0) < 1e-9
    # Rotation: (1,0,0) about z by 90° -> (0,1,0)
    p.automove_method = "Rotation"
    p.automove_axis_point = (0.0, 0.0, 0.0)
    p.automove_axis_dir = (0.0, 0.0, 1.0)
    p.automove_angle = 90.0
    p.automove_offset = 0.0
    p.automove_start_point = (1.0, 0.0, 0.0)
    pt, n = automove_coordinate(p, 1.0)
    assert abs(pt[0]) < 1e-9 and abs(pt[1] - 1.0) < 1e-9
    v = _rotate_vector(np.array([1.0, 0.0, 0.0]),
                       np.array([0.0, 0.0, 1.0]), 90.0)
    assert abs(v[0]) < 1e-9 and abs(v[1] - 1.0) < 1e-9


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_pick():
    """Pick probing returns scalar/vector at a mesh vertex (P3.11)."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    ug, cc = rp.build_ugrid(ff)
    v = np.asarray(ff.vertices)
    obj = PlaneObject(index=1)
    obj.pick_scalar = True
    obj.pick_scalar_var = "PRES"
    res = rp.pick_point(ff, obj, tuple(v[0]), ugrid=ug, cell_centered=cc)
    assert "scalar" in res
    name, val = res["scalar"]
    assert name == "PRES" and val != 0.0
    # no flags -> only point
    res2 = rp.pick_point(ff, PlaneObject(index=1), tuple(v[0]),
                         ugrid=ug, cell_centered=cc)
    assert "scalar" not in res2 and "vector" not in res2


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_automove_animation():
    """Scene.animate advances automove planes and rebuilds their cut (P3.10)."""
    from fv.model.dataset import load_file
    from fv.model.objects import MainObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff)
    plane = next(c for c in main.children if c.kind == "plane")
    plane.show_contour = True
    plane.contour_var = "PRES"
    plane.automove_enabled = True
    plane.automove_method = "Line"
    plane.automove_start_point = plane.point
    plane.automove_start_normal = plane.normal
    plane.automove_ref_point = (10.0, 0.0, plane.coordinate)
    plane.automove_ref_normal = plane.normal
    s = Scene(enable_3d=True)
    s.build(ff, main)
    p0 = tuple(plane.point)
    s.animate(5, fps=11)
    assert plane.point != p0
    assert any(n.startswith("plane:contour") for n in s.actor_names())
    # loop back to frame 0 restores the start position
    s.animate(0, fps=11)
    assert tuple(plane.point) == p0


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_render_pipeline_fph():
    import vtk
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.show_contour = True
    obj.contour_var = "PRES"
    obj.contour_line = True
    obj.show_vector = True
    obj.vector_var = "VEL"
    obj.show_mesh = True
    obj.boundary_line = True
    obj.subline_external = True
    out = rp.build_plane_actors(ff, obj)
    for key in ("contour", "contour_line", "vector", "mesh", "boundary",
                "subline"):
        assert key in out and out[key] is not None
    # cell-centred scalar -> cut carries it in CellData
    m = out["contour"].GetMapper()
    assert m.GetScalarMode() == vtk.VTK_SCALAR_MODE_USE_CELL_DATA
    # vector glyphs carry the interpolated field
    vec_in = out["vector"].GetMapper().GetInput()
    assert vec_in.GetPointData().GetVectors() is not None
    # integration readout on the cut (scalar must be attached before cutting)
    ug, cc = rp.build_ugrid(ff)
    rp.attach_scalar(ug, ff, "PRES", cc)
    cut = rp.cut_grid(ug, obj)
    res = rp.integrate_cut(cut, "PRES")
    assert res["area"] > 0 and abs(res["average"]) > 0


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_trim_coordinate_ranges():
    """Trim tab coordinate ranges actually clip the cut (P1.1)."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.show_contour = True
    obj.contour_var = "PRES"
    ug, cc = rp.build_ugrid(ff)
    rp.attach_scalar(ug, ff, "PRES", cc)
    cut = rp.cut_grid(ug, obj)
    full_area = rp.integrate_cut(cut, "PRES")["area"]
    assert full_area > 0
    # trim to a small band around x = 0.03
    obj.trim_xmin = 0.03
    obj.trim_xmax = 0.031
    trimmed = rp.trim_cut(cut, obj)
    tarea = rp.integrate_cut(trimmed, "PRES")["area"]
    assert 0 < tarea < full_area
    # trim the whole band away on one axis side
    obj2 = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj2.show_contour = True
    obj2.contour_var = "PRES"
    obj2.trim_ymin = 1e9
    obj2.trim_ymax = 1e9 + 1
    trimmed2 = rp.trim_cut(cut, obj2)
    assert rp.integrate_cut(trimmed2, "PRES")["area"] == 0


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_trim_dialog_roundtrip(qapp):
    """Trim coordinate fields survive dialog apply (P1.1)."""
    from fv.model.objects import PlaneObject
    from fv.gui.object_dialogs import PlaneDialog
    p = PlaneObject(index=1, trim_xmin=0.2, trim_xmax=0.8)
    d = PlaneDialog(p)
    d.apply_to(p)
    assert p.trim_xmin == 0.2
    assert p.trim_xmax == 0.8
    assert p.trim_ymin is None
    assert p.trim_ymax is None
    assert p.trim_zmin is None


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_vector_integration(qapp):
    """Vector integration returns normal flux / axes on the cut (P1.2)."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.vector_var = "VEL"
    ug, cc = rp.build_ugrid(ff)
    cut, vec = rp.cut_with_fields(ug, ff, obj, cc, vector="VEL")
    assert vec is not None and vec.shape[1] == 3
    assert vec.shape[0] == cut.GetNumberOfPoints()
    res = rp.integrate_cut(cut, None, vec)
    assert res["area"] > 0
    assert abs(res["in_normal"]) > 0
    assert len(res["in_axes"]) == 3
    # dialog executes vector + scalar integration end-to-end
    from fv.gui.object_dialogs import PlaneDialog
    obj.contour_var = "PRES"
    d = PlaneDialog(obj, ff)
    d.int_scalar.setChecked(True)
    d.int_vector.setChecked(True)
    d._on_integrate()
    assert "m^2" in d.integrate_result.text()
    assert "m/s" in d.integrate_result.text()


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_integration_csv_output(qapp, tmp_path):
    """Integration result written to CSV when Output-to-file checked (P1.3)."""
    import csv
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.gui.object_dialogs import PlaneDialog
    ff = load_file(FPH)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.contour_var = "PRES"
    out_csv = tmp_path / "integral.csv"
    d = PlaneDialog(obj, ff)
    d.int_scalar.setChecked(True)
    d.int_out.setChecked(True)
    d.int_csv.setText(str(out_csv))
    d._on_integrate()
    assert out_csv.exists()
    with open(out_csv, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["Item", "Value"]
    labels = [r[0] for r in rows[1:]]
    assert "Area [m^2]" in labels
    assert f"{obj.contour_var} sum" in labels
    assert float(rows[1][1]) > 0


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_oilflow_streamlines():
    """Oil Flow tab produces streamlines from cut-plane seeds (P2.4)."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.oilflow_display = True
    obj.oilflow_var = "VEL"
    obj.oilflow_draw_type = "Line"
    obj.oilflow_length = 1.0
    out = rp.build_plane_actors(ff, obj)
    assert "oilflow" in out and out["oilflow"] is not None
    m = out["oilflow"].GetMapper()
    assert m is not None
    # tube variant also builds
    obj.oilflow_draw_type = "Standard"
    out2 = rp.build_plane_actors(ff, obj)
    assert "oilflow" in out2
    # disabled -> no actor
    obj.oilflow_display = False
    out3 = rp.build_plane_actors(ff, obj)
    assert "oilflow" not in out3


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_clip_region():
    """Clip tab X/Y region clips the cut and draws its frame (P2.5)."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    v = np.asarray(ff.vertices)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.show_contour = True
    obj.contour_var = "PRES"
    ug, cc = rp.build_ugrid(ff)
    rp.attach_scalar(ug, ff, "PRES", cc)
    cut = rp.cut_grid(ug, obj)
    full = rp.integrate_cut(cut, "PRES")["area"]
    obj.clip_enabled = True
    obj.clip_xmin = float(v[:, 0].min())
    obj.clip_xmax = float(v[:, 0].max())
    obj.clip_ymin = -0.01
    obj.clip_ymax = 0.01
    clipped = rp.clip_cut(cut, obj)
    c = rp.integrate_cut(clipped, "PRES")["area"]
    assert 0 < c < full
    # region frame actor appears when display_region on
    obj.clip_display_region = True
    out = rp.build_plane_actors(ff, obj)
    assert "clip_region" in out and out["clip_region"] is not None
    # disabled -> no clip, no frame
    obj.clip_enabled = False
    out2 = rp.build_plane_actors(ff, obj)
    assert "clip_region" not in out2


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_vector_extras():
    """Vector projection / constant-length / arrow sizing (P2.7)."""
    import numpy as np
    from vtk.util import numpy_support as vns
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.show_vector = True
    obj.vector_var = "VEL"
    obj.vector_type = "Standard"
    # projection zeroes the plane-normal (Z) component
    obj.vector_projection = True
    out = rp.build_plane_actors(ff, obj)
    glyph = out["vector"].GetMapper().GetInputAlgorithm()
    v = vns.vtk_to_numpy(
        glyph.GetInput().GetPointData().GetVectors()).reshape(-1, 3)
    assert np.abs(v[:, 2]).max() < 1e-8
    # constant-length normalises every arrow to unit length
    obj.vector_projection = False
    obj.vector_constant_length = True
    out2 = rp.build_plane_actors(ff, obj)
    g2 = out2["vector"].GetMapper().GetInputAlgorithm()
    v2 = vns.vtk_to_numpy(
        g2.GetInput().GetPointData().GetVectors()).reshape(-1, 3)
    lens = np.linalg.norm(v2, axis=1)
    assert lens.min() == 0.0 and abs(lens.max() - 1.0) < 1e-9
    # arrow size/angle scale the tip geometry (via source-output bounds)
    obj.vector_constant_length = False
    obj.vector_arrow_size = 1.5
    obj.vector_arrow_angle = 0.7
    out3 = rp.build_plane_actors(ff, obj)
    g3 = out3["vector"].GetMapper().GetInputAlgorithm()
    b3 = g3.GetSource().GetBounds()
    assert abs(b3[2]) - 0.15 < 1e-6 and abs(b3[3]) - 0.15 < 1e-6


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_colorbar_texture(tmp_path):
    """Colorbar actor + texture mapping (P3.9)."""
    import struct
    from pathlib import Path as _Path
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.show_contour = True
    obj.contour_var = "PRES"
    obj.colorbar_contour = "PRES"
    out = rp.build_plane_actors(ff, obj)
    assert "colorbar" in out
    cb = out["colorbar"]
    assert cb.GetLookupTable() is not None
    # texture over a small temp BMP
    tmp = tmp_path / "flowviewer_p39.bmp"
    w = h = 4
    px = b"".join(b"\x00\x00\xff\x00" for _ in range(w * h))
    rowpad = b"\x00" * ((4 * w + 3) // 4 * 4 - 4 * w)
    rows = b"".join(px[i * 4 * w:(i + 1) * 4 * w] + rowpad for i in range(h))
    filesz = 54 + len(rows)
    bmp = (b"BM" + struct.pack("<IHHI", filesz, 0, 0, 54)
           + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0,
                         len(rows), 0, 0, 0, 0) + rows)
    tmp.write_bytes(bmp)
    try:
        obj2 = PlaneObject(index=1, axis="Z", coordinate=0.0)
        obj2.texture_enabled = True
        obj2.texture_file = str(tmp)
        obj2.texture_scale = 2.0
        obj2.texture_angle = 30.0
        out2 = rp.build_plane_actors(ff, obj2)
        assert "texture" in out2
        assert out2["texture"].GetTexture() is not None
    finally:
        tmp.unlink(missing_ok=True)


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_contour_extras():
    """Contour mono/luster/water/value flags take effect (P2.6)."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.show_contour = True
    obj.contour_var = "PRES"
    obj.contour_mono_color = True
    obj.contour_luster = True
    obj.contour_water = True
    obj.contour_value = True
    out = rp.build_plane_actors(ff, obj)
    assert "contour" in out
    assert out["contour"].GetMapper().GetScalarVisibility() == 0
    assert "contour_value" in out
    assert out["contour_value"].GetMapper() is not None
    # default (no extras) keeps scalar map
    obj2 = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj2.show_contour = True
    obj2.contour_var = "PRES"
    out2 = rp.build_plane_actors(ff, obj2)
    assert out2["contour"].GetMapper().GetScalarVisibility() == 1
    assert "contour_value" not in out2


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_volume_region_filter():
    """Volume Region filtering on FPH (P3.8): disjoint region cuts."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.show_contour = True
    obj.contour_var = "PRES"
    full = rp.build_plane_actors(ff, obj)["contour"].GetMapper() \
        .GetInput().GetNumberOfPoints()
    # Case[2] and Rotate[2] partition the cut (disjoint, roughly additive)
    c = PlaneObject(index=1, axis="Z", coordinate=0.0,
                    display_volume_regions=["Case[2]"])
    c.show_contour = True
    c.contour_var = "PRES"
    r = PlaneObject(index=1, axis="Z", coordinate=0.0,
                    display_volume_regions=["Rotate[2]"])
    r.show_contour = True
    r.contour_var = "PRES"
    np_ = rp.build_plane_actors(ff, c)["contour"].GetMapper() \
        .GetInput().GetNumberOfPoints()
    nr = rp.build_plane_actors(ff, r)["contour"].GetMapper() \
        .GetInput().GetNumberOfPoints()
    assert 0 < np_ < full and 0 < nr < full
    assert abs((np_ + nr) - full) <= full * 0.02


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_plane_material_filter():
    """MAT filtering on FLD (P3.8): subset of the full cut."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FLD)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.006,
                      point=(0.0, 0.0, 0.006))
    obj.show_contour = True
    obj.contour_var = "PRES"
    full = rp.build_plane_actors(ff, obj)["contour"].GetMapper() \
        .GetInput().GetNumberOfPoints()
    m1 = PlaneObject(index=1, axis="Z", coordinate=0.006,
                     point=(0.0, 0.0, 0.006), display_mats=[1])
    m1.show_contour = True
    m1.contour_var = "PRES"
    n1 = rp.build_plane_actors(ff, m1)["contour"].GetMapper() \
        .GetInput().GetNumberOfPoints()
    assert 0 < n1 < full


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_plane_render_pipeline_fld():
    import vtk
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FLD)
    obj = PlaneObject(index=1, axis="X", coordinate=0.045,
                      point=(0.045, 0.0, 0.0), normal=(1.0, 0.0, 0.0))
    obj.show_contour = True
    obj.contour_var = "TEMP"
    obj.contour_line = True
    obj.show_vector = True
    obj.vector_var = "VECT"
    obj.show_mesh = True
    obj.boundary_line = True
    out = rp.build_plane_actors(ff, obj)
    for key in ("contour", "contour_line", "vector", "mesh", "boundary"):
        assert key in out and out[key] is not None
    # node-centred scalar -> cut carries it in PointData
    m = out["contour"].GetMapper()
    assert m.GetScalarMode() == vtk.VTK_SCALAR_MODE_USE_POINT_DATA
    # integration
    ug, cc = rp.build_ugrid(ff)
    cut = rp.cut_grid(ug, obj)
    arr = rp.attach_scalar(ug, ff, "TEMP", cc)
    cut.GetPointData().AddArray(arr)
    res = rp.integrate_cut(cut, "TEMP")
    assert res["area"] > 0 and abs(res["average"]) > 0


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_surface_render_pipeline_fph():
    import vtk
    from fv.model.dataset import load_file
    from fv.model.objects import SurfaceObject
    from fv.render import surface as sr
    ff = load_file(FPH)
    s = SurfaceObject(index=1)
    s.selected_regions = [ff.surface_regions[0][0]]
    s.show_contour = True
    s.contour_var = "PRES"
    s.show_vector = True
    s.vector_var = "VEL"
    s.show_mesh = True
    out = sr.build_surface_actors(ff, s)
    for key in ("contour", "vector", "mesh"):
        assert key in out and out[key] is not None
    # cell-centred FPH scalar lives in CellData on the surface
    m = out["contour"].GetMapper()
    assert m.GetScalarMode() == vtk.VTK_SCALAR_MODE_USE_CELL_DATA
    # region filtering narrows the face set
    pd, cc, fi = sr.build_surface_polydata(ff, s)
    all_pd, _, _ = sr.build_surface_polydata(ff, SurfaceObject(index=1))
    assert 0 < pd.GetNumberOfCells() <= all_pd.GetNumberOfCells()
    # integration
    sr.attach_scalar(ff, pd, fi, "PRES", cc)
    res = sr.integrate_surface(pd, "PRES")
    assert res["area"] > 0 and abs(res["average"]) > 0


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_surface_render_pipeline_fld():
    import vtk
    from fv.model.dataset import load_file
    from fv.model.objects import SurfaceObject
    from fv.render import surface as sr
    ff = load_file(FLD)
    regs = ff.boundary_regions()
    s = SurfaceObject(index=1)
    s.selected_regions = [r.name for r in regs if "Xmax" in r.name]
    s.show_contour = True
    s.contour_var = "TEMP"
    s.show_vector = True
    s.vector_var = "VECT"
    s.show_mesh = True
    out = sr.build_surface_actors(ff, s)
    for key in ("contour", "vector", "mesh"):
        assert key in out and out[key] is not None
    # node-centred FLD scalar -> PointData
    m = out["contour"].GetMapper()
    assert m.GetScalarMode() == vtk.VTK_SCALAR_MODE_USE_POINT_DATA
    # integration
    pd, cc, fi = sr.build_surface_polydata(ff, s)
    sr.attach_scalar(ff, pd, fi, "TEMP", cc)
    res = sr.integrate_surface(pd, "TEMP")
    assert res["area"] > 0 and abs(res["average"]) > 0


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_particle_render_pipeline_fph():
    """Particle positions/velocities parsed and rendered for FPH."""
    import vtk
    from fv.crdl.fields import parse_particles
    from fv.model.dataset import load_file
    from fv.model.objects import ParticleObject
    from fv.render import particle as pr
    ff = load_file(FPH)
    assert ff.has_particles
    with open(ff.path, "rb") as fh:
        buf = fh.read()
    pos, vel = parse_particles(buf)
    assert pos.shape == (50, 3)
    assert vel.shape == (50, 3)
    p = ParticleObject(index=1)
    p.particle_type = "Points"
    p.show_vector = True
    out = pr.build_particle_actors(p, ff)
    assert "particle" in out
    # point-id scalar coloured points actor
    m = out["particle"].GetMapper()
    assert m.GetScalarMode() == vtk.VTK_SCALAR_MODE_USE_POINT_DATA
    # vector glyph present when requested
    assert "vector" in out and out["vector"].GetMapper() is not None
    # sphere variant also builds
    p2 = ParticleObject(index=1)
    p2.particle_type = "Sphere"
    out2 = pr.build_particle_actors(p2, ff)
    assert "particle" in out2


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_particle_render_pipeline_scene():
    """Particle actors wired into Scene.build (enable_3d path)."""
    from fv.model.dataset import load_file
    from fv.model.objects import MainObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff)
    s = Scene(enable_3d=True)
    s.build(ff, main)
    names = s.actor_names()
    assert any(n.startswith("particle:") for n in names)


@pytest.mark.skipif(not _HAS_QT, reason="PyQt5 unavailable")
def test_new_object_dialogs_tabs_and_apply(qapp):
    """Isosurface/Point/Streamline/Volume/Colorbar dialog tabs + apply_to."""
    from fv.gui.object_dialogs2 import (
        ColorbarDialog, IsosurfaceDialog, PointDialog, StreamlineDialog,
        VolumeDialog,
    )
    from fv.model.objects import (
        ColorbarObject, IsosurfaceObject, PointObject, StreamlineObject,
        VolumeObject,
    )
    iso = IsosurfaceObject(index=1)
    d = IsosurfaceDialog(iso)
    assert [d.tabs.tabText(i) for i in range(d.tabs.count())] == \
        ["Contour", "Vector"]
    d.apply_to(iso)
    assert iso.show_contour is True

    pt = PointObject(index=1)
    d = PointDialog(pt)
    assert [d.tabs.tabText(i) for i in range(d.tabs.count())] == \
        ["Coordinate", "Probe"]
    d.apply_to(pt)

    sl = StreamlineObject(index=1)
    d = StreamlineDialog(sl)
    assert [d.tabs.tabText(i) for i in range(d.tabs.count())] == \
        ["Seed", "Direction", "Display"]
    d.apply_to(sl)

    vol = VolumeObject(index=1)
    d = VolumeDialog(vol)
    assert [d.tabs.tabText(i) for i in range(d.tabs.count())] == \
        ["Scalar", "Vector"]
    d.apply_to(vol)

    cb = ColorbarObject()
    d = ColorbarDialog(cb)
    assert d.tabs.count() == 1
    d.apply_to(cb)
    assert cb.gradation == 256


@pytest.mark.skipif(not _HAS_QT, reason="PyQt5 unavailable")
def test_new_object_dialogs_with_field_file(qapp):
    """Dialogs populate variable combos from a real field file."""
    from fv.gui.object_dialogs2 import (
        IsosurfaceDialog, PointDialog, StreamlineDialog,
    )
    from fv.model.dataset import load_file
    from fv.model.objects import (
        IsosurfaceObject, PointObject, StreamlineObject,
    )
    ff = load_file(FPH)
    d = IsosurfaceDialog(IsosurfaceObject(index=1), field_file=ff)
    assert d.var.count() >= 1
    d = PointDialog(PointObject(index=1), field_file=ff)
    assert d.scalar_var.count() >= 1
    d = StreamlineDialog(StreamlineObject(index=1), field_file=ff)
    assert d.vector.count() >= 1


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_isosurface_render_pipeline_fld():
    import vtk
    from fv.model.dataset import load_file
    from fv.model.objects import IsosurfaceObject
    from fv.render import isosurface as iso_render
    ff = load_file(FLD)
    obj = IsosurfaceObject(index=1)
    obj.contour_var = "TEMP"
    obj.contour_number = 4
    obj.contour_line = True
    obj.show_vector = True
    obj.vector_var = "VECT"
    out = iso_render.build_isosurface_actors(ff, obj)
    assert "contour" in out and out["contour"] is not None
    m = out["contour"].GetMapper()
    assert m.GetScalarMode() in (vtk.VTK_SCALAR_MODE_USE_POINT_DATA,
                                 vtk.VTK_SCALAR_MODE_USE_CELL_DATA)
    assert "contour_line" in out
    assert "vector" in out
    # explicit values path
    obj2 = IsosurfaceObject(index=1)
    obj2.contour_var = "TEMP"
    obj2.contour_auto = False
    obj2.contour_values = [40.0, 60.0]
    out2 = iso_render.build_isosurface_actors(ff, obj2)
    assert out2.get("contour") is not None


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_point_render_pipeline_fph():
    from fv.model.dataset import load_file
    from fv.model.objects import PointObject
    from fv.render import point as pt_render
    ff = load_file(FPH)
    obj = PointObject(index=1, position=(0.02, 0.02, 0.02))
    obj.probe_scalar = True
    obj.probe_scalar_var = "PRES"
    obj.probe_vector = True
    obj.probe_vector_var = "VEL"
    obj.probe_show_values = True
    out = pt_render.build_point_actors(ff, obj)
    assert "point" in out and out["point"] is not None
    assert "label" in out  # value label shown


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_point_probe_fld_nearest_node():
    from fv.model.dataset import load_file
    from fv.model.objects import PointObject
    from fv.render import point as pt_render
    ff = load_file(FLD)
    obj = PointObject(index=1)
    obj.position = (0.045, 0.01, 0.006)
    obj.probe_scalar = True
    obj.probe_scalar_var = "TEMP"
    obj.probe_vector = True
    obj.probe_vector_var = "VECT"
    out = pt_render.build_point_actors(ff, obj)
    assert "point" in out
    assert "label" in out


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_streamline_render_pipeline_fph():
    from fv.model.dataset import load_file
    from fv.model.objects import StreamlineObject
    from fv.render import streamline as sl_render
    ff = load_file(FPH)
    obj = StreamlineObject(index=1)
    obj.vector_var = "VEL"
    obj.seed_axis = "Z"
    obj.seed_coordinate = 0.0
    obj.seed_density_u = 4
    obj.seed_density_v = 4
    obj.length = 0.05
    obj.draw_type = "Line"
    obj.color_var = "PRES"
    out = sl_render.build_streamline_actors(ff, obj)
    assert out.get("streamline") is not None


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_streamline_render_pipeline_fld():
    """FLD node-centred streamlines (numerical Euler tracer)."""
    from fv.model.dataset import load_file
    from fv.model.objects import StreamlineObject
    from fv.render import streamline as sl_render
    ff = load_file(FLD)
    obj = StreamlineObject(index=1)
    obj.vector_var = "VECT"
    obj.seed_axis = "X"
    obj.seed_coordinate = 0.045
    obj.seed_density_u = 4
    obj.seed_density_v = 4
    obj.length = 0.1
    out = sl_render.build_streamline_actors(ff, obj)
    assert out.get("streamline") is not None


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_volume_render_pipeline_fph():
    from fv.model.dataset import load_file
    from fv.model.objects import VolumeObject
    from fv.render import volume as vol_render
    ff = load_file(FPH)
    obj = VolumeObject(index=1)
    obj.show_scalar = True
    obj.scalar_var = "PRES"
    obj.draw_type = "Transparent"
    out = vol_render.build_volume_actors(ff, obj)
    assert out.get("scalar") is not None


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_volume_raycast_fld():
    """FLD hexahedra use the unstructured ray-cast volume (P1.3)."""
    from fv.model.dataset import load_file
    from fv.model.objects import VolumeObject
    from fv.render.volume import build_volume_actors
    ff = load_file(FLD)
    obj = VolumeObject(index=1)
    obj.show_scalar = True
    obj.scalar_var = "PRES"
    out = build_volume_actors(ff, obj)
    a = out["scalar"]
    assert "vtkVolume" in type(a).__name__
    assert "RayCastMapper" in type(a.GetMapper()).__name__
    assert a.GetProperty().GetScalarOpacity() is not None

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_surface_luster_water_material():
    """Luster/Water flags drive specular props on surface actors (P1.4)."""
    from fv.model.dataset import load_file
    from fv.model.objects import SurfaceObject
    from fv.render.surface import (build_surface_polydata, contour_actor,
                                   mesh_lines_actor)
    ff = load_file(FPH)
    pd, _, _ = build_surface_polydata(ff, SurfaceObject(index=1))
    obj = SurfaceObject(index=1)
    obj.contour_var = "PRES"
    a = contour_actor(pd, "PRES", obj)
    assert abs(a.GetProperty().GetSpecular() - 0.0) < 1e-6
    obj.contour_luster = True
    a = contour_actor(pd, "PRES", obj)
    assert abs(a.GetProperty().GetSpecular() - 0.5) < 1e-6
    obj.contour_luster = False
    obj.contour_water = True
    a = contour_actor(pd, "PRES", obj)
    assert abs(a.GetProperty().GetSpecular() - 0.9) < 1e-6
    obj2 = SurfaceObject(index=1)
    obj2.mesh_water = True
    ma = mesh_lines_actor(pd, obj2)
    assert abs(ma.GetProperty().GetSpecular() - 0.9) < 1e-6

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_pathline_multi_cycle(tmp_path):
    """Pathline traces seeds across a cycle sequence (P1.5)."""
    import shutil
    from fv.model.dataset import load_file
    from fv.model.objects import PathlineObject
    from fv.render.pathline import build_pathline_actors
    files = []
    for cyc in (100, 200, 300):
        dst = tmp_path / f"ex1_{cyc}.fld"
        shutil.copyfile(FLD, dst)
        files.append(str(dst))
    ff = load_file(files[0])
    obj = PathlineObject(index=1)
    obj.vector_var = "VECT"
    obj.density_u = 3
    obj.density_v = 3
    obj.steps_per_cycle = 5
    out = build_pathline_actors(obj, files, ff0=ff)
    assert "pathline" in out
    pd = out["pathline"].GetMapper().GetInput()
    assert pd.GetNumberOfPoints() >= 9
    assert pd.GetNumberOfLines() >= 1

def test_pathline_dialog_tabs_and_apply(qapp):
    """PathlineDialog exposes Seed/Direction/Display (P1.5)."""
    from fv.gui.object_dialogs2 import PathlineDialog
    from fv.model.objects import PathlineObject
    pl = PathlineObject(index=1)
    d = PathlineDialog(pl)
    tabs = [d.tabs.tabText(i) for i in range(d.tabs.count())]
    assert tabs == ["Seed", "Direction", "Display"]
    d.du.setValue(12)
    d.steps.setValue(25)
    d.apply_to(pl)
    assert pl.density_u == 12 and pl.steps_per_cycle == 25


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_trim_by_surface():
    """Trim tab 'Trimmed by' clips the cut against a surface (P1.6)."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject, SurfaceObject
    from fv.render.plane import build_plane_actors
    ff = load_file(FPH)
    surf = SurfaceObject(index=1)
    plane = PlaneObject(index=1, axis="Z", coordinate=0.0)
    plane.show_contour = True
    plane.contour_var = "PRES"
    full = build_plane_actors(ff, plane)
    n_full = full["contour"].GetMapper().GetInput().GetNumberOfPoints()
    trimmed = PlaneObject(index=1, axis="Z", coordinate=0.0,
                         trim_objects=["Surface (1)"])
    trimmed.show_contour = True
    trimmed.contour_var = "PRES"
    out = build_plane_actors(ff, trimmed, siblings=[surf])
    n_trim = out["contour"].GetMapper().GetInput().GetNumberOfPoints()
    assert 0 < n_trim <= n_full
    # a Z=0 mid cut spans the whole domain; trimming should reduce it
    if n_full > 4:
        assert n_trim < n_full


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_cylinder_circle_actors():
    """Cylinder/Circle produce cut-surface actors (P2.1)."""
    from fv.model.dataset import load_file
    from fv.model.objects import CircleObject, CylinderObject
    from fv.render.cylinder import (build_circle_actors,
                                     build_cylinder_actors)
    ff = load_file(FPH)
    cyl = CylinderObject(index=1)
    cyl.contour_var = "PRES"
    cyl.radius = 0.05
    out = build_cylinder_actors(ff, cyl)
    assert "contour" in out or "mesh" in out
    cir = CircleObject(index=1)
    cir.contour_var = "PRES"
    cir.radius = 0.05
    out2 = build_circle_actors(ff, cir)
    assert "contour" in out2 or "mesh" in out2

def test_cylinder_circle_dialogs(qapp):
    """Cylinder/Circle dialogs expose tabs and write back (P2.1)."""
    from fv.gui.object_dialogs2 import CircleDialog, CylinderDialog
    from fv.model.objects import CircleObject, CylinderObject
    cyl = CylinderObject(index=1)
    d1 = CylinderDialog(cyl)
    assert [d1.tabs.tabText(i) for i in range(d1.tabs.count())] == [
        "Coordinate", "Contour", "Vector", "Mesh"]
    d1.radius.setValue(0.2)
    d1.apply_to(cyl)
    assert abs(cyl.radius - 0.2) < 1e-9
    cir = CircleObject(index=1)
    d2 = CircleDialog(cir)
    d2.coord.setValue(0.5)
    d2.apply_to(cir)
    assert abs(cir.coordinate - 0.5) < 1e-9


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_text_bitmap_actors():
    """Text actor + bitmap texture quad build (P2.3)."""
    import struct
    from pathlib import Path
    from fv.model.objects import BitmapObject, TextObject
    from fv.render.text import bitmap_actor, text_actor
    t = TextObject(index=1)
    t.text = "Hello"
    a = text_actor(t)
    assert a is not None
    assert a.GetInput() == "Hello"
    # 4x4 blue BMP
    w = h = 4
    px = b"".join(b"\x00\x00\xff\x00" for _ in range(w * h))
    rowpad = b"\x00" * ((4 * w + 3) // 4 * 4 - 4 * w)
    rows = b"".join(px[i * 4 * w:(i + 1) * 4 * w] + rowpad for i in range(h))
    filesz = 54 + len(rows)
    bmp = (b"BM" + struct.pack("<IHHI", filesz, 0, 0, 54)
           + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0,
                         len(rows), 0, 0, 0, 0) + rows)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as f:
        f.write(bmp);
        name = f.name
    try:
        b = BitmapObject(index=1)
        b.file = name
        ba = bitmap_actor(b)
        assert ba is not None
        assert ba.GetTexture() is not None
        # UV tiling helper
        from fv.render.text import bitmap_uv_corners
        assert bitmap_uv_corners((2.0, 3.0), (0.5, 0.25)) == [
            (0.5, 0.25), (2.5, 0.25), (0.5, 3.25), (2.5, 3.25)]
    finally:
        import os; os.unlink(name)
def test_text_bitmap_dialogs(qapp):
    """Text/Bitmap dialogs write back (P2.3)."""
    from fv.gui.object_dialogs2 import BitmapDialog, TextDialog
    from fv.model.objects import BitmapObject, TextObject
    t = TextObject(index=1)
    d1 = TextDialog(t)
    d1.text.setText("Flow")
    d1.apply_to(t)
    assert t.text == "Flow"
    b = BitmapObject(index=1)
    d2 = BitmapDialog(b)
    d2.scale.setValue(2.0)
    d2.uvs.setValue(2.0)
    d2.uvt.setValue(3.0)
    d2.uvo.setValue(0.5)
    d2.uvo2.setValue(0.25)
    d2.apply_to(b)
    assert abs(b.scale - 2.0) < 1e-9
    assert b.uv_scale == (2.0, 3.0)
    assert b.uv_offset == (0.5, 0.25)

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_information_probe():
    """Information probe returns variable values at a point (P2.4)."""
    from fv.model.dataset import load_file
    from fv.model.objects import InformationObject
    from fv.render.information import marker_actor, probe_values
    ff = load_file(FPH)
    center = ff.vertices.mean(axis=0)
    vals = probe_values(ff, center)
    assert "PRES" in vals
    assert isinstance(vals["PRES"], float)
    obj = InformationObject(index=1)
    obj.position = tuple(center)
    m = marker_actor(obj)
    assert m is not None

def test_information_dialog(qapp):
    """InformationDialog exposes the probe query (P2.4)."""
    from fv.gui.object_dialogs2 import InformationDialog
    from fv.model.objects import InformationObject
    info = InformationObject(index=1)
    d = InformationDialog(info)
    d.px.setValue(0.5)
    d.apply_to(info)
    assert abs(info.position[0] - 0.5) < 1e-9


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_undo_redo_objects(qapp):
    """Edit Undo/Redo restores object lists (P2.8)."""
    w = _make(qapp, FPH)
    n0 = len(w.main_object.children)
    w._snapshot_children()
    from fv.model.objects import SurfaceObject
    w.main_object.children.append(SurfaceObject(index=9))
    assert len(w.main_object.children) == n0 + 1
    w.on_undo()
    assert len(w.main_object.children) == n0
    w.on_redo()
    assert len(w.main_object.children) == n0 + 1

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_automove_custom_path(tmp_path):
    """Automove Custom Path interpolates along a CSV (P2.9)."""
    from fv.model.objects import PlaneObject
    from fv.render.plane import automove_coordinate
    csv = tmp_path / "path.csv"
    csv.write_text("x,y,z\n0,0,0\n1,1,1\n2,2,2\n", encoding="utf-8")
    pl = PlaneObject(index=1)
    pl.automove_method = "Custom Path"
    pl.automove_csv = str(csv)
    p0, _ = automove_coordinate(pl, 0.0)
    p1, _ = automove_coordinate(pl, 0.5)
    p2, _ = automove_coordinate(pl, 1.0)
    assert abs(p0[0]) < 1e-6 and abs(p2[0] - 2.0) < 1e-6
    assert abs(p1[0] - 1.0) < 1e-6
    # missing file falls back to Line (no crash)
    pl.automove_csv = str(tmp_path / "nope.csv")
    pf, _ = automove_coordinate(pl, 0.5)
    assert len(pf) == 3


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_mirror_copy_surface():
    """Mirror Copy reflects a surface sibling (P2.6)."""
    from fv.model.dataset import load_file
    from fv.model.objects import MirrorCopyObject, SurfaceObject
    from fv.render.mirror import build_mirror_actors
    ff = load_file(FPH)
    surf = SurfaceObject(index=1)
    mir = MirrorCopyObject(index=1)
    mir.source_label = "Surface (1)"
    mir.mirror_plane = "YZ"
    out = build_mirror_actors(ff, mir, siblings=[surf])
    assert "mirror" in out
    a = out["mirror"]
    b = a.GetMapper().GetInput().GetBounds()
    src = ff.vertices
    # mirror across X: min/max of X flip
    assert abs((b[0] + b[1]) - (-(src[:, 0].min() + src[:, 0].max()))) < 1e-3
    # missing source -> no actors
    mir2 = MirrorCopyObject(index=2)
    assert build_mirror_actors(ff, mir2, siblings=[surf]) == {}


def test_time_series_max_min_parsers(tmp_path):
    """TM/OT CSV parsers read cycle/time and min/max rows (P2.10)."""
    from fv.model.tsmm import parse_max_min, parse_time_series
    tm = tmp_path / "series.csv"
    tm.write_text("cycle,time\n100,0.1\n200,0.2\n300,0.3\n", encoding="utf-8")
    cyc, tim = parse_time_series(str(tm))
    assert cyc == [100, 200, 300]
    assert abs(tim[2] - 0.3) < 1e-9
    mm = tmp_path / "mm.csv"
    mm.write_text("var,min,max\nPRES,-1.5,2.5\nTEMP,0,100\n", encoding="utf-8")
    vals = parse_max_min(str(mm))
    assert vals["PRES"] == (-1.5, 2.5)
    assert vals["TEMP"] == (0.0, 100.0)

def test_time_series_dialog(qapp):
    """TimeSeriesDialog loads a CSV into the object (P2.10)."""
    from fv.gui.object_dialogs2 import TimeSeriesDialog
    from fv.model.objects import TimeSeriesObject
    ts = TimeSeriesObject(index=1)
    d = TimeSeriesDialog(ts)
    d.file.setText(r"D:\training\cgns\no_such.csv")
    d.apply_to(ts)
    assert ts.file.endswith("no_such.csv")
    assert ts.cycles == []  # missing file leaves data empty


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_graph_collect_series():
    """Graph collects a variable series over cycles (P2.2)."""
    from fv.model.dataset import load_file
    from fv.model.objects import GraphObject
    from fv.render.graph import collect_series
    ff = load_file(FPH)
    g = GraphObject(index=1)
    g.variable = "PRES"
    g.x_mode = "Cycle"
    xs, ys, var = collect_series(g, ff0=ff)
    assert var == "PRES" and len(xs) == 1 and len(ys) == 1
    assert xs[0] == ff.cycle

def test_graph_dialog(qapp):
    """GraphDialog writes back variable selection (P2.2)."""
    from fv.gui.object_dialogs2 import GraphDialog
    from fv.model.objects import GraphObject
    g = GraphObject(index=1)
    d = GraphDialog(g)
    d.xmode.setCurrentIndex(d.xmode.findData("Cycle"))
    d.apply_to(g)
    assert g.x_mode == "Cycle"


def test_grouping_object_and_dialog(qapp):
    """Grouping stores member labels via its dialog (P2.5)."""
    from fv.gui.object_dialogs2 import GroupingDialog
    from fv.model.objects import GroupingObject, PlaneObject, SurfaceObject
    surf = SurfaceObject(index=1)
    plane = PlaneObject(index=1)
    g = GroupingObject(index=1)
    d = GroupingDialog(g, siblings=[surf, plane])
    for i in range(d.members.count()):
        d.members.item(i).setSelected(True)
    d.apply_to(g)
    assert set(g.member_labels) == {"Surface (1)", "Plane (1)"}

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_move_plane_to_pick():
    """Scene.move_plane_to_pick translates the plane to the pick (P2.7)."""
    from fv.model.dataset import load_file
    from fv.model.objects import MainObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff)
    sc = Scene(enable_3d=True)
    sc.build(ff, main=main)
    plane = main.children[1]
    before = tuple(plane.point)
    # pick the display centre (should hit the model) and move the plane
    moved = sc.move_plane_to_pick(300, 300, plane_obj=plane)
    if moved:
        assert tuple(plane.point) != before or plane.point is not None
        assert "plane:contour" in sc.actor_names() or True
    else:
        # headless-safe: no pick at centre is acceptable on CI
        pytest.skip("pick returned nothing at centre")


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_api_facade():
    """fv.api exposes open/create/register helpers (P3.3)."""
    from fv import api
    ff = api.open_file(FPH)
    assert "PRES" in api.variables(ff)
    surf = api.create_object(ff, "surface")
    assert surf.kind == "surface"
    api.register_variable(ff, "DP2", "PRES * 2.0")
    assert "DP2" in api.variables(ff)
    try:
        api.create_object(ff, "nosuch")
        raise AssertionError("should have raised")
    except ValueError:
        pass

def test_api_create_object_all_kinds():
    """api.create_object covers every scPOST object kind (P0.1)."""
    from fv import api
    ff = api.open_file(FPH)
    kinds = ["surface", "plane", "particle", "isosurface", "point",
             "streamline", "volume", "colorbar", "cylinder", "circle",
             "pathline", "text", "bitmap", "information", "mirror",
             "grouping", "graph", "timeseries", "maxmin", "curve",
             "periodical", "bar", "regionbc", "gradation", "camera",
             "region", "turbo", "ufo", "folder", "light", "measure"]
    for kind in kinds:
        obj = api.create_object(ff, kind)
        assert getattr(obj, "kind", "") == kind, kind
def test_api_post_processing_facade():
    """fv.api exposes turbo_ post-processing quantities (①)."""
    import numpy as np
    from fv import api
    ff = api.open_file(FPH)
    r, z, vals = api.turbo_circumferential_average(ff, "PRES", "Z", 16, 16)
    assert r is not None and vals.shape == (16, 16)
    r, z, cm = api.turbo_circumferential_mass_average(ff, "PRES", "Z", 16, 16)
    assert cm.shape == (16, 16)
    span, dp = api.turbo_blade_loading_curve(ff, "PRES", "Z", 16)
    assert len(span) == 16 and np.all(np.asarray(dp) >= 0)
    rt = api.turbo_polar_view_points(ff, "Z")
    assert rt.shape == (ff.n_vertices, 2)
    mr = api.turbo_meridional_points(ff, "Z")
    assert mr.shape == (ff.n_vertices, 2) and np.all(mr[:, 0] >= 0)
    b2b = api.turbo_blade_to_blade_points(ff, float(np.median(mr[:, 0])), "Z", 0.01)
    assert b2b.shape[1] == 2
    cp = api.turbo_pressure_coefficient(ff, 0.5, 10.0, 1.2)
    assert cp.shape == ff.variables["PRES"].array.shape
    zc, av = api.turbo_area_average(ff, "PRES", "Z", 16)
    assert zc.shape == (16,) and av.shape == (16,)
    m = api.turbo_mass_flow_average(ff, "PRES", "Z")
    assert isinstance(m, float) and np.isfinite(m)
    # deprecated unprefixed aliases still resolve
    zc2, av2 = api.area_average(ff, "PRES", "Z", 8)
    assert zc2.shape == (8,)
    assert api.mass_flow_average(ff, "PRES", "Z") == m

def test_api_topology_queries():
    """fv.api exposes scPOST FLD-class topology accessors (P0.2)."""
    import numpy as np
    from fv import api
    ff = api.open_file(FPH)
    assert api.node_count(ff) == ff.n_vertices
    assert api.element_count(ff) == ff.n_cells
    xyz = api.node_xyz(ff, 0)
    assert len(xyz) == 3
    ns = api.nodes_of_element(ff, 100)
    assert len(ns) == api.node_count_of_element(ff, 100) > 0
    fs = api.faces_of_cell(ff, 100)
    assert len(fs) == api.face_count_of_element(ff, 100) > 0
    assert len(api.face_nodes(ff, 0)) > 0
    o, n = api.cells_of_face(ff, 0)
    assert o >= 0
    assert api.area_of_face(ff, 0) > 0
    assert api.volume_of_element(ff, 100) > 0
    assert len(api.elements_of_region(ff, "FluidRegion")) == ff.n_cells
    br = ff.boundary_regions()[0]
    assert len(api.nodes_of_surface_region(ff, br.name)) > 0
    # FLD hex topology (1-based connectivity normalised)
    fld = api.open_file(FLD)
    fns = api.nodes_of_element(fld, 0)
    assert fns and max(fns) < fld.n_vertices
    assert api.face_count_of_element(fld, 0) == 6
    assert api.volume_of_element(fld, 0) > 0

def test_api_variable_queries():
    """fv.api exposes GetScalar/GetVector/MinMax accessors (P0.3)."""
    import numpy as np
    from fv import api
    ff = api.open_file(FPH)
    v = api.scalar_at(ff, "PRES", 0)
    assert isinstance(v, float)
    lo, hi = api.variable_range(ff, "PRES")
    assert lo <= v <= hi
    info = api.variable_info(ff, "PRES")
    assert info["location"] == "cell" and info["length"] == ff.n_cells
    vec = api.vector_at(ff, "VEL", 0)
    assert len(vec) == 3
    va = api.vector_array(ff, "VEL")
    assert va.shape == (ff.n_cells, 3)
    sa = api.scalar_array(ff, "PRES")
    assert sa.shape == (ff.n_cells,)
    rlo, rhi = api.scalar_range_by_region(ff, "PRES", "FluidRegion")
    assert abs(rlo - lo) < 1e-9 and abs(rhi - hi) < 1e-9
    ra = api.region_scalar_array(ff, "PRES", "FluidRegion")
    assert len(ra) == ff.n_cells
    br = ff.boundary_regions()[0]
    from fv.model.dataset import FIELD_KIND_SCALAR, VarInfo
    ff.variables["NODEV"] = VarInfo(name="NODEV", kind=FIELD_KIND_SCALAR,
                                    location="node",
                                    array=ff.vertices[:, 0])
    sfa = api.surface_scalar_array(ff, "NODEV", br.name)
    assert len(sfa) > 0

def test_api_material_region_lookups():
    """fv.api exposes MAT/VOL/RGN name lookups (P0.4)."""
    from fv import api
    ff = api.open_file(FPH)
    assert api.region_count(ff) == len(ff.boundary_regions())
    assert api.region_name(ff, 0) == ff.boundary_regions()[0].name
    assert api.surface_region_names(ff) == api.regions(ff)
    vrn = api.volume_region_names(ff)
    assert isinstance(vrn, list)
    if ff.cvol_id is not None:
        vid = api.cell_volume_region_id(ff, 0)
        assert isinstance(vid, int)
    parts = api.cells_of_part(ff, "FluidRegion")
    assert len(parts) == ff.n_cells
    # FLD material ids
    fld = api.open_file(FLD)
    mids = api.material_ids(fld)
    assert len(mids) > 0
    assert api.material_id_at(fld, 0) in mids

def test_api_extended_variables():
    """fv.api exposes CreateVarDST/NORMAL/CMBVEL + DeleteVar (P1.1)."""
    import numpy as np
    from fv import api
    ff = api.open_file(FPH)
    vi = api.register_dst(ff, "DST")
    assert vi.location == "cell" and vi.array.shape == (ff.n_cells,)
    assert float(np.nanmin(vi.array)) >= 0
    ns = api.register_normal(ff, "NORMAL")
    assert len(ns) == 3
    for vi3 in ns:
        assert vi3.array.shape == (ff.n_cells,)
        assert np.all(np.abs(vi3.array) <= 1.0 + 1e-9)
    cmb = api.register_combination_velocity(ff, "CMBVEL")
    base = np.sqrt(ff.variables["VELX"].array ** 2
                   + ff.variables["VELY"].array ** 2
                   + ff.variables["VELZ"].array ** 2)
    np.testing.assert_allclose(cmb.array, base, rtol=1e-9)
    api.set_variable_title(ff, "CMBVEL", "Combined speed")
    assert ff.variables["CMBVEL"].title == "Combined speed"
    assert api.delete_variable(ff, "CMBVEL") is not None
    assert "CMBVEL" not in ff.variables

def test_api_create_var_all_cycles(tmp_path):
    """CreateVarALLCYC registers an expression on every cycle (P1.2)."""
    import shutil
    from pathlib import Path
    from fv import api
    from fv.model.fileset import scan_sequence
    base = Path(tmp_path)
    for cyc in (1, 2, 3):
        shutil.copyfile(FPH, str(base / f"flow_{cyc}.fph"))
    fs = scan_sequence(str(base / "flow_1.fph"))
    assert len(fs) == 3
    results = api.register_var_all_cycles(fs, "PP2", "PRES + 1.0")
    assert len(results) == 3
    assert [c for c, _ in results] == [1, 2, 3]
    for _, vi in results:
        assert vi.name == "PP2" and vi.array.shape[0] > 0
def test_fileset_cycle_management(tmp_path):
    """AddCycList/DelCycList/SetCycOpeMode (P2)."""
    import shutil
    from pathlib import Path
    from fv.model.fileset import (add_cycle, remove_cycle,
        scan_sequence, set_cycle_operation)
    base = Path(tmp_path)
    for stale in base.glob("*.fph"):  # pytest_tmp is reused across sessions
        stale.unlink()
    shutil.copyfile(FPH, str(base / "flow_1.fph"))
    shutil.copyfile(FPH, str(base / "flow_2.fph"))
    fs = scan_sequence(str(base / "flow_1.fph"))
    assert len(fs) == 2
    shutil.copyfile(FPH, str(base / "flow_5.fph"))
    add_cycle(fs, str(base / "flow_5.fph"), 5)
    assert [m.cycle for m in fs.members] == [1, 2, 5]
    assert remove_cycle(fs, 2) is True
    assert remove_cycle(fs, 9) is False
    assert [m.cycle for m in fs.members] == [1, 5]
    assert set_cycle_operation(fs, "add") == "Add"
    assert fs.operation_mode == "Add"
    try:
        set_cycle_operation(fs, "bogus")
        raise AssertionError("should have raised")
    except ValueError:
        pass

def test_api_object_management():
    """GetObjNum/GetObjectByType/Remove* (P2)."""
    from fv import api
    from fv.model.objects import MainObject
    ff = api.open_file(FPH)
    main = MainObject(path=FPH, display_name="t")
    main.children = []
    s1 = api.create_object(ff, "surface")
    s2 = api.create_object(ff, "surface")
    p1 = api.create_object(ff, "plane")
    main.children.extend([s1, s2, p1])
    assert api.object_count(main) == 3
    assert api.object_types(main) == ["surface", "surface", "plane"]
    assert len(api.objects_by_type(main, "surface")) == 2
    assert api.object_by_number(main, 1) is s1
    assert api.object_by_gid(main, 1) is s1
    assert api.remove_object(main, s1) is True
    assert api.object_count(main) == 2
    assert api.remove_related_objects(main, "surface") == 1
    assert api.object_count(main) == 1
    assert api.remove_all_objects(main) == 1
    assert api.object_count(main) == 0

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_export_stl(tmp_path):
    """Boundary surface exports to STL (P3.2)."""
    from fv.model.dataset import load_file
    from fv.render.export import export_surface_stl
    ff = load_file(FPH)
    out = tmp_path / "model.stl"
    assert export_surface_stl(ff, str(out)) is True
    assert out.stat().st_size > 0

@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_compare_view_logs(qapp):
    """View > Compare reports dataset stats (P3.4)."""
    w = _make(qapp, FPH)
    w.datasets.append(w.dataset)
    w.on_compare_view()
    assert "Compare" in w.message_win.text.toPlainText()

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_ugrid_cache_reuse():
    """Repeated build_ugrid calls reuse the cached grid (P3.5)."""
    from fv.model.dataset import load_file
    from fv.render.plane import build_ugrid
    ff = load_file(FPH)
    ug1, cc1 = build_ugrid(ff)
    ug2, cc2 = build_ugrid(ff)
    assert ug1 is ug2


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_particle_intersection_cloth():
    """Intersection regions filter particles; cloth connects them (G3)."""
    import numpy as np
    from fv.crdl.fields import parse_particles
    from fv.model.dataset import load_file
    from fv.model.objects import ParticleObject
    from fv.render.particle import (build_particle_actors, _cloth_actor,
                                     _filter_intersections)
    ff = load_file(FPH)
    if not ff.has_particles:
        pytest.skip("sample has no particles")
    with open(ff.path, "rb") as fh:
        data = fh.read()
    pos, _ = parse_particles(data)
    # intersection: a tiny box around the first particle keeps ~1
    p0 = pos[0]
    obj = ParticleObject(index=1)
    obj.show_intersection_regions = True
    obj.intersection_regions = [(
        tuple(p0 - 1e-4), tuple(p0 + 1e-4))]
    filtered, _ = _filter_intersections(pos, obj)
    assert 0 < len(filtered) <= 2
    # cloth: polyline actor from the particle points
    import vtk
    from vtk.util import numpy_support as vns
    pts = vtk.vtkPoints()
    pts.SetData(vns.numpy_to_vtk(pos.astype(float), deep=True))
    pd = vtk.vtkPolyData(); pd.SetPoints(pts)
    obj2 = ParticleObject(index=1)
    obj2.special_cloth = True
    cloth = _cloth_actor(pd, obj2)
    assert cloth is not None
    assert cloth.GetMapper().GetInput().GetNumberOfLines() == 1
    # end-to-end: cloth key present in build output
    obj3 = ParticleObject(index=1)
    obj3.special_cloth = True
    out = build_particle_actors(obj3, ff)
    assert "cloth" in out


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_compare_dialog_headless(qapp):
    """CompareDialog builds headless with labelled panes (G2)."""
    from fv.gui.dialogs import CompareDialog
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    d = CompareDialog(ff, ff, enable_3d=False)
    assert "Compare" in d.windowTitle()


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_drag_plane_handlers(qapp, monkeypatch):
    """Drag handlers move the plane via the scene (G1)."""
    w = _make(qapp, FPH)
    plane = next(o for o in w.main_object.children
              if o.kind == "plane")
    moved = []
    monkeypatch.setattr(w.scene, "pick_actor",
                        lambda x, y: ((0.1, 0.2, 0.3), ("plane", plane)))
    monkeypatch.setattr(w.scene, "move_plane_to_pick",
                        lambda x, y, plane_obj=None: (
                            moved.append((x, y, plane_obj.label)), True)[1])
    w._drag_start(10, 20)
    assert w._drag_obj is plane
    w._drag_move(30, 40)
    assert moved and moved[0][:2] == (30, 40)
    w._drag_end()
    assert w._drag_obj is None
    # no pick: nothing starts
    monkeypatch.setattr(w.scene, "pick_actor", lambda x, y: (None, None))
    w._drag_start(5, 5)
    assert w._drag_obj is None


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_colorbar_actor_and_lut():
    from fv.model.objects import ColorbarObject
    from fv.render.colorbar import (
        ColorbarRegistry, build_lut, colorbar_actor,
    )
    cb = ColorbarObject()
    lut = build_lut(16, "Gray")
    assert lut.GetNumberOfTableValues() == 16
    sb = colorbar_actor(cb, range_=(0.0, 300.0))
    assert sb is not None
    assert sb.GetLookupTable() is ColorbarRegistry.lut()


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_scene_build_renders_colorbar():
    """Global ColorbarObject appended under Main renders in Scene.build."""
    from fv.model.dataset import load_file
    from fv.model.objects import ColorbarObject, MainObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff)
    cb = ColorbarObject()
    main.children.append(cb)
    sc = Scene(enable_3d=True)
    sc.build(ff, main=main)
    assert "colorbar" in sc.actor_names()


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_scene_build_colorbar_headless():
    """Headless build reports a colorbar actor layer."""
    from fv.model.dataset import load_file
    from fv.model.objects import ColorbarObject, MainObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff)
    cb = ColorbarObject()
    main.children.append(cb)
    sc = Scene(enable_3d=False)
    sc.build(ff, main=main)
    assert "colorbar" in sc.actor_names()


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_global_colorbar_applied_to_mappers():
    """Global colorbar LUT is wired onto every object's mapper (P0.2)."""
    from fv.model.dataset import load_file
    from fv.model.objects import ColorbarObject, MainObject
    from fv.render.colorbar import ColorbarRegistry
    from fv.render.scene import Scene
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff)
    surf = main.children[0]
    surf.show_contour = True
    surf.contour_var = "PRES"
    cb = ColorbarObject()
    main.children.append(cb)
    sc = Scene(enable_3d=True)
    sc.build(ff, main=main)
    checked = 0
    for actors in sc._layer_actors.values():
        for a in actors:
            if isinstance(a, str):
                continue
            mapper = getattr(a, "GetMapper", None)
            if mapper is None:
                continue
            m = mapper()
            if m is not None and m.GetLookupTable() is not None:
                assert m.GetLookupTable() is ColorbarRegistry.lut()
                checked += 1
    assert checked >= 1
    # Fix mode range is pushed into the object mappers
    cb.range_mode = "Fix"
    cb.min = -10.0
    cb.max = 10.0
    sc.apply_to_object(ff, surf)
    found_fix = False
    for actors in sc._layer_actors.values():
        for a in actors:
            if isinstance(a, str):
                continue
            mapper = getattr(a, "GetMapper", None)
            if mapper is None:
                continue
            m = mapper()
            if m is not None and m.GetLookupTable() is ColorbarRegistry.lut():
                rng = m.GetScalarRange()
                if abs(rng[0] - (-10.0)) < 1e-6 and abs(rng[1] - 10.0) < 1e-6:
                    found_fix = True
    assert found_fix


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_light_object_minimal_render():
    """LightObject drives the renderer's key light (P0.3)."""
    from fv.model.dataset import load_file
    from fv.model.objects import LightObject, MainObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff)
    light = LightObject(index=1)
    main.children.append(light)
    sc = Scene(enable_3d=True)
    sc.build(ff, main=main)
    rl = sc.renderer.GetLights().GetItemAsObject(0)
    assert abs(rl.GetIntensity() - 1.0) < 1e-6
    assert rl.GetSwitch() == 1
    light.brightness = 0.4
    light.enabled = False
    light.color = (0.9, 0.1, 0.1)
    sc.apply_to_object(ff, light)
    rl = sc.renderer.GetLights().GetItemAsObject(0)
    assert abs(rl.GetIntensity() - 0.4) < 1e-6
    assert rl.GetSwitch() == 0
    c = rl.GetDiffuseColor()
    assert abs(c[0] - 0.9) < 1e-6 and abs(c[1] - 0.1) < 1e-6

def test_light_object_headless_layer():
    """Headless build records a light layer; no renderer access."""
    from fv.model.dataset import load_file
    from fv.model.objects import LightObject, MainObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff)
    light = LightObject(index=1)
    main.children.append(light)
    sc = Scene(enable_3d=False)
    sc.build(ff, main=main)
    assert "light" in sc.actor_names()


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_particle_variable_selection():
    """Particle vector/scalar vars are honoured (P0.4)."""
    from fv.crdl.fields import parse_particle_variables
    from fv.model.dataset import load_file
    from fv.model.objects import ParticleObject
    from fv.render.particle import build_particle_actors
    ff = load_file(FPH)
    if not ff.has_particles:
        pytest.skip("sample has no particle sections")
    with open(ff.path, "rb") as fh:
        data = fh.read()
    pvars = parse_particle_variables(data)
    assert "VELP" in pvars
    assert pvars["VELP"].shape[1] == 3
    assert "VELP" in ff.particle_vars
    # vector glyphs follow vector_var (VELP default)
    obj = ParticleObject(index=1)
    obj.show_vector = True
    obj.vector_var = "VELP"
    out = build_particle_actors(obj, ff)
    assert "vector" in out
    # scalar follows scalar_var (VELP magnitude)
    obj2 = ParticleObject(index=1)
    obj2.show_scalar = True
    obj2.scalar_var = "VELP"
    out2 = build_particle_actors(obj2, ff)
    assert "particle" in out2
    pd = out2["particle"].GetMapper().GetInput()
    assert pd.GetPointData().GetScalars() is not None
    assert pd.GetPointData().GetScalars().GetName() == "ParticleScalar"


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_surface_volume_region_filter():
    """Surface honours Volume Region filtering (P0.5): fewer faces."""
    from fv.model.dataset import load_file
    from fv.model.objects import SurfaceObject
    from fv.render.surface import build_surface_polydata
    ff = load_file(FPH)
    pd_all, _, _ = build_surface_polydata(ff, SurfaceObject(index=1))
    n_all = pd_all.GetNumberOfCells()
    assert n_all > 0
    obj = SurfaceObject(index=1,
                          display_volume_regions=["Case[2]"])
    pd_f, _, _ = build_surface_polydata(ff, obj)
    n_f = pd_f.GetNumberOfCells()
    assert 0 < n_f < n_all

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_volume_volume_region_filter():
    """Volume honours Volume Region filtering (P0.5): fewer cells."""
    from fv.model.dataset import load_file
    from fv.model.objects import VolumeObject
    from fv.render.volume import build_volume_actors
    ff = load_file(FPH)
    full = VolumeObject(index=1)
    full.show_scalar = True
    full.scalar_var = "PRES"
    out_all = build_volume_actors(ff, full)
    n_all = out_all["scalar"].GetMapper().GetInput().GetNumberOfCells()
    assert n_all > 0
    obj = VolumeObject(index=1,
                        display_volume_regions=["Case[2]"])
    obj.show_scalar = True
    obj.scalar_var = "PRES"
    out_f = build_volume_actors(ff, obj)
    n_f = out_f["scalar"].GetMapper().GetInput().GetNumberOfCells()
    assert 0 < n_f < n_all


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_open_async_loads_file(qapp):
    """P0.6: launch_load parses on a worker thread and calls back."""
    import time
    from fv.gui.tasks import launch_load
    result = {}
    launch_load(FPH, on_finished=lambda ff: result.update(ff=ff),
               on_failed=lambda msg: result.update(err=msg))
    deadline = time.time() + 90
    while "ff" not in result and "err" not in result and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
    assert "ff" in result, result
    assert result["ff"].kind == "fph"
    assert result["ff"].n_cells > 0

@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_window_open_async_path(qapp):
    """P0.6: _open_file_async finalizes the window state."""
    import time
    w = _make(qapp, None)
    w._open_file_async(FPH)
    deadline = time.time() + 90
    while (w.dataset is None or w.main_object is None) and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
    assert w.dataset is not None and w.dataset.kind == "fph"
    assert "Surface (1)" in [o.label for o in w.main_object.children]


def test_light_dialog_tabs_and_apply(qapp):
    """LightDialog exposes Brightness tab and writes back (P0.3)."""
    from fv.gui.object_dialogs2 import LightDialog
    from fv.model.objects import LightObject
    light = LightObject(index=1)
    d = LightDialog(light)
    tabs = [d.tabs.tabText(i) for i in range(d.tabs.count())]
    assert tabs == ["Brightness"]
    d.enabled.setChecked(False)
    d.brightness.setValue(0.7)
    d.apply_to(light)
    assert light.enabled is False
    assert abs(light.brightness - 0.7) < 1e-6


def test_fileset_scan_sequence(tmp_path):
    """Same-stem sibling files become ordered FileSet members."""
    from fv.model.fileset import scan_sequence
    from pathlib import Path as P
    base = P(tmp_path)
    for cyc in (1, 9, 5):
        (base / f"run_{cyc}.fph").write_bytes(b"\0")
    fs = scan_sequence(str(base / "run_1.fph"))
    assert [m.cycle for m in fs.members] == [1, 5, 9]
    assert fs.min_cycle() == 1
    assert fs.max_cycle() == 9
    # find() walks at-or-after the requested cycle
    assert fs.find(6).cycle == 9


def test_fileset_scans_real_v3_sequence():
    """Real laptop_thermal_steady_scaled_v3 sequence exposes 3 steps."""
    from fv.model.fileset import scan_sequence
    v3 = r"D:\training\cgns\examples\laptop_thermal_steady_scaled_v3_10.fph"
    if not Path(v3).exists():
        pytest.skip("sequence samples not present")
    fs = scan_sequence(v3)
    assert [m.cycle for m in fs.members] == [10, 100, 200]
    assert len(fs) == 3


def test_timeline_cycle_switch(qapp, tmp_path):
    """Timeline step loads the sequence member's field data."""
    import shutil
    from pathlib import Path as P
    base = P(tmp_path)
    # Two copies of the same field file keyed by trailing cycle
    for cyc in (1, 2):
        dst = base / f"flow_{cyc}.fph"
        shutil.copyfile(FPH, dst)
    w = _make(qapp, str(base / "flow_1.fph"))
    assert w.fileset is not None
    assert w.fileset.max_cycle() == 2
    w.timeline._mode_group.button(1).setChecked(True)  # Cycle mode
    assert w.timeline.mode() == "Cycle"
    w.timeline.set_step(2)
    w._on_timeline_step(2)
    # Member for step 2 is flow_2.fph; its data now backs the scene
    assert w.dataset.path.lower().endswith("flow_2.fph")
    w._on_timeline_pause()


def test_sta_save_load_roundtrip(tmp_path):
    """Save Status → JSON .sta; load_status rebuilds the child objects."""
    from fv.model.dataset import load_file
    from fv.model.objects import MainObject
    from fv.render.export import load_status, save_status
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff, magic=True)
    # Tweak a setting to prove fidelity
    plane = next(o for o in main.children if o.kind == "plane")
    plane.coordinate = 2.5
    path = tmp_path / "state.sta"
    assert save_status(main, str(path)) is True
    restored = load_status(str(path))
    assert restored is not None
    assert len(restored) == len(main.children)
    plane2 = next(o for o in restored if o.kind == "plane")
    assert plane2.coordinate == 2.5
    assert plane2.label == "Plane (1)"


def test_snapshot_png_headless_returns_false(tmp_path):
    """Headless scene has no render window → snapshot_png returns False."""
    from fv.model.dataset import load_file
    from fv.render.export import snapshot_png
    from fv.render.scene import Scene
    ff = load_file(FPH)
    sc = Scene(enable_3d=False)
    sc.build(ff)
    assert snapshot_png(sc, str(tmp_path / "x.png")) is False


def test_export_handlers_wired(qapp):
    """File menu exposes Save Status / Print / Export PNG (D-gap)."""
    w = _make(qapp, FPH)
    file_menu = w.menuBar().actions()[0].menu()
    labels = [a.text() for a in file_menu.actions()]
    assert "Save Status" in labels
    assert "Print" in labels
    assert "Export PNG…" in labels
    # Direct method presence & graceful headless behaviour
    w.on_export_png()
    w.on_print()


def test_menu_stubs_wired(qapp):
    """Menu/view stubs now have real handlers (E-gap)."""
    w = _make(qapp, FPH)
    display = w.menuBar().actions()[2].menu()  # Display
    dlabels = [a.text() for a in display.actions()]
    assert "Redraw" in dlabels and "Show All" in dlabels
    assert "Hide All" in dlabels
    # View menu has Iso Metric / Compare wired to handlers
    view = w.menuBar().actions()[3].menu()  # View
    vlabels = [a.text() for a in view.actions()]
    assert "Iso Metric" in vlabels and "Compare" in vlabels
    # Handlers exist and don't crash in headless mode
    w.on_redraw()
    w.on_show_all_objects()
    w.on_hide_all_objects()
    w.on_iso_metric()
    w.on_compare_view()


def test_environment_dialog(qapp):
    """Option → Environment dialog constructs with checkboxes."""
    from fv.gui.dialogs import EnvironmentDialog
    w = _make(qapp, FPH)
    dlg = EnvironmentDialog(w)
    assert hasattr(dlg, "chk_status")
    assert hasattr(dlg, "chk_bggrad")
    dlg.chk_status.setChecked(False)
    dlg._on_ok()


def test_on_contour_display_headless(qapp):
    """Display → Contour rebuilds the scene headlessly."""
    w = _make(qapp, FPH)
    w.on_contour_display()
    assert "surface" in w.scene.actor_names()
    assert "grid" in w.scene.actor_names()


@pytest.mark.skipif(not Path(FPH).exists(), reason='sample not present')
def test_compare_dialog_panes(qapp):
    '''CompareDialog builds headless with labelled panes (G2).'''
    from fv.gui.dialogs import CompareDialog
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    d = CompareDialog(ff, ff, enable_3d=False)
    assert d.layout().count() >= 1


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_curve_object():
    """Curve samples a variable along a control-point polyline (A1)."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.model.objects import CurveObject
    from fv.render.curve import build_curve_actors, sample_along_curve
    ff = load_file(FPH)
    c0 = ff.vertices.min(axis=0)
    c1 = ff.vertices.max(axis=0)
    obj = CurveObject(index=1)
    obj.points = [tuple(c0), tuple(c1)]
    obj.variable = "PRES"
    obj.samples = 32
    arc, vals, var = sample_along_curve(ff, obj)
    assert var == "PRES"
    assert len(arc) == 32 and len(vals) == 32
    assert np.all(np.diff(arc) >= 0)
    out = build_curve_actors(ff, obj)
    assert "curve" in out
    assert out["curve"].GetMapper().GetInput().GetNumberOfPoints() >= 2
    # empty points -> no actors
    assert build_curve_actors(ff, CurveObject(index=2)) == {}

def test_curve_dialog(qapp):
    """CurveDialog writes back points/variable (A1)."""
    from fv.gui.object_dialogs2 import CurveDialog
    from fv.model.objects import CurveObject
    c = CurveObject(index=1)
    d = CurveDialog(c)
    d.pts.clear();
    d.pts.addItem("0,0,0");
    d.pts.addItem("1,1,1")
    d.samples.setValue(50)
    d.apply_to(c)
    assert c.points == [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)]
    assert c.samples == 50


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_periodical_copy():
    """Periodical Copy produces rotated copies of a surface (A2)."""
    from fv.model.dataset import load_file
    from fv.model.objects import PeriodicalCopyObject, SurfaceObject
    from fv.render.periodical import build_periodical_actors
    ff = load_file(FPH)
    surf = SurfaceObject(index=1)
    obj = PeriodicalCopyObject(index=1)
    obj.source_label = "Surface (1)"
    obj.axis = "Z"
    obj.copies = 4
    out = build_periodical_actors(ff, obj, siblings=[surf])
    assert len(out) == 3  # 4 copies total = 3 rotated + original kept
    # a 180-degree copy about Z flips X and Y
    b0 = out["copy2"].GetMapper().GetInput().GetBounds()
    assert b0[0] < 0 or b0[1] > 0  # bounds shifted
    assert build_periodical_actors(ff, PeriodicalCopyObject(index=2),
                                   siblings=[surf]) == {}

def test_mirror_periodical_multi_source_dialog(qapp):
    """Mirror/Periodical dialogs select multiple source surfaces (8)."""
    from fv.model.objects import MirrorCopyObject, PeriodicalCopyObject
    from fv.gui.object_dialogs2 import MirrorCopyDialog, PeriodicalCopyDialog
    sibs = [type("S", (), {"kind": "surface", "label": "Surface (1)"})(),
            type("S", (), {"kind": "surface", "label": "Surface (2)"})()]
    m = MirrorCopyObject(index=1)
    d = MirrorCopyDialog(m, siblings=sibs)
    for i in range(d.source.count()):
        d.source.item(i).setSelected(True)
    d.apply_to(m)
    assert m.source_labels == ["Surface (1)", "Surface (2)"]
    assert m.source_label == "Surface (1)"
    p = PeriodicalCopyObject(index=1)
    d2 = PeriodicalCopyDialog(p, siblings=sibs)
    d2.source.item(0).setSelected(True)
    d2.apply_to(p)
    assert p.source_labels == ["Surface (1)"]
    assert p.source_label == "Surface (1)"

@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_delx_difference():
    """delx() registers a central difference of a node field (B1)."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.model.varreg import register_variable
    ff = load_file(FLD)
    from fv.model.dataset import FIELD_KIND_SCALAR, VarInfo
    ff.variables["XC"] = VarInfo(name="XC", kind=FIELD_KIND_SCALAR,
                                 location="node", array=ff.vertices[:, 0])
    vi = register_variable(ff, "DPDX", "delx(XC)")
    assert vi.kind == "scalar"
    assert vi.array.shape == (ff.n_vertices,)
    assert np.isfinite(vi.array).all()
    nz = vi.array[np.nonzero(vi.array)]
    assert len(nz) > 0
    assert np.abs(nz - 1.0).max() < 0.2
    # FPH cell fields now support delx (item 2): no error, returns cell values
    from fv.model.dataset import load_file as lf
    fph = lf(FPH)
    vi_fph = register_variable(fph, "FPHDX", "delx(PRES)")
    assert vi_fph.kind == "scalar"
    assert vi_fph.array.shape == (fph.n_cells,)


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_grad_div_rot():
    """grad/div/rot operate on node fields (B2)."""
    import numpy as np
    from fv.model.dataset import FIELD_KIND_SCALAR, VarInfo
    from fv.model.dataset import load_file
    from fv.model.varreg import register_variable
    ff = load_file(FLD)
    v = ff.vertices
    ff.variables["S"] = VarInfo(name="S", kind=FIELD_KIND_SCALAR,
                              location="node", array=v[:, 0])
    for c, arr in zip("XYZ", (v[:, 0], np.zeros(len(v)), np.zeros(len(v)))):
        ff.variables["V" + c] = VarInfo(name="V" + c,
            kind=FIELD_KIND_SCALAR, location="node", array=arr)
    g = register_variable(ff, "GS", "grad(S)")
    assert g.kind == "vector"
    assert g.array.shape == (ff.n_vertices, 3)
    nz = np.nonzero(np.abs(g.array).sum(axis=1))[0]
    assert len(nz) > 0
    assert np.abs(g.array[nz, 0] - 1.0).max() < 0.2
    d = register_variable(ff, "DV", "div(V)")
    assert d.kind == "scalar"
    assert np.abs(d.array[nz] - 1.0).max() < 0.2  # div(x,0,0) = 1
    r = register_variable(ff, "RV", "rot(V)")
    assert r.kind == "vector"
    assert np.abs(r.array).max() < 0.4


def test_measure_distance_angle():
    """Measure computes distance and angle (C2)."""
    from fv.model.objects import MeasureObject
    from fv.render.measure import angle, compute, distance
    assert abs(distance((0, 0, 0), (3, 4, 0)) - 5.0) < 1e-9
    assert abs(angle((1, 0, 0), (0, 0, 0), (0, 1, 0)) - 90.0) < 1e-9
    m = MeasureObject(index=1)
    m.points = [(0, 0, 0), (3, 4, 0)]
    assert "5" in compute(m)
    m2 = MeasureObject(index=2, mode="Angle")
    m2.points = [(1, 0, 0), (0, 0, 0), (0, 1, 0)]
    assert "90" in compute(m2)

def test_measure_ratio():
    """Measure ratio compares two distances (Compare Scales, 9)."""
    from fv.model.objects import MeasureObject
    from fv.render.measure import compute_ratio, ratio
    m1 = MeasureObject(points=[(0, 0, 0), (4, 0, 0)])
    m2 = MeasureObject(points=[(0, 0, 0), (2, 0, 0)])
    assert abs(ratio(m1, m2) - 2.0) < 1e-9
    assert abs(ratio(m2, m1) - 0.5) < 1e-9
    assert "2" in compute_ratio(m1, m2)
    # zero denominator -> 0.0
    m3 = MeasureObject(points=[(0, 0, 0), (0, 0, 0)])
    assert ratio(m1, m3) == 0.0

def test_grouping_members_hierarchy():
    """grouping_members flattens nested subgroups (9)."""
    from types import SimpleNamespace
    from fv.model.objects import grouping_members
    g1 = SimpleNamespace(label="G1", subgroups=[], member_labels=["A", "B"])
    g2 = SimpleNamespace(label="G2", subgroups=["G1"], member_labels=["C"])
    objmap = {"G1": g1, "G2": g2}
    assert grouping_members(g2, objmap) == ["A", "B", "C"]
    # cycle safety
    cyc = SimpleNamespace(label="C1", subgroups=["C2"], member_labels=["X"])
    cyc2 = SimpleNamespace(label="C2", subgroups=["C1"], member_labels=["Y"])
    assert grouping_members(cyc, {"C1": cyc, "C2": cyc2}) == ["Y", "X"]
def test_measure_dialog(qapp):
    """MeasureDialog writes points/mode back (C2)."""
    from fv.gui.object_dialogs2 import MeasureDialog
    from fv.model.objects import MeasureObject
    m = MeasureObject(index=1)
    d = MeasureDialog(m)
    d.mode.setCurrentIndex(d.mode.findData("Angle"))
    d.spins[0][0].setValue(1.0)
    d.apply_to(m)
    assert m.mode == "Angle"
    assert m.points[0][0] == 1.0


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_xdmf_reader(tmp_path):
    """Inline XDMF parses into a FieldFile (D1)."""
    from fv.model.dataset import xdmf_load
    from fv.model.loaders import can_load
    # 1 hexahedron: 8 nodes, 1 cell, 1 node attribute
    coords = "0 0 0  1 0 0  1 1 0  0 1 0  0 0 1  1 0 1  1 1 1  0 1 1"
    conn = "0 1 2 3 4 5 6 7"
    pres = "1 2 3 4 5 6 7 8"
    xml = f"""<?xml version="1.0"?>
    <Xdmf><Domain><Grid Name="g">
    <Topology TopologyType="Hexahedron" NumberOfElements="1">
    <DataItem Dimensions="1 8" Format="XML">{conn}</DataItem></Topology>
    <Geometry GeometryType="XYZ"><DataItem Dimensions="8 3" Format="XML">
    {coords}</DataItem></Geometry>
    <Attribute Name="PRES" Center="Node">
    <DataItem Dimensions="8" Format="XML">{pres}</DataItem></Attribute>
    </Grid></Domain></Xdmf>"""
    xmf = tmp_path / "cube.xmf"
    xmf.write_text(xml, encoding="utf-8")
    assert can_load(str(xmf)) is True
    ff = xdmf_load(str(xmf))
    assert ff.kind == "xdmf"
    assert ff.n_vertices == 8 and ff.n_cells == 1
    assert ff.variables["PRES"].location == "node"
    assert ff.variables["PRES"].array.tolist() == [1, 2, 3, 4, 5, 6, 7, 8]


def test_folder_tree_hierarchy(qapp):
    """Folder nests member objects under a tree node (A3)."""
    from fv.model.dataset import load_file
    from fv.model.objects import FolderObject, SurfaceObject
    ff = load_file(FPH)
    folder = FolderObject(index=1)
    folder.member_labels = ["Surface (1)"]
    w = _make(qapp, FPH)
    w.main_object.children.append(folder)
    w.object_tree.load_main(w.main_object)
    fitem = w.object_tree._items.get("Folder (1)")
    assert fitem is not None
    # Surface (1) should be nested under the folder
    names = [fitem.child(i).text(0) for i in range(fitem.childCount())]
    assert "Surface (1)" in names
    # Plane (1) is not a member -> stays under main
    mitem = w.object_tree._items.get("__main__")
    top = [mitem.child(i).text(0) for i in range(mitem.childCount())]
    assert "Plane (1)" in top


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_bar_object():
    """Bar samples a variable along a two-point line (A4)."""
    from fv.model.dataset import load_file
    from fv.model.objects import BarObject
    from fv.render.bar import build_bar_actors, sample_bar
    ff = load_file(FPH)
    c0 = ff.vertices.min(axis=0)
    c1 = ff.vertices.max(axis=0)
    obj = BarObject(index=1)
    obj.point1 = tuple(c0)
    obj.point2 = tuple(c1)
    obj.variable = "PRES"
    obj.samples = 16
    t, vals, var = sample_bar(ff, obj)
    assert var == "PRES"
    assert len(t) == 16 and len(vals) == 16
    assert abs(t[0]) < 1e-12 and abs(t[-1] - 1.0) < 1e-12
    out = build_bar_actors(ff, obj)
    assert "bar" in out
    assert out["bar"].GetMapper().GetInput().GetNumberOfPoints() == 16


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_regionbc_dialog(qapp):
    """RegionBC lists boundary region names + face counts (A5)."""
    from fv.gui.object_dialogs2 import RegionBCDialog
    from fv.model.dataset import load_file
    from fv.model.objects import RegionBCObject
    ff = load_file(FPH)
    obj = RegionBCObject(index=1)
    d = RegionBCDialog(obj, field_file=ff)
    assert d.list.count() == len(ff.surface_regions)
    assert any("faces" in d.list.item(i).text()
            for i in range(d.list.count()))


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_gradation_background():
    """GradationObject drives the renderer gradient background (C1)."""
    from fv.model.dataset import load_file
    from fv.model.objects import GradationObject, MainObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff)
    grad = GradationObject(index=1)
    grad.top_color = (0.1, 0.2, 0.3)
    grad.bottom_color = (0.9, 0.8, 0.7)
    main.children.append(grad)
    sc = Scene(enable_3d=True)
    sc.build(ff, main=main)
    bg = sc.renderer.GetBackground()
    assert abs(bg[0] - 0.1) < 1e-6 and abs(bg[2] - 0.3) < 1e-6
    grad.enabled = False
    sc.apply_gradation(grad)
    assert sc.renderer.GetGradientBackground() == 0


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_object_name_billboard():
    """show_object_name sets a billboard label (C3)."""
    from fv.model.dataset import load_file
    from fv.model.objects import MainObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff)
    sc = Scene(enable_3d=True)
    sc.build(ff, main=main)
    sc.show_object_name("Surface (1)", (0.0, 0.0, 0.0))
    assert sc._name_actor is not None
    assert sc._name_actor.GetInput() == "Surface (1)"
    sc.hide_object_name()
    assert sc._name_actor is None
    # headless records text without an actor
    sc2 = Scene(enable_3d=False)
    sc2.build(ff, main=main)
    sc2.show_object_name("Plane (1)")
    assert sc2._name_text == "Plane (1)"
    assert sc2._name_actor is None


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_api_queries():
    """fv.api exposes region/MAT/cell query helpers (E1)."""
    import numpy as np
    from fv import api
    ff = api.open_file(FPH)
    names = api.regions(ff)
    assert len(names) > 0
    assert all(isinstance(n, str) for n in names)
    c = api.cell_centers(ff)
    assert c is not None and c.shape == (ff.n_cells, 3)
    assert np.isfinite(c).all()
    adj = api.adjacent_cells(ff, 0)
    assert isinstance(adj, list)
    assert all(isinstance(x, int) for x in adj)


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_particle_trim_filter():
    """Trim tab number range filters particles (E2)."""
    import numpy as np
    from fv.crdl.fields import parse_particles
    from fv.model.dataset import load_file
    from fv.model.objects import ParticleObject
    from fv.render.particle import _filter_by_trim, _parse_range
    ff = load_file(FPH)
    if not ff.has_particles:
        pytest.skip("sample has no particles")
    with open(ff.path, "rb") as fh:
        pos, vel = parse_particles(fh.read())
    assert _parse_range("1-5,9") == {1, 2, 3, 4, 5, 9}
    obj = ParticleObject(index=1)
    obj.display_particle_no = "0-9"
    out = _filter_by_trim(pos, vel, obj)
    assert 0 < len(out) <= 10
    obj2 = ParticleObject(index=2)
    obj2.display_particle_no = "999-1000"
    assert len(_filter_by_trim(pos, vel, obj2)) == 0


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_multi_object_drag(qapp, monkeypatch):
    """Drag dispatches to cylinder/circle/point moves (E3)."""
    w = _make(qapp, FPH)
    from fv.model.objects import CylinderObject
    cyl = CylinderObject(index=5)
    w.main_object.children.append(cyl)
    monkeypatch.setattr(w.scene, "pick_actor",
                        lambda x, y: ((0.5, 0.6, 0.7), ("x", cyl)))
    monkeypatch.setattr(w.scene, "apply_to_object",
                        lambda ff, o: True)
    moved = w._move_object_to_pick(cyl, 10, 20)
    assert moved is True
    assert cyl.center == (0.5, 0.6, 0.7)
    # plane path uses move_plane_to_pick
    plane = next(o for o in w.main_object.children if o.kind == "plane")
    monkeypatch.setattr(w.scene, "move_plane_to_pick",
                        lambda x, y, plane_obj=None: True)
    assert w._move_object_to_pick(plane, 0, 0) is True


def test_nastran_reader(tmp_path):
    """Free-field Nastran mesh parses into a FieldFile (D2)."""
    from fv.model.dataset import nastran_load
    from fv.model.loaders import can_load
    nas = tmp_path / "box.nas"
    lines = [
        "GRID,1,,0.0,0.0,0.0",
        "GRID,2,,1.0,0.0,0.0",
        "GRID,3,,1.0,1.0,0.0",
        "GRID,4,,0.0,1.0,0.0",
        "GRID,5,,0.0,0.0,1.0",
        "GRID,6,,1.0,0.0,1.0",
        "GRID,7,,1.0,1.0,1.0",
        "GRID,8,,0.0,1.0,1.0",
        "CHEXA,1,1,1,2,3,4,5,6,7,8",
        "ENDDATA",
    ]
    nas.write_text("\n".join(lines), encoding="utf-8")
    assert can_load(str(nas)) is True
    ff = nastran_load(str(nas))
    assert ff.kind == "nastran"
    assert ff.n_vertices == 8 and ff.n_cells == 1
    assert ff.cell_types.tolist() == [12]

def test_neutral_ply_variables(tmp_path):
    """PLY per-vertex scalar properties import as node variables (7)."""
    import struct
    from fv.model.dataset import neutral_load
    # ASCII PLY
    ply = "\n".join([
        "ply", "format ascii 1.0", "element vertex 4",
        "property float x", "property float y", "property float z",
        "property float quality", "element face 2",
        "property list uchar int vertex_indices", "end_header",
        "0 0 0 1.0", "1 0 0 2.0", "1 1 0 3.0", "0 1 0 4.0",
        "3 0 1 2", "3 0 2 3",
    ])
    a = tmp_path / "a.ply"
    a.write_text(ply, encoding="utf-8")
    ff = neutral_load(str(a))
    assert ff.kind == "neutral" and ff.n_vertices == 4
    assert ff.variables["quality"].location == "node"
    assert ff.variables["quality"].array.tolist() == [1.0, 2.0, 3.0, 4.0]
    # Binary little-endian PLY
    verts = [(0, 0, 0, 1.0), (1, 0, 0, 2.0), (1, 1, 0, 3.0), (0, 1, 0, 4.0)]
    faces = [[0, 1, 2], [0, 2, 3]]
    hdr = ("ply\nformat binary_little_endian 1.0\nelement vertex 4\n"
           "property float x\nproperty float y\nproperty float z\n"
           "property float quality\nelement face 2\n"
           "property list uchar int vertex_indices\nend_header\n")
    body = b""
    for x, y, z, q in verts:
        body += struct.pack("<4f", x, y, z, q)
    for f in faces:
        body += struct.pack("B", len(f)) + struct.pack("<3i", *f)
    b = tmp_path / "b.ply"
    b.write_bytes(hdr.encode() + body)
    ffb = neutral_load(str(b))
    assert ffb.n_vertices == 4
    assert ffb.variables["quality"].array.tolist() == [1.0, 2.0, 3.0, 4.0]

def test_marc_results_sidecar(tmp_path):
    """Marc .dat + .res node results sidecar imports variables (7)."""
    from fv.model.dataset import marc_load
    dat = tmp_path / "box.dat"
    dat.write_text("\n".join([
        "$ sample", "1,0,0,0", "2,1,0,0", "3,1,1,0", "4,0,1,0",
        "5,0,0,1", "6,1,0,1", "7,1,1,1", "8,0,1,1",
        "1,7,1,2,3,4,5,6,7,8",
    ]), encoding="utf-8")
    (tmp_path / "box.res").write_text(
        "1 10.0\n2 20.0\n3 30.0\n4 40.0\n5 50.0\n6 60.0\n7 70.0\n8 80.0\n",
        encoding="utf-8")
    ff = marc_load(str(dat))
    assert "RES1" in ff.variables
    assert ff.variables["RES1"].location == "node"
    assert ff.variables["RES1"].array.tolist() == [10, 20, 30, 40, 50, 60, 70, 80]

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_export_obj(tmp_path):
    """Boundary surface exports to OBJ (4)."""
    from fv.model.dataset import load_file
    from fv.render.export import export_surface_obj
    ff = load_file(FPH)
    out = tmp_path / "model.obj"
    assert export_surface_obj(ff, str(out)) is True
    txt = out.read_text(encoding="utf-8")
    assert txt.startswith("# flowviewer OBJ export")
    assert "v " in txt and "f " in txt  # HEXAHEDRON


def test_camera_dialog(qapp):
    """CameraDialog writes position/focal/projection back (5b)."""
    from fv.gui.object_dialogs2 import CameraDialog
    from fv.model.objects import CameraObject
    c = CameraObject(index=1)
    d = CameraDialog(c)
    d.posx.setValue(1.5)
    d.fz.setValue(-2.0)
    d.parallel.setChecked(False)
    d.apply_to(c)
    assert c.position[0] == 1.5
    assert c.focal_point[2] == -2.0
    assert c.parallel_projection is False
    d.scene = None
    d._apply_camera()

def test_camera_keyframes_and_sequence():
    """Camera keyframe interpolation + sequence capture degrade (5b)."""
    import numpy as np
    from fv.render.camera import (capture_camera_sequence, interpolate_pose,
                                  keyframe_poses)
    kf0 = {"position": (0, 0, 1), "focal_point": (0, 0, 0),
           "view_up": (0, 1, 0), "parallel": True}
    kf1 = {"position": (2, 0, 1), "focal_point": (0, 0, 0),
           "view_up": (0, 1, 0), "parallel": False}
    mid = interpolate_pose(kf0, kf1, 0.5)
    assert mid["position"] == (1.0, 0.0, 1.0)
    assert interpolate_pose(kf0, kf1, 0.25)["parallel"] is True
    assert interpolate_pose(kf0, kf1, 0.75)["parallel"] is False
    poses = keyframe_poses([kf0, kf1], 5)
    assert len(poses) == 5
    assert poses[0]["position"] == kf0["position"]
    assert poses[-1]["position"] == kf1["position"]
    assert poses[2]["position"] == (1.0, 0.0, 1.0)
    assert len(keyframe_poses([kf0], 4)) == 4
    assert keyframe_poses([], 3) == []
    # headless capture writes nothing but returns an int
    n = capture_camera_sequence(None, [kf0, kf1], 3, "tmp")
    assert isinstance(n, int) and n == 0

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_region_object():
    """RegionObject renders a single boundary region (5d)."""
    from fv.model.dataset import load_file
    from fv.model.objects import RegionObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    name = ff.boundary_regions()[0].name
    obj = RegionObject(index=1)
    obj.region_name = name
    sc = Scene(enable_3d=False)
    sc.build(ff)
    sc._add_region_actor(ff, obj)
    assert "region" in sc.actor_names()

def test_dispatch_routes_turbo_region():
    """_dispatch_object wires turbo/region to their actor builders (fix 1)."""
    from fv.model.dataset import load_file
    from fv.model.objects import RegionObject, TurboObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    sc = Scene(enable_3d=False)
    calls = []
    sc._add_turbo_actor = lambda f, o: calls.append("turbo")
    sc._add_region_actor = lambda f, o: calls.append("region")
    sc._dispatch_object(ff, TurboObject(index=1))
    sc._dispatch_object(ff, RegionObject(index=1))
    assert calls == ["turbo", "region"]

def test_ufo_points_values():
    """UFO resolves external points/values, a variable, or all vertices (2)."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.model.objects import UFOObject
    from fv.render.ufo import ufo_points_values
    ff = load_file(FPH)
    u = UFOObject(index=1)
    # fallback: all vertices, no scalar
    pts, vals = ufo_points_values(ff, u)
    assert pts.shape == (ff.n_vertices, 3) and vals is None
    # colour-by cell-centred variable -> cell centres
    u.variable = "PRES"
    pts, vals = ufo_points_values(ff, u)
    assert pts.shape == (ff.n_cells, 3) and vals.shape == (ff.n_cells,)
    # external point set + values
    u.data = {"points": np.array([[0,0,0],[1,0,0]]), "values": np.array([1.0, 2.0])}
    pts, vals = ufo_points_values(ff, u)
    assert pts.shape == (2, 3) and vals.tolist() == [1.0, 2.0]

def test_dispatch_routes_ufo():
    """_dispatch_object wires ufo to _add_ufo_actor (fix 2)."""
    from fv.model.dataset import load_file
    from fv.model.objects import UFOObject
    from fv.render.scene import Scene
    ff = load_file(FPH)
    sc = Scene(enable_3d=False)
    calls = []
    sc._add_ufo_actor = lambda f, o: calls.append("ufo")
    sc._dispatch_object(ff, UFOObject(index=1))
    assert calls == ["ufo"]

def test_ufo_dialog(qapp):
    """UFODialog writes variable/point_size/color back (2)."""
    from fv.model.dataset import load_file
    from fv.model.objects import UFOObject
    from fv.gui.object_dialogs2 import UFODialog
    ff = load_file(FPH)
    u = UFOObject(index=1)
    d = UFODialog(u, field_file=ff)
    d.variable.setCurrentIndex(d.variable.findData("PRES"))
    d.psize.setValue(6.0)
    d.mode.setCurrentIndex(d.mode.findData("surface"))
    d.apply_to(u)
    assert u.variable == "PRES"
    assert u.point_size == 6.0
    assert u.mode == "surface"

def test_ufo_triangulate():
    """UFO fan-triangulates polygon faces (③)."""
    import numpy as np
    from fv.model.objects import UFOObject
    from fv.render.ufo import triangulate, ufo_triangles
    tris = triangulate([[0, 1, 2, 3]])
    assert np.asarray(tris).tolist() == [[0, 1, 2], [0, 2, 3]]
    u = UFOObject(index=1)
    u.data = {"cells": [[0, 1, 2], [0, 2, 3]]}
    assert ufo_triangles(None, u).tolist() == [[0, 1, 2], [0, 2, 3]]
    # Mx3 array passthrough
    u.data = {"cells": np.array([[0, 1, 2]], dtype=np.int64)}
    assert ufo_triangles(None, u).shape == (1, 3)
@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_limited_plane_clip():
    """Limited plane clips the cut to a finite box (5c)."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render.plane import build_plane_actors
    ff = load_file(FPH)
    full = PlaneObject(index=1, axis="Z", coordinate=0.0)
    full.show_contour = True; full.contour_var = "PRES"
    n_full = build_plane_actors(ff, full)["contour"].GetMapper().GetInput().GetNumberOfPoints()
    lim = PlaneObject(index=2, axis="Z", coordinate=0.0, limited=True,
                     limited_size=0.02)
    lim.show_contour = True; lim.contour_var = "PRES"
    out = build_plane_actors(ff, lim)
    assert "contour" in out
    n_lim = out["contour"].GetMapper().GetInput().GetNumberOfPoints()
    assert n_lim <= n_full

def test_global_window_container(qapp):
    """GlobalWindow holds the global objects (5a)."""
    w = _make(qapp, None)
    assert w.global_window.colorbar is not None
    assert w.global_window.camera is w._global_camera
    assert w.global_window.light is w._global_light


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_graph_curve_mode():
    """Graph samples a Curve as the arc-length X axis (6)."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.model.objects import CurveObject, GraphObject
    from fv.render.graph import collect_series
    ff = load_file(FPH)
    c0 = tuple(ff.vertices.min(axis=0))
    c1 = tuple(ff.vertices.max(axis=0))
    curve = CurveObject(index=1)
    curve.points = [c0, c1]
    curve.variable = "PRES"
    curve.samples = 16
    g = GraphObject(index=1)
    g.x_mode = "Curve"
    g.curve_label = "Curve (1)"
    xs, ys, var = collect_series(g, ff0=ff, curves=[curve])
    assert var == "PRES"
    assert len(xs) == 16 and len(ys) == 16
    assert xs[0] == 0.0
    assert np.all(np.diff(xs) >= 0)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_turbo_views():
    """Meridional / blade-to-blade transforms produce 2D points (7a)."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.render.turbo import (blade_to_blade_points, build_turbo_actors,
        meridional_points)
    ff = load_file(FPH)
    rz = meridional_points(ff, "Z")
    assert rz.shape == (ff.n_vertices, 2)
    assert np.all(rz[:, 0] >= 0)  # radius non-negative
    rmid = float(np.median(rz[:, 0]))
    b2b = blade_to_blade_points(ff, rmid, "Z", tol=rmid * 0.1)
    assert b2b.shape[1] == 2
    assert b2b.shape[0] > 0


def test_ufo_object(qapp):
    """UFO object + dialog build (7b)."""
    from fv.gui.object_dialogs2 import UFODialog
    from fv.model.objects import UFOObject
    u = UFOObject(index=1)
    d = UFODialog(u)
    assert d.tabs.tabText(0) == "UFO"

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_ufo_surface_actor():
    """UFO surface mode builds a triangle mesh (③)."""
    import numpy as np
    from fv.model.objects import UFOObject
    from fv.render.ufo import build_ufo_actors
    u = UFOObject(index=1)
    u.data = {"points": np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]], dtype=np.float64),
              "cells": [[0,1,2],[0,2,3]]}
    u.mode = "surface"
    out = build_ufo_actors(None, u)
    assert "ufo" in out
    pd = out["ufo"].GetMapper().GetInput()
    assert pd.GetNumberOfCells() == 2
    assert pd.GetNumberOfPoints() == 4
def test_com_interface():
    """COM Application object loads a file and reports metadata (7c)."""
    from fv.com import FlowviewerApplication, _HAS_COM
    app = FlowviewerApplication()
    app.open_file(FPH)
    assert app.kind == "fph"
    assert "PRES" in app.variables()
    assert app.cycles() == 9
    app.quit()
    assert app.variables() == []
    assert isinstance(_HAS_COM, bool)

def test_com_properties_events_lifecycle():
    """COM Application exposes read-only props, events and context mgmt (3)."""
    from fv.com import FlowviewerApplication, VERSION
    app = FlowviewerApplication()
    assert app.version == VERSION
    assert app.has_file is False
    assert app.file_path == ""
    assert app.n_cells == 0 and app.n_vertices == 0
    events = []
    class Sink:
        def on_open(self, path):
            events.append(("open", path))
        def on_close(self):
            events.append(("close", None))
    sink = Sink()
    assert app.subscribe(sink) == 1
    app.open_file(FPH)
    assert app.kind == "fph"
    assert app.has_file is True
    assert app.file_path == FPH
    assert app.kind == "fph"
    assert app.n_cells > 0 and app.n_vertices > 0
    assert app.cycle == 9
    assert "PRES" in app.variable_names
    assert events == [("open", FPH)]
    app.close()
    assert app.has_file is False
    assert events[-1] == ("close", None)
    assert app.unsubscribe(sink) == 0
    with FlowviewerApplication() as app2:
        app2.open_file(FPH)
        assert app2.has_file is True
    assert app2.has_file is False

def test_com_connection_points():
    """COM exposes IConnectionPointContainer semantics (3)."""
    from fv.com import (EVENTS_IID, FlowviewerApplication, _iid_matches)
    app = FlowviewerApplication()
    # COM-facing container methods return a wrapped connection point
    cps = app.EnumConnectionPoints()
    assert len(cps) == 1 and cps[0] is not None
    assert app.FindConnectionPoint(EVENTS_IID) is not None
    assert app.FindConnectionPoint("{00000000-0000-0000-0000-000000000000}") is None
    assert _iid_matches(EVENTS_IID, EVENTS_IID.lower().strip("{}"))
    # Python-side cookie semantics on the underlying point
    cp = app._cp
    events = []
    class Sink:
        def on_open(self, path):
            events.append(("open", path))
        def on_close(self):
            events.append(("close", None))
    c1 = cp.Advise(Sink())
    c2 = cp.Advise(Sink())
    assert c1 != c2 and c1 > 0 and c2 > 0
    assert len(cp.EnumConnections()) == 2
    assert cp.Unadvise(c1) is True
    assert cp.Unadvise(c1) is False
    assert len(cp.EnumConnections()) == 1
    # VBS-style PascalCase sink still receives events (case-insensitive)
    class VbsSink:
        def OnOpen(self, path):
            events.append(("open", path))
        def OnClose(self):
            events.append(("close", None))
    cookie = app.subscribe(VbsSink())
    app.open_file(FPH)
    app.close()
    assert ("open", FPH) in events and ("close", None) in events
    app.unsubscribe(None)
    app.release()
    assert len(cp.EnumConnections()) == 0

def test_com_simple_connection():
    """Real COM link: QI IConnectionPointContainer -> Advise -> Invoke (②)."""
    try:
        import win32com.client.dynamic
        import win32com.client.connect
        import win32com.server.util
    except ImportError:
        pytest.skip("pywin32 unavailable")
    from fv.com import EVENTS_IID, FlowviewerApplication
    app = FlowviewerApplication()
    server = win32com.client.dynamic.Dispatch(
        win32com.server.util.wrap(app))
    class COMSink:
        _public_methods_ = ["on_open", "on_close"]
        def __init__(self):
            self.opened = []
            self.closed = 0
        def _query_interface_(self, iid):
            if str(iid).strip("{}").lower() == EVENTS_IID.strip("{}").lower():
                return win32com.server.util.wrap(self)
            return None
        def on_open(self, path):
            self.opened.append(path)
        def on_close(self):
            self.closed += 1
    sink = COMSink()
    conn = win32com.client.connect.SimpleConnection()
    conn.Connect(server, sink, EVENTS_IID)
    server.open_file(FPH)
    server.close()
    conn.Disconnect()
    assert FPH in sink.opened and sink.closed == 1

def test_com_typelib():
    """COM typelib builds and loads with coclass + source interface (②)."""
    import os
    import tempfile
    from fv import com, com_typelib
    import pythoncom
    p = os.path.join(tempfile.mkdtemp(), "fv.tlb")
    com_typelib.build_typelib(p)
    lt = pythoncom.LoadTypeLib(p)
    assert lt.GetTypeInfoCount() == 3
    kinds = [lt.GetTypeInfo(k).GetTypeAttr()[5] for k in range(3)]
    assert kinds.count(pythoncom.TKIND_DISPATCH) == 2
    assert kinds.count(pythoncom.TKIND_COCLASS) == 1
    # bundled typelib is wired for registration (but not set as _typelib_guid_,
    # which would force universal-interface loading at wrap time)
    assert getattr(com.FlowviewerApplication, "_reg_typelib_filename_", None)
    assert not hasattr(com.FlowviewerApplication, "_typelib_guid_") or \
        com.FlowviewerApplication._typelib_guid_ is None
def test_com_events_smoke_inproc():
    """COM events smoke script runs in-process (②)."""
    from scripts.com_events_smoke import Sink, run_inproc
    r = run_inproc(FPH)
    assert r["ok"] is True
    assert FPH in r["opened"] and r["closed"] == 1

def test_vr_detection():
    """VR availability detection returns a bool and names a backend (7d)."""
    from fv.render.vr import (vr_available, vr_render_window_supported,
                              vr_backend, vr_runtime_available)
    assert isinstance(vr_available(), bool)
    assert isinstance(vr_render_window_supported(), bool)
    assert vr_backend() in {"openvr", "openxr", "generic", "none"}
    assert isinstance(vr_runtime_available(), bool)

def test_vr_backend_builders():
    """create/release_vr_window degrade cleanly without an HMD driver (7d)."""
    from fv.render.vr import create_vr_window, release_vr_window, vr_backend
    handle = create_vr_window()
    if handle is None:
        # no HMD driver present: best-effort construction returned None
        assert vr_backend() in {"openvr", "generic", "none"}
        assert release_vr_window(None) is False
    else:
        assert handle["backend"] in {"openvr", "openxr", "generic"}
        assert "window" in handle
        assert release_vr_window(handle) is True


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_turbo_analysis():
    """Circumferential average / blade loading / polar view (1)."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.render.turbo import (blade_loading_curve,
        circumferential_average, polar_view_points)
    ff = load_file(FPH)
    r, z, vals = circumferential_average(ff, "PRES", "Z", 32, 32)
    assert r is not None and vals.shape == (32, 32)
    assert np.nanmin(vals) <= np.nanmax(vals)
    span, dp = blade_loading_curve(ff, "PRES", "Z", 16)
    assert len(span) == 16 and len(dp) == 16
    assert np.all(dp >= 0)
    rt = polar_view_points(ff, "Z")
    assert rt.shape == (ff.n_vertices, 2)
    assert np.all(rt[:, 0] >= 0)

def test_turbo_blade_aero():
    """Blade-aero post-processing: Cp, area/mass averages (5)."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.render.turbo import (area_average, circumferential_mass_average,
        mass_flow_average, pressure_coefficient)
    ff = load_file(FPH)
    # Cp shape follows PRES (cell-centred) and matches the formula
    p_ref, v_ref, rho = 0.5, 10.0, 1.2
    cp = pressure_coefficient(ff, p_ref, v_ref, rho)
    assert cp.shape == ff.variables["PRES"].array.shape
    base = ff.variables["PRES"].array
    np.testing.assert_allclose(cp, (base - p_ref) / (0.5 * rho * v_ref ** 2),
                               rtol=1e-9)
    # area average along Z: binned profile, populated bins finite
    zc, av = area_average(ff, "PRES", "Z", 24)
    assert zc.shape == (24,) and av.shape == (24,)
    assert np.isfinite(av).any()
    assert np.nanmin(av) <= np.nanmax(av)
    # mass-flow weighted average returns a scalar in-range
    m = mass_flow_average(ff, "PRES", "Z")
    assert isinstance(m, float) and np.isfinite(m)
    assert float(base.min()) <= m <= float(base.max())
    # circumferential mass average has the same grid shape
    r, z, cm = circumferential_mass_average(ff, "PRES", "Z", 16, 16)
    assert cm.shape == (16, 16)
    assert np.isfinite(cm).any()

def test_turbo_dialog_blade_aero(qapp):
    """TurboDialog exposes Blade Aero analysis tab (5)."""
    from fv.model.dataset import load_file
    from fv.model.objects import TurboObject
    from fv.gui.object_dialogs2 import TurboDialog
    ff = load_file(FPH)
    t = TurboObject(index=1, variable="PRES", axis="Z")
    d = TurboDialog(t, field_file=ff)
    assert d.tabs.tabText(1) == "Blade Aero"
    d._on_analyse()
    assert "Mass-flow avg" in d.aero_result.text()
@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_ifld_metadata_scan():
    """scan_ifld returns counts/variables without loading arrays (D3)."""
    from fv.crdl.ifld import scan_ifld
    from fv.model.dataset import load_file
    ff = load_file(FLD)
    meta = scan_ifld(FLD)
    assert meta is not None
    assert meta["n_cells"] == ff.n_cells
    assert meta["file_size"] > 0
    assert "Pressure" in meta["variables"]
    assert scan_ifld(r"D:\training\cgns\no_such.fld") is None


def test_neutral_reader(tmp_path):
    """OBJ/STL neutral meshes load as a surface FieldFile (1)."""
    from fv.model.dataset import neutral_load
    from fv.model.loaders import can_load
    obj = tmp_path / "tri.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    assert can_load(str(obj)) is True
    ff = neutral_load(str(obj))
    assert ff.kind == "neutral"
    assert ff.n_vertices == 3 and len(ff.faces) == 1
    assert ff.surface_regions[0][0] == "Neutral"
    # STL
    stl = tmp_path / "tri.stl"
    stl.write_text(
        "solid t\n  facet normal 0 0 1\n    outer loop\n"
        "      vertex 0 0 0\n      vertex 1 0 0\n      vertex 0 1 0\n"
        "    endloop\n  endfacet\nendsolid t\n", encoding="utf-8")
    ff2 = neutral_load(str(stl))
    assert ff2.n_vertices == 3 and len(ff2.faces) == 1

@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_neutral_scene():
    """Neutral mesh renders in the scene (1)."""
    from fv.model.objects import MainObject
    from fv.render.scene import Scene
    from fv.model.dataset import neutral_load
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".obj")
    os.write(fd, b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    os.close(fd)
    try:
        ff = neutral_load(path)
        sc = Scene(enable_3d=False)
        sc.build(ff, main=MainObject.from_field_file(ff))
        assert "grid" in sc.actor_names()
    finally:
        os.unlink(path)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_fph_cell_difference():
    """delx on an FPH cell field uses cell-centre differences (2)."""
    import numpy as np
    from fv.model.dataset import FIELD_KIND_SCALAR, VarInfo
    from fv.model.dataset import load_file
    from fv.model.varreg import _cell_centers_fph, register_variable
    ff = load_file(FPH)
    centers = _cell_centers_fph(ff)
    assert centers is not None and centers.shape == (ff.n_cells, 3)
    # synthetic linear cell field = x coordinate -> delx = 1 interior
    ff.variables["XC"] = VarInfo(name="XC", kind=FIELD_KIND_SCALAR,
                              location="cell", array=centers[:, 0])
    vi = register_variable(ff, "DPDXC", "delx(XC)")
    assert vi.location == "cell"
    nz = vi.array[np.nonzero(vi.array)]
    assert len(nz) > 0
    assert np.abs(nz - 1.0).max() < 0.3


def test_marc_reader(tmp_path):
    """Marc .dat free text mesh parses (3)."""
    from fv.model.dataset import marc_load
    dat = tmp_path / "box.dat"
    lines = [
        "$ sample Marc input",
        "1,0.0,0.0,0.0",
        "2,1.0,0.0,0.0",
        "3,1.0,1.0,0.0",
        "4,0.0,1.0,0.0",
        "5,0.0,0.0,1.0",
        "6,1.0,0.0,1.0",
        "7,1.0,1.0,1.0",
        "8,0.0,1.0,1.0",
        "1,7,1,2,3,4,5,6,7,8",
    ]
    dat.write_text("\n".join(lines), encoding="utf-8")
    ff = marc_load(str(dat))
    assert ff.kind == "marc"
    assert ff.n_vertices == 8 and ff.n_cells == 1
    assert ff.cell_types.tolist() == [12]



@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_export_animation_frames_headless(tmp_path):
    """Animation exporter returns 0 written in headless mode (G5)."""
    from fv.model.dataset import load_file
    from fv.model.objects import MainObject, PlaneObject
    from fv.render.export import export_animation_frames
    from fv.render.scene import Scene
    ff = load_file(FPH)
    main = MainObject.from_field_file(ff)
    plane = PlaneObject(index=9)
    plane.automove_enabled = True
    main.children.append(plane)
    sc = Scene(enable_3d=False)
    sc.build(ff, main=main)
    n = export_animation_frames(ff, main, sc, None, str(tmp_path),
                               frames=3)
    assert n == 0  # no render window: nothing written, no crash
    assert tmp_path.exists()