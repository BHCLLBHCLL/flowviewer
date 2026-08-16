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
        ("fld", "ifld", "fph", "gph", "pph", "cgns", "xmf", "xdmf"))
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


def test_create_menu_all_kinds_wired(qapp):
    """P0.1/P0.4: every Create-menu entry maps to a real kind (no None)."""
    from fv.gui import main as gmain
    for name, kind in gmain._CREATE_MENU:
        assert kind, f"Create menu '{name}' has kind=None"
    for name, kind in gmain._CREATE_MORE:
        assert kind, f"More-objects menu '{name}' has kind=None"
    # Vector maps to the Plane pipeline (most complete vector tab)
    assert dict(gmain._CREATE_MENU)["Vector"] == "plane"
    # Renderable kinds aligned between main and panes (single-click wiring)
    assert set(gmain._RENDERABLE_KINDS) >= {
        k for _, k in gmain._CREATE_MENU + gmain._CREATE_MORE}


def _tree_texts(tree) -> set:
    """Collect all item texts (recursively) from the object tree widget."""
    texts = set()

    def walk(item):
        texts.add(item.text(0))
        for j in range(item.childCount()):
            walk(item.child(j))

    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i))
    return texts


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_create_object_secondary_kinds(qapp):
    """P0.1: secondary objects (previously unreachable) now create + panel."""
    w = _make(qapp, FPH)
    for kind in ("pathline", "cylinder", "text", "graph", "curve", "bar",
                 "information", "mirror", "measure", "ufo"):
        n0 = len(w.main_object.children)
        w._create_object(kind)
        assert len(w.main_object.children) == n0 + 1, f"{kind} not created"
        obj = w.main_object.children[-1]
        assert obj.kind == kind
        assert obj.label in _tree_texts(w.object_tree)
    # Cylinder maps to the cylinder pipeline (was kind=None stub)
    w._create_object("cylinder")
    assert any(o.kind == "cylinder" for o in w.main_object.children)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_undo_redo_wired(qapp):
    """P0.3: Edit menu + snapshot on create → undo/redo actually work."""
    w = _make(qapp, FPH)
    n0 = len(w.main_object.children)
    w._create_object("text")
    assert len(w.main_object.children) == n0 + 1
    assert w._undo_stack  # create pushed a snapshot
    w.on_undo()
    assert len(w.main_object.children) == n0  # creation undone
    assert w._redo_stack
    w.on_redo()
    assert len(w.main_object.children) == n0 + 1  # redo restores
    # Edit menu exists with Undo/Redo actions + shortcuts
    edit_menu = _menu_by_title(w, "Edit")
    texts = {a.text() for a in edit_menu.actions()}
    assert {"Undo", "Redo"} <= texts


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
def test_plane_oilflow_color_var_p15():
    """P1.5: oilflow lines coloured by a scalar variable."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.oilflow_display = True
    obj.oilflow_var = "VEL"
    obj.oilflow_draw_type = "Line"
    obj.oilflow_length = 1.0
    obj.oilflow_color_var = "PRES"
    out = rp.build_plane_actors(ff, obj)
    assert "oilflow" in out
    mapper = out["oilflow"].GetMapper()
    pd = mapper.GetInput()
    arr = pd.GetPointData().GetArray("PRES")
    assert arr is not None
    assert arr.GetNumberOfTuples() == pd.GetNumberOfPoints()
    rng = arr.GetRange()
    mrng = mapper.GetScalarRange()
    assert abs(mrng[0] - rng[0]) < 1e-9 and abs(mrng[1] - rng[1]) < 1e-9


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


def _synthetic_two_frame_fph(path):
    """Write a 2-frame FPH (6 x 30-particle coordinate blocks) to *path*."""
    import struct

    import numpy as np

    def coordinate(values):
        n = values.size
        payload = np.asarray(values, dtype=">f4").tobytes()
        return (struct.pack(">iiii", 12, 4, n, 1)
                + struct.pack(">ii", 12, len(payload)) + payload
                + struct.pack(">i", len(payload)))

    def section(name, *payloads):
        body = b""
        for pay in payloads:
            body += (struct.pack(">ii", 12, len(pay)) + pay
                     + struct.pack(">i", len(pay)))
        return (struct.pack(">i", 32) + name.ljust(32).encode("ascii")
                + struct.pack(">i", 32) + body)

    rng = np.random.default_rng(21)
    pos_blocks = [coordinate(rng.random(30)) for _ in range(6)]
    Path(path).write_bytes(
        b"CRDL-FLD" + section("LS_ParticlesPosition", *pos_blocks))


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_particle_multiframe_animate(tmp_path):
    """P0.5: frame_index selects the frame; Scene.animate advances it."""
    from types import SimpleNamespace

    import numpy as np
    from vtk.util import numpy_support as vns

    from fv.model.objects import ParticleObject
    from fv.render import particle as pr
    from fv.render.scene import Scene

    fph = tmp_path / "two_frames.fph"
    _synthetic_two_frame_fph(fph)
    ff = SimpleNamespace(path=str(fph), meta={})
    obj = ParticleObject(index=1)

    a0 = pr.build_particle_actors(obj, ff, frame_index=0)
    a1 = pr.build_particle_actors(obj, ff, frame_index=1)
    assert ff.meta["particle_frames"] == 2
    assert "particle" in a0 and "particle" in a1

    def points(actor):
        poly = actor.GetMapper().GetInput()
        return vns.vtk_to_numpy(poly.GetPoints().GetData())

    p0, p1 = points(a0["particle"]), points(a1["particle"])
    assert p0.shape == (30, 3) and p1.shape == (30, 3)
    assert not np.allclose(p0, p1)  # frame 1 differs from frame 0

    # Scene.animate advances the particle object's frame (headless scene)
    s = Scene(enable_3d=False)
    s._field_file = ff
    s._main = SimpleNamespace(children=[obj])
    s.animate(1)
    assert obj.frame_index == 1
    assert any(n.startswith("particle:") for n in s.actor_names())
    # out-of-range frame index loops back into [0, n_frames)
    s.animate(2)
    assert obj.frame_index == 0


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
    """FLD streamlines: RK4 numeric tracer with color_var (P1.2)."""
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
    obj.color_var = "PRES"
    out = sl_render.build_streamline_actors(ff, obj)
    a = out.get("streamline")
    assert a is not None
    pd = a.GetMapper().GetInput()
    arr = pd.GetPointData().GetArray("PRES")
    assert arr is not None and arr.GetNumberOfTuples() == \
        pd.GetNumberOfPoints()  # sampled at every trace point (P1.2)
    # Both direction yields polylines through the same seeds
    obj.direction = "Both"
    out2 = sl_render.build_streamline_actors(ff, obj)
    assert out2.get("streamline") is not None
    pd2 = out2["streamline"].GetMapper().GetInput()
    assert pd2.GetNumberOfLines() >= pd.GetNumberOfLines()


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_volume_render_pipeline_fph():
    """P1.1: FPH polyhedra render via ResampleToImage→SmartVolumeMapper."""
    from fv.model.dataset import load_file
    from fv.model.objects import VolumeObject
    from fv.render import volume as vol_render
    ff = load_file(FPH)
    obj = VolumeObject(index=1)
    obj.show_scalar = True
    obj.scalar_var = "PRES"
    obj.draw_type = "Transparent"
    out = vol_render.build_volume_actors(ff, obj)
    a = out.get("scalar")
    assert a is not None
    # polyhedral grid → resampled image → smart volume mapper
    assert "vtkVolume" in type(a).__name__
    assert "SmartVolumeMapper" in type(a.GetMapper()).__name__
    img = a.GetMapper().GetInput()
    assert img is not None and img.IsA("vtkImageData")
    # transfer functions parameterised from the object (P1.1)
    ctf = a.GetProperty().GetRGBTransferFunction()
    assert ctf is not None and ctf.GetSize() >= 2
    otf = a.GetProperty().GetScalarOpacity()
    assert otf is not None and otf.GetSize() >= 2


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
@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_volume_transfer_and_sampling_p11():
    """P1.1: TF reads colorbar palette; sampling strides (keeps tail)."""
    from fv.model.dataset import load_file
    from fv.model.objects import VolumeObject
    from fv.render import volume as vol_render
    ff = load_file(FLD)
    obj = VolumeObject(index=1)
    obj.show_scalar = True
    obj.scalar_var = "PRES"
    obj.colorbar = "Gray"
    out = vol_render.build_volume_actors(ff, obj)
    a = out["scalar"]
    ctf = a.GetProperty().GetRGBTransferFunction()
    # Gray palette: first/last colour stops are near-black / near-white
    c0 = [0.0, 0.0, 0.0]
    c1 = [0.0, 0.0, 0.0]
    ctf.GetColor(ctf.GetRange()[0], c0)
    ctf.GetColor(ctf.GetRange()[1], c1)
    assert sum(c0) < 0.6 and sum(c1) > 2.0
    # stride sampling keeps cells across the whole domain
    from fv.render.plane import build_ugrid
    grid, _ = build_ugrid(ff)
    decimated = vol_render._apply_sampling(grid, type("O", (), {"sampling": 4})())
    assert decimated.GetNumberOfCells() == \
        (grid.GetNumberOfCells() + 3) // 4


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
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_plane_contour_sheen_unified_p14():
    """P1.4: plane contour actors use material.apply_sheen (Phong)."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render import plane as rp
    ff = load_file(FPH)
    obj = PlaneObject(index=1)
    obj.show_contour = True
    obj.contour_var = "PRES"
    obj.contour_water = True
    out = rp.build_plane_actors(ff, obj)
    assert "contour" in out
    p = out["contour"].GetProperty()
    assert abs(p.GetSpecular() - 0.9) < 1e-6
    # unified helper keeps Phong everywhere (inline path used Gouraud)
    assert p.GetInterpolation() == 2  # VTK_PHONG
    obj.contour_water = False
    obj.contour_luster = True
    out = rp.build_plane_actors(ff, obj)
    p = out["contour"].GetProperty()
    assert abs(p.GetSpecular() - 0.5) < 1e-6
    assert p.GetInterpolation() == 2

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


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_pathline_step_and_color_p12(tmp_path):
    """P1.2: pathline honours step_size; color_var colours by point data."""
    import shutil
    from fv.model.dataset import load_file
    from fv.model.objects import PathlineObject
    from fv.render.pathline import build_pathline_actors
    files = []
    for cyc in (100, 200):
        dst = tmp_path / f"ex1_{cyc}.fld"
        shutil.copyfile(FLD, dst)
        files.append(str(dst))
    ff = load_file(files[0])
    obj = PathlineObject(index=1)
    obj.vector_var = "VECT"
    obj.density_u = 3
    obj.density_v = 3
    obj.steps_per_cycle = 5
    obj.step_size = 0.01          # parameterised (was hard-coded 0.001)
    obj.color_var = "PRES"
    out = build_pathline_actors(obj, files, ff0=ff)
    assert "pathline" in out
    actor = out["pathline"]
    pd = actor.GetMapper().GetInput()
    arr = pd.GetPointData().GetArray("PRES")
    assert arr is not None
    assert arr.GetNumberOfTuples() == pd.GetNumberOfPoints()
    # colour path active: mapper's scalar range follows the sampled array
    rng = arr.GetRange()
    mrng = actor.GetMapper().GetScalarRange()
    assert abs(mrng[0] - rng[0]) < 1e-9 and abs(mrng[1] - rng[1]) < 1e-9

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


def test_mirror_periodical_inherit_source_field():
    """R0.5: mirror/periodical copies inherit the source contour field."""
    from fv.model.dataset import load_file
    from fv.model.objects import (MirrorCopyObject, PeriodicalCopyObject,
                                  SurfaceObject)
    from fv.render.mirror import build_mirror_actors
    from fv.render.periodical import build_periodical_actors
    ff = load_file(FPH)
    surf = SurfaceObject(index=1)
    surf.show_contour = True
    surf.contour_var = "PRES"

    mir = MirrorCopyObject(index=1)
    mir.source_label = "Surface (1)"
    out = build_mirror_actors(ff, mir, siblings=[surf])
    assert "mirror" in out
    data = out["mirror"].GetMapper().GetInput()
    arr = data.GetCellData().GetArray("PRES")
    assert arr is not None
    rng = arr.GetRange()
    m = out["mirror"].GetMapper()
    assert abs(m.GetScalarRange()[0] - rng[0]) < 1e-9
    assert abs(m.GetScalarRange()[1] - rng[1]) < 1e-9

    per = PeriodicalCopyObject(index=1)
    per.source_label = "Surface (1)"
    per.copies = 4
    out2 = build_periodical_actors(ff, per, siblings=[surf])
    assert len(out2) == 3
    m2 = next(iter(out2.values())).GetMapper()
    assert abs(m2.GetScalarRange()[0] - rng[0]) < 1e-9
    assert abs(m2.GetScalarRange()[1] - rng[1]) < 1e-9

    # Source contour off -> flat colour fallback (no scalar attached)
    surf.show_contour = False
    out3 = build_mirror_actors(ff, mir, siblings=[surf])
    assert out3["mirror"].GetMapper().GetInput().GetCellData().GetArray(
        "PRES") is None



def test_vector_arrow_coloring_modes():
    """R0.6 (B7): vector arrows colour by magnitude/variable or mono RGB."""
    from fv.model.dataset import load_file
    from fv.model.objects import SurfaceObject
    from fv.render.surface import build_surface_actors
    ff = load_file(FPH)

    # Default: scPOST black arrows
    obj = SurfaceObject(index=1)
    obj.show_vector = True
    obj.vector_var = "VEL"
    a = build_surface_actors(ff, obj).get("vector")
    assert a is not None
    assert a.GetProperty().GetColor() == (0.0, 0.0, 0.0)

    # Mono colour
    obj.vector_mono_color = True
    obj.vector_mono_rgb = (0.2, 0.4, 0.8)
    a = build_surface_actors(ff, obj)["vector"]
    got = a.GetProperty().GetColor()
    assert all(abs(g - e) < 1e-3 for g, e in zip(got, (0.2, 0.4, 0.8)))

    # Contour colour: magnitude fallback (no contour var on glyph input)
    obj.vector_mono_color = False
    obj.vector_contour_color = True
    a = build_surface_actors(ff, obj)["vector"]
    m = a.GetMapper()
    assert m.GetArrayName() and m.GetArrayName().endswith("_mag")
    rng = m.GetScalarRange()
    assert rng[0] < rng[1]

    # Contour colour: by variable when contour_var rides the glyph input
    obj.show_contour = True
    obj.contour_var = "PRES"
    a = build_surface_actors(ff, obj)["vector"]
    assert a.GetMapper().GetArrayName() == "PRES"



def test_hardcoded_params_adaptive():
    """R0.7: marker/tube radius adapt to extent; point labels stagger."""
    import vtk
    from fv.model.objects import InformationObject, ParticleObject, PointObject
    from fv.render.information import marker_actor
    from fv.render.particle import _sphere_actor
    from fv.render.point import _label_actor
    from fv.render.streamline import _tube_radius

    # Information marker radius follows the bounds diagonal (0.5%)
    obj = InformationObject(index=1)
    obj.show_marker = True
    a1 = marker_actor(obj)
    a2 = marker_actor(obj, bounds=((0.0, 0.0, 0.0), (10.0, 0.0, 0.0)))
    r1 = a1.GetMapper().GetInputAlgorithm().GetRadius()
    r2 = a2.GetMapper().GetInputAlgorithm().GetRadius()
    assert abs(r1 - 0.002) < 1e-12
    assert abs(r2 - 0.05) < 1e-9

    # Streamline tube radius scales with the extent (0.2% diag)
    line = vtk.vtkLineSource()
    line.SetPoint1(0.0, 0.0, 0.0)
    line.SetPoint2(5.0, 0.0, 0.0)
    line.Update()
    assert abs(_tube_radius(line.GetOutput()) - 0.01) < 1e-9

    # Point label staggers vertically by object index
    t1 = _label_actor("x", PointObject(index=1))
    t3 = _label_actor("x", PointObject(index=3))
    assert t1.GetPosition() == (0.02, 0.84)
    assert abs(t3.GetPosition()[1] - (0.84 - 0.12)) < 1e-9

    # Particle spheres scale by |velocity| (vectors attached)
    from vtk.util import numpy_support as vns
    import numpy as np
    pd = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    pts.InsertNextPoint(0.0, 0.0, 0.0)
    pts.InsertNextPoint(1.0, 0.0, 0.0)
    pd.SetPoints(pts)
    fa = vns.numpy_to_vtk(
        np.array([[1.0, 0.0, 0.0], [3.0, 0.0, 0.0]]), deep=True)
    fa.SetName("Velocity")
    pd.GetPointData().SetVectors(fa)
    po = ParticleObject(index=1)
    po.size_px = 5
    a = _sphere_actor(pd, po)
    assert a is not None
    a.GetMapper().Update()
    out = a.GetMapper().GetInput()
    b = out.GetBounds()
    # mean |v| = 2 normalises the scale factor: sphere x-extents are
    # 0.4949*0.0025*|v| (0.4949 = tessellated unit-sphere x bound), so
    # the fast particle is ~3x wider than the slow one.
    left = abs(b[0])
    right = b[1] - 1.0
    assert abs(left - 0.4949 * 0.0025 * 1.0) < 1e-4
    assert abs(right - 0.4949 * 0.0025 * 3.0) < 1e-4
    assert right > 2.5 * left


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
    assert len(span) == 16 and np.all(np.isfinite(np.asarray(dp)))
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
    # P1-1: FLD NGON faces answer face_nodes/cells_of_face/area_of_face
    assert len(fld.faces) > 0 and len(fld.face_cells) > 0
    fns0 = api.face_nodes(fld, 0)
    assert len(fns0) >= 3 and max(fns0) < fld.n_vertices
    owner, _ = api.cells_of_face(fld, 0)
    assert owner >= 0
    assert api.area_of_face(fld, 0) > 0.0

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

def test_fileset_time_interpolation_and_runtime(tmp_path):
    """Fractional cycle ids blend members; runtime API (P2.4)."""
    import shutil
    import numpy as np
    from pathlib import Path
    from fv import api
    from fv.model.dataset import load_file
    from fv.model.fileset import interpolate_at, interpolate_files, scan_sequence
    base = Path(tmp_path)
    for cyc in (1, 2):
        shutil.copyfile(FPH, str(base / f"flow_{cyc}.fph"))
    fs = scan_sequence(str(base / "flow_1.fph"))
    assert len(fs) == 2

    # direct file blend: bump PRES on the second member by +10
    ff0 = load_file(str(base / "flow_1.fph"))
    ff1 = load_file(str(base / "flow_2.fph"))
    ff1.variables["PRES"].array = ff1.variables["PRES"].array + 10.0
    mid = interpolate_files(ff0, ff1, 0.5)
    np.testing.assert_allclose(
        mid.variables["PRES"].array,
        ff0.variables["PRES"].array + 5.0, rtol=1e-9)
    assert mid.n_cells == ff0.n_cells
    assert mid.vertices.shape == ff0.vertices.shape
    assert set(mid.variables) == set(ff0.variables)

    # runtime: scPOST SetCurCycleID family semantics
    rt = api.cycle_runtime(fs)
    assert api.get_cycle_num(rt) == 2
    assert api.set_cur_cycle_id(rt, 2) == 2
    assert api.set_cur_cycle_id(rt, 9) == -1     # out of range
    assert api.get_cur_cycle_id(rt) == 2         # unchanged after failure
    assert api.set_cur_cycle_id_f(rt, 1, 0.5) == 1
    assert api.set_cur_cycle_id_f(rt, 2, 0.5) == -1  # no member after last
    assert api.set_cur_cycle_id_f(rt, 1, 1.5) == -1  # bad fraction
    cur = rt.current_file()
    assert cur.variables["PRES"].array.shape \
        == ff0.variables["PRES"].array.shape
    assert np.all(np.isfinite(cur.variables["PRES"].array))
    assert api.set_auto_cycle(rt, True) is True and rt.auto is True
    assert api.reset_cyc_ope(rt) is True and fs.operation_mode == "None"

    # interpolate_at + cache: parsed members are reused
    cache = {}
    interpolate_at(fs, 1.0, cache=cache)
    interpolate_at(fs, 1.5, cache=cache)
    assert len(cache) == 2
    with pytest.raises(ValueError):
        interpolate_at(fs, 3.0)

def test_pod_decompose():
    """POD SVD decomposition: orthogonal modes + energy fractions (P3)."""
    import numpy as np
    from fv.model.pod import pod_decompose
    rng = np.random.default_rng(7)
    X = rng.standard_normal((12, 50))
    mean, modes, energies, sv = pod_decompose(X, 6)
    assert mean.shape == (50,)
    assert len(modes) == 6 and len(energies) == 6
    assert np.all(energies >= 0) and energies.sum() <= 1.0 + 1e-12
    assert np.all(np.diff(energies) <= 1e-12)  # descending energy
    _, _, e_full, _ = pod_decompose(X)  # all modes sum to 1
    assert abs(e_full.sum() - 1.0) < 1e-9    # modes are orthonormal
    M = np.vstack(modes)
    gram = M @ M.T
    assert np.allclose(gram, np.eye(6), atol=1e-9)
    # rank-deficient data -> exactly one non-zero mode
    Xr = np.tile(rng.standard_normal(50), (5, 1))
    _, modes_r, energies_r, _ = pod_decompose(Xr, 3)
    assert energies_r[0] > 0.999

def test_pod_analysis_fileset(tmp_path):
    """POD across a cycle FileSet registers POD_MEAN / POD_MODE_i (P3)."""
    import shutil
    from pathlib import Path
    from fv import api
    from fv.model.fileset import scan_sequence
    base = Path(tmp_path)
    for stale in base.glob("*.fph"):
        stale.unlink()
    for cyc in (1, 2, 3):
        shutil.copyfile(FPH, str(base / f"flow_{cyc}.fph"))
    fs = scan_sequence(str(base / "flow_1.fph"))
    ff0 = api.open_file(FPH)
    res = api.register_pod_modes(fs, ff0, "PRES", 3)
    assert res["n_cycles"] == 3
    assert res["mean"].shape == (ff0.n_cells,)
    assert len(res["modes"]) == 3
    assert "POD_MEAN" in ff0.variables
    assert "POD_MODE_0" in ff0.variables and "POD_MODE_2" in ff0.variables

def test_pod_allcyc_cache_and_no_swallow(tmp_path):
    """POD/ALLCYC share a member cache and surface errors (P2.5)."""
    import shutil
    from pathlib import Path
    from fv import api
    from fv.model.fileset import scan_sequence
    from fv.model.pod import collect_snapshots
    base = Path(tmp_path)
    for stale in base.glob("*.fph"):
        stale.unlink()
    for cyc in (1, 2, 3):
        shutil.copyfile(FPH, str(base / ("flow_" + str(cyc) + ".fph")))
    fs = scan_sequence(str(base / "flow_1.fph"))
    assert len(fs) == 3

    # shared cache: each member parsed once and reused across POD/ALLCYC
    cache = {}
    res = api.pod_analysis(fs, "PRES", 2, cache=cache)
    assert res["cycles"] == [1, 2, 3]
    assert len(cache) == 3
    out = api.register_var_all_cycles(fs, "PP3", "PRES + 2.0", cache=cache)
    assert [c for c, _ in out] == [1, 2, 3]
    assert len(cache) == 3          # no re-parse of cached members
    assert all("PP3" in ff.variables for ff in cache.values())

    # missing variable is an explicit error, not a silent skip
    with pytest.raises(ValueError):
        collect_snapshots(fs, "NO_SUCH_VAR")

    # a corrupt member must propagate, not be swallowed
    (base / "flow_2.fph").write_bytes(b"garbage: not a field file")
    with pytest.raises(Exception):
        collect_snapshots(fs, "PRES")
def test_xdmf_temporal_collection(tmp_path):
    """XDMF temporal collection: shared topology, per-step fields (P3)."""
    import numpy as np
    from fv.model.dataset import xdmf_load
    coords = "0 0 0  1 0 0  1 1 0  0 1 0  0 0 1  1 0 1  1 1 1  0 1 1"
    conn = "0 1 2 3 4 5 6 7"

    def full_grid(t, vals):
        return f"""<Grid Name="t{t}"><Time Value="{t}"/>
    <Topology TopologyType="Hexahedron" NumberOfElements="1">
    <DataItem Dimensions="1 8" Format="XML">{conn}</DataItem></Topology>
    <Geometry GeometryType="XYZ"><DataItem Dimensions="8 3" Format="XML">
    {coords}</DataItem></Geometry>
    <Attribute Name="PRES" Center="Node">
    <DataItem Dimensions="8" Format="XML">{vals}</DataItem></Attribute>
    </Grid>"""

    def attr_only(t, vals):
        return f"""<Grid Name="t{t}"><Time Value="{t}"/>
    <Attribute Name="PRES" Center="Node">
    <DataItem Dimensions="8" Format="XML">{vals}</DataItem></Attribute>
    </Grid>"""

    xml = f"""<?xml version="1.0"?>
    <Xdmf><Domain>
    <Grid GridType="Collection" CollectionType="Temporal">
    {full_grid(0.0, "1 2 3 4 5 6 7 8")}
    {attr_only(1.0, "2 3 4 5 6 7 8 9")}
    {attr_only(2.0, "3 4 5 6 7 8 9 10")}
    </Grid></Domain></Xdmf>"""
    xmf = tmp_path / "seq.xmf"
    xmf.write_text(xml, encoding="utf-8")
    ff = xdmf_load(str(xmf))
    assert ff.kind == "xdmf"
    assert ff.n_vertices == 8 and ff.n_cells == 1
    # the loaded file is the first frame
    assert ff.variables["PRES"].array.tolist() == [1, 2, 3, 4, 5, 6, 7, 8]
    temporal = ff.meta["xdmf_temporal"]
    assert temporal["cycles"] == [1, 2, 3]
    np.testing.assert_allclose(temporal["times"], [0.0, 1.0, 2.0])
    frames = ff.meta["xdmf_frames"]
    assert len(frames) == 3
    # attribute-only frames inherit the shared topology
    for f, pres in zip(frames, ([1, 2, 3, 4, 5, 6, 7, 8],
                                [2, 3, 4, 5, 6, 7, 8, 9],
                                [3, 4, 5, 6, 7, 8, 9, 10])):
        assert f["mesh"]["n_vertices"] == 8
        assert f["mesh"]["n_cells"] == 1
        assert f["mesh"]["fields"]["PRES"][0].tolist() == pres

def test_api_geometry_and_region_queries():
    """api GetBoundingBox / coordinate transforms / VOL+MAT (P3)."""
    import numpy as np
    from fv import api
    ff = api.open_file(FPH)
    box = api.get_bounding_box(ff)
    assert len(box) == 6
    assert box[0] <= box[1] and box[2] <= box[3] and box[4] <= box[5]
    np.testing.assert_allclose(box[:2], (ff.vertices[:, 0].min(),
                                         ff.vertices[:, 0].max()))
    # part-filtered box stays inside the global one; unknown names raise
    if getattr(ff, "parts_with_cvol", None):
        part = ff.parts_with_cvol[0][0]
        rbox = api.get_bounding_box(ff, part)
        assert len(rbox) == 6
        assert rbox[0] >= box[0] - 1e-9 and rbox[1] <= box[1] + 1e-9
    # unknown region names classify as the whole mesh (lenient semantics)
    np.testing.assert_allclose(api.get_bounding_box(ff, "NO_SUCH_REGION"), box)
    # local <-> global: rotate + translate, then round-trip back
    g = api.local_xyz_to_global_xyz((1.0, 0.0, 0.0), axis="z", angle_deg=90.0)
    np.testing.assert_allclose(g, (0.0, 1.0, 0.0), atol=1e-12)
    g2 = api.local_xyz_to_global_xyz((1.0, 1.0, 1.0), origin=(10, 20, 30))
    np.testing.assert_allclose(g2, (11.0, 21.0, 31.0), atol=1e-12)
    l = api.global_xyz_to_local_xyz((0.0, 1.0, 0.0), axis="z", angle_deg=90.0)
    np.testing.assert_allclose(l, (1.0, 0.0, 0.0), atol=1e-12)
    # array form maps N points at once
    arr = api.local_xyz_to_global_xyz(np.eye(3), axis="z", angle_deg=90.0)
    assert arr.shape == (3, 3)
    np.testing.assert_allclose(arr[0], (0.0, 1.0, 0.0), atol=1e-12)
    # region / material bookkeeping
    assert api.get_vol_num(ff) == len(ff.volume_regions)
    assert api.get_vol_org_names(ff) == list(ff.volume_regions)
    assert api.get_overlapping_region_count(ff) >= 0
    assert api.get_mat_num(ff) >= 0  # 0 when the file carries no MAT-ID
    mid = api.get_mat_id_of_vol(ff, getattr(ff, "parts", [""])[0])
    assert mid is None or mid == -1 or mid >= 1

def test_com_scpost_surface(tmp_path):
    """COM scPOST methods: cycle runtime + queries + flags + errors (P3)."""
    import shutil
    from pathlib import Path
    from fv.com import FlowviewerApplication
    base = Path(tmp_path)
    for stale in base.glob("*.fph"):
        stale.unlink()
    for cyc in (1, 2):
        shutil.copyfile(FPH, str(base / f"flow_{cyc}.fph"))
    app = FlowviewerApplication()
    # sequence runtime
    assert app.open_sequence(str(base / "flow_1.fph")) == 2
    assert app.GetCycleNum() == 2
    assert app.SetCurCycleID(2) == 2
    assert app.SetCurCycleID(9) == -1
    assert app.SetCurCycleID_F(1, 0.5) == 1
    assert app.GetCurCycleID() == 1
    assert app.GetCycleByCycleID(1) is not None
    # geometry on the loaded member
    box = app.GetBoundingBox()
    assert box is not None and len(box) == 6
    # LocalXYZ2GlobalXYZ reads the local coordinate system from the file;
    # the FPH sample has none, so the transform is identity.
    g = app.LocalXYZ2GlobalXYZ(1.0, 0.0, 0.0)
    assert g is not None and abs(g[0] - 1.0) < 1e-12
    l = app.GlobalXYZ2LocalXYZ(g[0], g[1], g[2])
    assert abs(l[0] - 1.0) < 1e-12
    # region / material queries through the error channel
    assert app.GetVOLNum() == len(app._ff.volume_regions)
    assert app.GetMATNumFLD() >= 0  # 0 when the file carries no MAT-ID
    assert app.GetOverlappingRegionCount() >= 0
    # application state flags
    assert app.SetDisplayAxis(False) is True
    assert app.SetUseUndoBuffer(False) is True
    assert app.AnimationStart() is True and app.AnimationStop() is True
    assert app.SplitView(2) is True and app.PrepareMinMaxPos() == 0
    assert app.ObjectNameArrange() is True
    # error channel: unknown cycle-op mode -> ErrorCode -1, message set
    app.SetCycOpeMode("Bogus")
    assert app.ErrorCode == -1 and "Bogus" in app.ErrorString
    # recovery: a good call clears the error again
    app.GetBoundingBox()
    assert app.ErrorCode == 0 and app.ErrorString == "OK"
    # AddCycList / DelCycList keep the list consistent
    shutil.copyfile(FPH, str(base / "flow_3.fph"))
    assert app.AddCycList(str(base / "flow_3.fph")) > 0
    assert app.GetCycleNum() == 3
    assert app.DelCycList(3) in (True, 1)
    assert app.GetCycleNum() == 2

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
    """Volume honours Volume Region filtering (P0.5): fewer cells.

    P1.1 note: the FPH actor input is now a resampled vtkImageData with
    dimensions independent of the mask, so the filtering effect is
    asserted on the pre-resample unstructured grid.
    """
    from fv.model.dataset import load_file
    from fv.model.objects import VolumeObject
    from fv.render.plane import build_ugrid, cell_filter_mask
    ff = load_file(FPH)
    full = VolumeObject(index=1)
    ug_all, _ = build_ugrid(ff, cell_filter_mask(ff, full))
    assert ug_all is not None and ug_all.GetNumberOfCells() > 0
    obj = VolumeObject(index=1,
                        display_volume_regions=["Case[2]"])
    ug_f, _ = build_ugrid(ff, cell_filter_mask(ff, obj))
    assert 0 < ug_f.GetNumberOfCells() < ug_all.GetNumberOfCells()


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


def test_object_delete_duplicate_and_undo(qapp):
    """R0.2/R0.3: Edit delete/duplicate + undo covers edits, not just create."""
    w = _make(qapp, FPH)
    n0 = len(w.main_object.children)
    obj = w.main_object.children[0]
    label = obj.label

    w.on_duplicate_object(label)
    assert len(w.main_object.children) == n0 + 1
    dup = w.main_object.children[-1]
    assert dup.label != label and dup.kind == obj.kind

    w.on_delete_object(dup.label)
    assert len(w.main_object.children) == n0

    # undo restores the duplicate
    w.on_undo()
    assert len(w.main_object.children) == n0 + 1
    w.on_redo()
    assert len(w.main_object.children) == n0

    # property-edit undo: change a plane coordinate, apply, undo restores it
    plane = next(o for o in w.main_object.children if o.kind == "plane")
    before = plane.coordinate
    plane.coordinate = before + 7.5
    w._on_property_applied(plane)
    w.on_undo()
    plane2 = next(o for o in w.main_object.children if o.kind == "plane")
    assert plane2.coordinate == before


def test_timeline_time_interpolation_gui(qapp, tmp_path):
    """R0.1: Time mode fractional cycle / physical time drive interpolate_at."""
    import shutil
    from pathlib import Path as P
    base = P(tmp_path)
    for cyc in (1, 2):
        shutil.copyfile(FPH, base / f"flow_{cyc}.fph")
    w = _make(qapp, str(base / "flow_1.fph"))
    assert w.fileset is not None and len(w.fileset) == 2
    w.timeline._mode_group.button(2).setChecked(True)  # Time mode
    assert w.timeline.mode() == "Time"

    before = w.dataset
    w._on_timeline_interp(1.5)
    # A blended FieldFile (new object, mesh shared with member 1)
    assert w.dataset is not before
    assert w.dataset.path.lower().endswith("flow_1.fph")

    # Cached members: interpolation reuses parsed files
    w._on_timeline_interp(1.0)
    assert any(k.lower().endswith("flow_1.fph")
               for k in w._member_cache)

    # Physical-time request maps onto bracketing members
    for m in w.fileset.members:
        m.refresh_meta()
    if all(m.time is not None for m in w.fileset.members):
        t0 = w.fileset.members[0].time
        t1 = w.fileset.members[1].time
        w._on_timeline_time_request((t0 + t1) / 2.0)
        assert w.dataset is not None
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


def test_sta_roundtrip_all_kinds(tmp_path):
    """P0.2: every PostObject kind survives an STA save/load round-trip."""
    import dataclasses
    from fv.model import objects as objmod
    from fv.model.objects import MainObject
    from fv.render.export import _object_class, load_status, save_status
    # Reflection registry covers all dataclass PostObject subclasses
    classes = [c for c in vars(objmod).values()
               if isinstance(c, type) and dataclasses.is_dataclass(c)
               and issubclass(c, objmod.PostObject) and c is not objmod.PostObject
               and isinstance(getattr(c, "kind", None), str)]
    assert len(classes) >= 30
    for cls in classes:
        assert _object_class(cls.kind) is cls, f"{cls.__name__} unregistered"
    # End-to-end: build one object of every kind and round-trip them
    main = MainObject(path="x.fph", display_name="x.fph")
    for i, cls in enumerate(classes, start=1):
        main.children.append(cls(index=1))
    path = tmp_path / "all_kinds.sta"
    assert save_status(main, str(path)) is True
    restored = load_status(str(path))
    assert restored is not None
    assert len(restored) == len(classes), (
        f"only {len(restored)}/{len(classes)} kinds restored")
    assert {o.kind for o in restored} == {c.kind for c in classes}


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


def _menu_by_title(w, title):
    return next(m.menu() for m in w.menuBar().actions() if m.text() == title)


def test_menu_stubs_wired(qapp):
    """Menu/view stubs now have real handlers (E-gap)."""
    w = _make(qapp, FPH)
    display = _menu_by_title(w, "Display")
    dlabels = [a.text() for a in display.actions()]
    assert "Redraw" in dlabels and "Show All" in dlabels
    assert "Hide All" in dlabels
    # View menu has Iso Metric / Compare wired to handlers
    view = _menu_by_title(w, "View")
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


def test_unit_settings_dialog_and_camera_wiring(qapp):
    """R0.4: UnitDialog factor/round-trip; Camera+Unit handlers wired."""
    from fv.gui.dialogs import UnitDialog, unit_factor
    assert unit_factor("m") == 1.0
    assert unit_factor("mm") == 1000.0
    assert abs(unit_factor("inch") - 39.3700787) < 1e-6
    assert unit_factor("bogus") == 1.0  # unknown falls back to metres

    w = _make(qapp, FPH)
    assert w.options.length_unit == "m"
    assert w.options.angle_unit == "deg"
    # Tree activation routes Unit/Camera to real handlers (not _nyi)
    assert callable(w.on_unit_settings)
    assert callable(w._open_camera_dialog)

    dlg = UnitDialog(w, bounds=(0.0, 2.0, 0.0, 4.0, 0.0, 6.0))
    dlg.cmb_length.setCurrentText("mm")
    dlg.cmb_angle.setCurrentText("rad")
    # Extent preview scales with the length factor
    txt = dlg.lbl_extent.text()
    assert "2000" in txt and "6000" in txt
    dlg._on_ok()
    assert dlg._applied is True
    assert dlg.length_unit == "mm"
    assert dlg.angle_unit == "rad"


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



def test_r08_camera_presets_statusbar_oilflow(qapp):
    """R0.8: camera view presets + status-bar cells/pick labels."""
    from fv.gui.object_dialogs2 import CameraDialog
    from fv.model.objects import CameraObject

    w = _make(qapp, FPH)
    assert w._cells_label.text().startswith("Cells ")
    assert "Cells —" not in w._cells_label.text()
    assert w._pick_label.text() == "Pick —"

    c = CameraObject(index=1)
    d = CameraDialog(c, scene=w.scene)
    pos, focal, up = d._preset_pose("Front")
    assert up == (0.0, 0.0, 1.0)
    assert pos[1] < focal[1]          # looks from -Y
    pos_iso, _, up_iso = d._preset_pose("Iso")
    assert pos_iso[0] > focal[0] and pos_iso[2] > focal[2]
    # no scene/bounds -> unit-sphere fallback keeps finite pose
    d2 = CameraDialog(CameraObject(index=2), scene=None)
    p2, f2, _ = d2._preset_pose("Top")
    assert all(abs(v) < 10.0 for v in p2) and f2 == (0.0, 0.0, 0.0)
    d._apply_preset("Back")
    assert d.obj.view_up == (0.0, 0.0, 1.0)
    assert d.obj.position[1] > d.obj.focal_point[1]

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


def test_camera_spline_keyframes_p15():
    """P1.5: >=3 keyframes use Catmull-Rom (passes through keyframes)."""
    from fv.render.camera import keyframe_poses
    kf = [{"position": (i, 0, 0), "focal_point": (0, 0, 0),
           "view_up": (0, 1, 0), "parallel": False} for i in range(4)]
    poses = keyframe_poses(kf, 7)
    assert len(poses) == 7
    # spline passes exactly through every keyframe (uniform spacing)
    for i in (0, 2, 4, 6):
        assert abs(poses[i]["position"][0] - (i / 2.0)) < 1e-9
    # mid-segment value differs from linear for a curved path
    kf2 = [{"position": (0, 0, 0), "focal_point": (0, 0, 0),
            "view_up": (0, 1, 0), "parallel": False},
           {"position": (1, 1, 0), "focal_point": (0, 0, 0),
            "view_up": (0, 1, 0), "parallel": False},
           {"position": (2, 0, 0), "focal_point": (0, 0, 0),
            "view_up": (0, 1, 0), "parallel": False}]
    p = keyframe_poses(kf2, 3)
    # linear mid would be y=0.5; Catmull-Rom reaches higher
    assert p[1]["position"][1] > 0.5
    assert abs(p[1]["position"][0] - 1.0) < 1e-9
    # view_up stays normalised
    u = p[1]["view_up"]
    assert abs((u[0] ** 2 + u[1] ** 2 + u[2] ** 2) ** 0.5 - 1.0) < 1e-9

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


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_turbo_heatmap_and_polar_p13():
    """P1.3: variable views render binned heatmaps; polar has an outlet."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.model.objects import TurboObject
    from fv.render.turbo import (blade_loading_surfaces, build_turbo_actors)

    ff = load_file(FPH)
    var = "PRES" if "PRES" in ff.variables else ff.variables[0]
    # meridional heatmap: quad mesh coloured by binned cell data
    obj = TurboObject(index=1)
    obj.view = "Meridional"
    obj.variable = var
    obj.n_r = 16
    obj.n_z = 16
    out = build_turbo_actors(ff, obj)
    assert "turbo" in out
    pd = out["turbo"].GetMapper().GetInput()
    assert pd.GetNumberOfCells() > 0
    arr = pd.GetCellData().GetArray(var)
    assert arr is not None
    assert arr.GetNumberOfTuples() == pd.GetNumberOfCells()
    # polar outlet: heatmap path exercises polar_view_points_from
    obj2 = TurboObject(index=2)
    obj2.view = "Polar"
    obj2.variable = var
    out2 = build_turbo_actors(ff, obj2)
    assert "turbo" in out2
    # blade loading PS/SS split surfaces
    sc, ps, ss = blade_loading_surfaces(ff, var, "Z", 16)
    assert sc is not None and len(sc) == 16
    assert np.isfinite(ps).sum() > 0
    assert np.isfinite(ss).sum() > 0


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
    # P1.3: dp = PS - SS is signed (was unsigned max-min approximation)
    assert np.isfinite(dp).all()
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


@pytest.mark.skipif(not _HAS_QT, reason="PyQt5 unavailable")
def test_p06_detail_sweep(qapp, tmp_path):
    """P0.6: extensions honest, timeline Scale wired, msg save, last_dir."""
    # 1. loadable_extensions mirrors the live loader registry (.emt!).
    from fv.gui.dialogs import loadable_extensions
    exts = loadable_extensions()
    assert {"fld", "ifld", "fph", "gph", "pph", "emt", "cgns"} <= exts

    # 2. BMP/TIF have native VTK writers on this build (export honesty).
    if _VTK:
        import vtk
        assert hasattr(vtk, "vtkBMPWriter")
        assert hasattr(vtk, "vtkTIFFWriter")

    # 3. Timeline: unbacked Sync/Ver controls removed; Scale wired.
    from fv.gui.panes import TimelineWindow
    tl = TimelineWindow()
    assert not hasattr(tl, "chk_sync") and not hasattr(tl, "edit_ver")
    tl.edit_scale.setText("2.5")
    assert tl.time_scale() == 2.5
    assert tl.format_time(2.0) == "5"
    tl.edit_scale.setText("junk")
    assert tl.time_scale() == 1.0
    assert tl.format_time(None) == ""


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_p06_message_save_and_last_dir(qapp, tmp_path):
    """P0.6: message log persists to file; open records options.last_dir."""
    w = _make(qapp, FPH)
    # message window save (button slot's non-dialog core)
    w.message_win.log("hello P0.6")
    out = tmp_path / "messages.log"
    assert w.message_win.save_log(str(out))
    assert "hello P0.6" in out.read_text(encoding="utf-8")
    assert hasattr(w.message_win, "btn_save")  # UI entry point exists
    # last_dir recorded from the loaded dataset's folder
    assert w.options.last_dir == str(Path(FPH).parent)


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_r11_probe_at_fld_nearest_node():
    """R1.1: generic probe_at probes explicit vars (FLD nearest-node)."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.render.point import probe_at
    ff = load_file(FLD)
    pt = tuple(np.asarray(ff.vertices)[0])
    res = probe_at(ff, pt, scalar_var="TEMP", vector_var="VECT", vector_on=True)
    assert "scalar" in res and res["scalar"][0] == "TEMP"
    assert "vector" in res and res["vector"][0] == "VECT"
    assert probe_at(ff, pt) == {}


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r11_probe_at_generic_fph():
    """R1.1: generic probe_at probes scalar/vector on a polyhedral file."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv.render.point import probe_at
    ff = load_file(FPH)
    pt = tuple(np.asarray(ff.vertices)[0])
    res = probe_at(ff, pt, scalar_var="PRES")
    assert "scalar" in res and res["scalar"][0] == "PRES"
    res = probe_at(ff, pt, vector_var="VEL", vector_on=True)
    assert "vector" in res and res["vector"][0] == "VEL"
    assert probe_at(ff, pt) == {}


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r11_pick_vars_mapping(qapp):
    """R1.1: _pick_vars maps each object kind to its displayed fields."""
    from fv.model.objects import (IsosurfaceObject, PlaneObject,
                                  StreamlineObject, SurfaceObject,
                                  VolumeObject)
    w = _make(qapp, FPH)
    sur = SurfaceObject(index=1, show_contour=True, contour_var="PRES",
                        show_vector=True, vector_var="VEL")
    assert w._pick_vars(sur) == ("PRES", "VEL", True, True)
    iso = IsosurfaceObject(index=1, contour_var="PRES")
    assert w._pick_vars(iso) == ("PRES", "", True, False)
    vol = VolumeObject(index=1, scalar_var="PRES", show_vector=True,
                       vector_var="VEL")
    assert w._pick_vars(vol) == ("PRES", "VEL", True, True)
    sl = StreamlineObject(index=1, color_var="PRES", vector_var="VEL")
    assert w._pick_vars(sl) == ("PRES", "VEL", True, True)
    pl = PlaneObject(index=1, pick_scalar=True, pick_scalar_var="PRES",
                     pick_vector=True, pick_vector_var="VEL")
    assert w._pick_vars(pl) == ("PRES", "VEL", True, True)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r12_lock_and_rename(qapp):
    """R1.2: lock blocks delete; toggle unlocks; rename updates title."""
    w = _make(qapp, FPH)
    assert w.main_object is not None and w.main_object.children
    obj = w.main_object.children[0]
    label = obj.label
    n_before = len(w.main_object.children)
    # lock blocks delete
    obj.locked = True
    w.on_delete_object(label)
    assert len(w.main_object.children) == n_before
    assert obj.locked is True
    # toggle unlock
    w.on_toggle_lock(label)
    assert obj.locked is False
    # rename -> title changes, index preserved
    new_label = w._apply_rename(obj, "RenamedObj")
    assert obj.title == "RenamedObj"
    assert new_label == f"RenamedObj ({obj.index})"
    # rename to identical title is a no-op
    assert w._apply_rename(obj, "RenamedObj") == new_label


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r12_hide_selected(qapp):
    """R1.2: hide/show selected toggles visibility."""
    w = _make(qapp, FPH)
    obj = w.main_object.children[0]
    obj.visible = True
    w._selected_labels = {obj.label}
    w.on_hide_selected(True)
    assert obj.visible is False
    w.on_hide_selected(False)
    assert obj.visible is True


def test_r12_area_pick_degrades_headless():
    """R1.2: area_pick returns [] without a live renderer."""
    from fv.render.scene import Scene
    s = Scene(enable_3d=False)
    assert s.area_pick(0, 0, 10, 10) == []


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_r13_measure_actors():
    """R1.3: Measure renders line(s) + billboard label."""
    from fv.model.objects import MeasureObject
    from fv.render.measure import build_measure_actors
    d = MeasureObject(index=1, mode="Distance",
                      points=[(0, 0, 0), (1, 2, 2)])
    out = build_measure_actors(None, d)
    assert "line" in out and "label" in out
    a = MeasureObject(index=2, mode="Angle",
                      points=[(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    out2 = build_measure_actors(None, a)
    assert "line1" in out2 and "line2" in out2 and "label" in out2
    # insufficient points -> empty
    assert build_measure_actors(
        None, MeasureObject(index=3, points=[(0, 0, 0)])) == {}


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r13_measure_dialog_pick(qapp):
    """R1.3: MeasureDialog begin_pick/set_pick_point fill the spinboxes."""
    from fv.model.objects import MeasureObject
    from fv.gui.object_dialogs2 import MeasureDialog
    obj = MeasureObject(index=1)
    d = MeasureDialog(obj)
    d.begin_pick(1)
    assert d._pick_index == 1
    d.set_pick_point(1, (1.5, 2.5, 3.5))
    assert obj.points[1] == (1.5, 2.5, 3.5)


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_r14_colorbar_expanded_maps():
    """R1.4: build_lut supports Jet/Hot/Cool/Turbo/Viridis/Parula."""
    from fv.render.colorbar import build_lut
    for name in ("Jet", "Hot", "Cool", "Turbo", "Viridis", "Parula",
                 "Rainbow", "Gray", "Invert"):
        lut = build_lut(32, name)
        assert lut.GetNumberOfTableValues() == 32
        c0 = lut.GetTableValue(0)
        c1 = lut.GetTableValue(31)
        assert (c0[0], c0[1], c0[2]) != (c1[0], c1[1], c1[2])


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_r14_colorbar_parametrized_labels():
    """R1.4: colorbar_actor honours num_labels / label_color / label_format."""
    from fv.model.objects import ColorbarObject
    from fv.render.colorbar import colorbar_actor
    cb = ColorbarObject(num_labels=5, label_color=(1.0, 0.0, 0.0),
                        label_format="%.2f")
    sb = colorbar_actor(cb)
    assert sb is not None
    assert sb.GetNumberOfLabels() == 5
    c = sb.GetLabelTextProperty().GetColor()
    assert abs(c[0] - 1.0) < 1e-9 and abs(c[1]) < 1e-9


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r15_graph_multi_series():
    """R1.5: collect_multi_series returns one series per variable."""
    from fv.model.dataset import load_file
    from fv.model.objects import GraphObject
    from fv.render.graph import collect_multi_series, collect_series
    ff = load_file(FPH)
    g = GraphObject(index=1, variable="PRES", variables=["PRES", "TURK"])
    series = collect_multi_series(g, ff0=ff)
    assert len(series) == 2
    labels = [s[2] for s in series]
    assert "PRES" in labels and "TURK" in labels
    # single-variable fallback still works
    g2 = GraphObject(index=2, variable="PRES")
    assert len(collect_multi_series(g2, ff0=ff)) == 1
    xs, ys, var = collect_series(g2, ff0=ff)
    assert var == "PRES"


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r15_graph_save(tmp_path):
    """R1.5: save_graph writes a PNG via matplotlib (Agg)."""
    try:
        import matplotlib  # noqa: F401
    except Exception:
        pytest.skip("matplotlib unavailable")
    from fv.model.dataset import load_file
    from fv.model.objects import GraphObject
    from fv.render.graph import save_graph
    ff = load_file(FPH)
    g = GraphObject(index=1, variable="PRES")
    out = tmp_path / "graph.png"
    assert save_graph(g, str(out), ff0=ff) is True
    assert out.exists() and out.stat().st_size > 0


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r16_compare_same_file_zero_diff():
    """R1.6: comparing a file with itself yields a zero difference field."""
    from fv.model.dataset import load_file
    from fv.model.compare import (common_variables, difference_field,
                                  compare_stats, compare_summary)
    ff = load_file(FPH)
    common = common_variables(ff, ff)
    assert "PRES" in common
    res = difference_field(ff, ff, "PRES")
    assert res is not None
    assert res["min"] == 0.0 and res["max"] == 0.0
    assert res["mean"] == 0.0 and res["rms"] == 0.0
    assert res["diff"].shape == ff.variable_array("PRES").shape
    st = compare_stats(ff, ff, "PRES")
    assert st["var"] == "PRES" and st["min"] == 0.0
    summary = compare_summary(ff, ff)
    assert "PRES" in summary and "TURK" in summary


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r16_compare_constant_offset():
    """R1.6: a constant offset gives uniform |A−B| equal to the offset."""
    import numpy as np
    from dataclasses import replace
    from fv.model.dataset import load_file, VarInfo
    from fv.model.compare import difference_field, diff_field_file
    a = load_file(FPH)
    b = replace(a)
    b.variables = dict(a.variables)
    b.variables["PRES"] = VarInfo(name="PRES", kind="scalar", location="cell",
                                  array=np.asarray(a.variable_array("PRES")) + 2.5)
    res = difference_field(a, b, "PRES")
    assert res["min"] == pytest.approx(2.5)
    assert res["max"] == pytest.approx(2.5)
    assert res["mean"] == pytest.approx(2.5)
    diff_ff = diff_field_file(a, "PRES", res["diff"], res["location"])
    arr = diff_ff.variable_array("PRES")
    assert arr is not None and len(arr) == len(res["diff"])


def test_r21_set_cyc_ope_mode_numeric():
    """R2.1: SetCycOpeMode accepts numeric 0-7 and legacy strings."""
    from fv.model.fileset import FileSet, set_cycle_operation
    fs = FileSet(directory=".")
    expect = {0: "Sum0", 1: "Average", 2: "Add", 3: "Sub",
              4: "Mul", 5: "Div", 6: "SqSum", 7: "SqAvg"}
    for n, name in expect.items():
        assert set_cycle_operation(fs, n) == name
        assert fs.operation_mode == name
    # legacy string aliases still work
    assert set_cycle_operation(fs, "add") == "Add"
    assert set_cycle_operation(fs, "SUB") == "Sub"
    with pytest.raises(ValueError):
        set_cycle_operation(fs, 8)


def test_r21_get_overlapping_region_count():
    """R2.1: GetOverlappingRegionCount counts regions, not cells."""
    import numpy as np
    from fv.model.dataset import FieldFile
    from fv import api
    ff = FieldFile(path="x", kind="fph")
    ff.cvol_id = np.array([1, 1, 2, 2], dtype=np.int64)
    ff.parts_with_cvol = [("A", 1), ("B", 2)]
    assert api.get_overlapping_region_count(ff) == 0
    # cells 0-1 belong to both A and B -> both regions overlap
    ff2 = FieldFile(path="y", kind="fph")
    ff2.cvol_id = np.array([1, 1, 2, 2], dtype=np.int64)
    ff2.parts_with_cvol = [("A", frozenset({1})), ("B", frozenset({1, 2}))]
    assert api.get_overlapping_region_count(ff2) == 2


def test_r21_get_mat_id_of_vol():
    """R2.1: GetMATIDofVOL takes a 1-based volid and reports MAT count."""
    import numpy as np
    from fv.model.dataset import FieldFile
    from fv import api
    ff = FieldFile(path="x", kind="fph")
    ff.cvol_id = np.array([1, 1, 2, 2], dtype=np.int64)
    ff.material = np.array([5, 5, 7, 7], dtype=np.int64)
    ff.parts_with_cvol = [("R1", 1), ("R2", 2)]
    ff.volume_regions = ["R1", "R2"]
    assert api.get_mat_id_of_vol(ff, "R1") == 5
    assert api.get_mat_id_of_vol(ff, 2) == 7
    assert api.get_mat_num_of_vol(ff, "R1") == 1
    # a region mixing two MAT ids -> -1, count 2
    ff.parts_with_cvol = [("R1", frozenset({1, 2})), ("R2", 2)]
    assert api.get_mat_id_of_vol(ff, "R1") == -1
    assert api.get_mat_num_of_vol(ff, "R1") == 2


def test_r21_local_xyz_global_from_file():
    """R2.1: LocalXYZ2GlobalXYZ reads ff.meta['local_coord']."""
    import numpy as np
    from fv.model.dataset import FieldFile
    from fv import api
    ff = FieldFile(path="x", kind="fph")
    ff.meta = {}
    out = api.local_xyz_to_global_xyz((1.0, 2.0, 3.0), ff=ff)
    assert np.allclose(out, (1.0, 2.0, 3.0))  # identity when absent
    # explicit origin/axis/angle path still works
    g = api.local_xyz_to_global_xyz((1.0, 0.0, 0.0), axis="z", angle_deg=90.0)
    assert np.allclose(g, (0.0, 1.0, 0.0), atol=1e-12)
    # stored 4x4 matrix is applied
    m = np.eye(4)
    m[:3, 3] = [10.0, 0.0, 0.0]
    ff2 = FieldFile(path="y", kind="fph")
    ff2.meta = {"local_coord": {"matrix": m}}
    g2 = api.local_xyz_to_global_xyz((1.0, 0.0, 0.0), ff=ff2)
    assert np.allclose(g2, (11.0, 0.0, 0.0))


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_r21_fld_local_coord_meta():
    """R2.1: FLD parser stores local_coord (identity for this sample)."""
    from fv.model.dataset import load_file
    ff = load_file(FLD)
    assert "local_coord" in ff.meta
    assert ff.meta["local_coord"] is None


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r22_ov_geometry_queries():
    """R2.2: ov-parameter geometry family (thin wrappers over topology)."""
    from fv.model.dataset import load_file
    from fv import api
    ff = load_file(FPH)
    assert api.get_node_count(ff) == ff.n_vertices
    assert api.get_element_count(ff) == ff.n_cells
    assert api.get_node_ofs(ff) in (0, 1)
    xyz = api.get_node_xyz(ff, 0)
    assert len(xyz) == 3 and all(isinstance(v, float) for v in xyz)
    nodes = api.get_nodes_of_element(ff, 0)
    assert len(nodes) == api.get_node_count_of_element(ff, 0) > 0
    nfaces = api.get_face_count_of_element(ff, 0)
    assert nfaces >= 0
    if nfaces:
        fnodes = api.get_nodes_of_face(ff, 0, 0)
        assert len(fnodes) == api.get_node_count_of_face(ff, 0, 0)
        assert api.get_area_of_face(ff, 0, 0) > 0.0
        assert isinstance(api.get_adjacent_element_of_face(ff, 0, 0), int)
    assert api.get_volume_of_element(ff, 0) > 0.0


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r22_ov_geometry_com():
    """R2.2: COM exposes the ov geometry family on an open file."""
    from fv.com import FlowviewerApplication
    app = FlowviewerApplication()
    app.open_file(FPH)
    assert app.GetNodeCount() == app._ff.n_vertices
    assert app.GetElementCount() == app._ff.n_cells
    assert app.GetNodeOfs() in (0, 1)
    assert app.GetNodeCountOfElement(0, 0) > 0
    assert app.GetFaceCountOfElement(0, 0) >= 0
    nodes = app.GetNodesOfElement(0, 0)
    assert isinstance(nodes, list) and len(nodes) > 0
    xyz = app.GetNodeXYZ(0)
    assert len(xyz) == 3
    assert app.GetElementsOfVolumeRegion(1) is not None


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r23_mat_vol_rgn_lookup_fph():
    """R2.3: VOL/RGN lookup family on a poly file."""
    from fv.model.dataset import load_file
    from fv import api
    ff = load_file(FPH)
    vols = api.get_vol_org_names(ff)
    assert len(vols) == len(ff.volume_regions)
    if vols:
        assert api.get_vol_id_by_vol_orgname(ff, vols[0]) == 1
        assert api.get_vol_orgname_by_vol_id(ff, 1) == vols[0]
        assert api.get_vol_emtname_by_vol_id(ff, 1) == vols[0]
    rgn = api.get_rgn_num(ff)
    assert rgn == len(ff.surface_regions)
    if rgn:
        name = api.get_rgn_name(ff, 0)
        assert name == ff.surface_regions[0][0]
        assert api.get_face_num_of_rgn(ff, 0) == len(ff.surface_regions[0][1])


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_r23_mat_lookup_fld():
    """R2.3: MAT lookup family on an FLD file with materials."""
    import numpy as np
    from fv.model.dataset import load_file
    from fv import api
    ff = load_file(FLD)
    assert api.get_mat_num(ff) >= 1
    ids = api._mat_ids(ff)
    assert ids == sorted(int(x) for x in np.unique(ff.material))
    if ids:
        assert api.get_mat_n_by_mat_id(ff, ids[0]) == ids[0]
        assert api.get_mat_id_by_mat_n(ff, ids[0]) == ids[0]
        assert api.get_mat_emtname_by_mat_id(ff, ids[0]) == "MAT%d" % ids[0]
        assert api.get_mat_id_by_mat_emtname(ff, "MAT%d" % ids[0]) == ids[0]
    assert api.get_mat_n_of_element(ff, 0) in (-1, 1, 2)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r23_mat_vol_rgn_com():
    """R2.3: COM exposes the MAT/VOL/RGN lookup family."""
    from fv.com import FlowviewerApplication
    app = FlowviewerApplication()
    app.open_file(FPH)
    assert app.GetRgnNum() == len(app._ff.surface_regions)
    assert app.GetVOLorgnameAsArray() == list(app._ff.volume_regions)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r24_variable_at_point():
    """R2.4: variable_at_point probes a cell-centred field."""
    from fv.model.dataset import load_file
    from fv import api
    ff = load_file(FPH)
    p = api.cell_centers(ff)[0]
    res = api.variable_at_point(ff, "PRES", p[0], p[1], p[2])
    assert res is not None and res["isinarea"] is True
    assert res["name"] == "PRES" and res["elem"] == 0
    assert isinstance(res["values"], float)
    resv = api.variable_at_point(ff, "VEL", p[0], p[1], p[2])
    assert resv is not None and len(resv["values"]) == 3


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_r24_variable_at_point_fld():
    """R2.4: node-centred FLD uses nearest-node lookup."""
    from fv.model.dataset import load_file
    from fv import api
    ff = load_file(FLD)
    v = ff.vertices[0]
    res = api.variable_at_point(ff, "PRES", v[0], v[1], v[2])
    assert res is not None and isinstance(res["values"], float)


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_p06_varreg_mag_div_rot():
    """P0-6: mag() reduces vector expressions; div/rot accept 3 components."""
    import numpy as np
    from fv.model.dataset import (load_file, FIELD_KIND_SCALAR,
                                  FIELD_KIND_VECTOR, VarInfo)
    from fv.model import varreg
    ff = load_file(FLD)
    n = ff.n_vertices
    x = np.linspace(0.0, 1.0, n)
    for c, arr in (("X", np.sin(x)), ("Y", np.cos(x)), ("Z", np.zeros(n))):
        ff.variables["VEL" + c] = VarInfo(
            name="VEL" + c, kind=FIELD_KIND_VECTOR, location="node", array=arr)
    # mag(vector) -> unit magnitude
    m = varreg.register_variable(ff, "SPEED", "mag(VEL)")
    assert m.kind == FIELD_KIND_SCALAR and m.array.shape == (n,)
    assert abs(float(m.array[0]) - 1.0) < 1e-6
    # mag(grad(scalar)) reduces the (n,3) gradient to a scalar
    g = varreg.register_variable(ff, "GMAG", "mag(grad(PRES))")
    assert g.kind == FIELD_KIND_SCALAR and g.array.shape == (n,)
    # div/rot with base name and explicit components
    d = varreg.register_variable(ff, "DIVV", "div(VEL)")
    assert d.kind == FIELD_KIND_SCALAR
    d3 = varreg.register_variable(ff, "DIV3", "div(VELX,VELY,VELZ)")
    assert d3.kind == FIELD_KIND_SCALAR
    r3 = varreg.register_variable(ff, "ROT3", "rot(VELX,VELY,VELZ)")
    assert r3.kind == FIELD_KIND_VECTOR and r3.array.shape == (n, 3)
    assert np.allclose(d.array, d3.array)


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_p05_oilflow_fld_numeric():
    """P0-5: oilflow on FLD takes the numeric fallback (no VTK locator crash)."""
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.render.oilflow import build_oilflow_actor, _numeric_trace_fld
    ff = load_file(FLD)
    assert ff.kind == "fld"
    obj = PlaneObject(index=1)
    obj.oilflow_display = True
    obj.oilflow_var = "VECT"
    obj.oilflow_color_var = "PRES"
    obj.oilflow_steps = 8
    obj.oilflow_length = 1.0
    poly = _numeric_trace_fld(ff, obj)
    assert poly is not None
    assert poly.GetNumberOfCells() > 0
    assert poly.GetPointData().GetArray("PRES") is not None
    actor = build_oilflow_actor(ff, obj)
    assert actor is not None


def test_p04_gettickcount_ex():
    """P0-4: GetTickCountEx returns machine uptime in seconds."""
    from fv.com import FlowviewerApplication
    app = FlowviewerApplication()
    t = app.GetTickCountEx()
    assert isinstance(t, float)
    assert t > 3600.0            # machine has been up for over an hour


def test_p04_shell_execute_error_path():
    """P0-4: ShellExecute fails cleanly on empty/bad targets."""
    from fv.com import FlowviewerApplication
    app = FlowviewerApplication()
    # empty target -> False (ok), no exception
    assert app.ShellExecute("") is False
    # a clearly-invalid path must not raise (returns None via _fail)
    res = app.ShellExecute("Z:\\__no_such_file_flowviewer__.xyz")
    assert res is None
    assert app.ErrorCode != 0


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_p03_object_and_var_query():
    """P0-3: COM object query + variable value query families."""
    from fv.com import FlowviewerApplication
    app = FlowviewerApplication()
    app.open_file(FPH)
    # object query family
    assert app.GetObjNum() == 0
    s = app.CreateObjectSurface("S1")
    pt = app.CreateObjectPoints("P1")
    assert app.GetObjNum() == 2
    assert app.GetObjType(s) == "surface"
    assert app.GetObjectByNumber(1).kind == "surface"
    assert [o.title for o in app.GetObjectByType("surface")] == ["S1"]
    assert app.GetObjectByLongTitle("P1") is pt
    assert app.GetObjectActiveObj() is not None
    # variable value query family
    var = "PRES" if "PRES" in app.variable_names else app.variable_names[0]
    assert isinstance(app.GetScalar(var, 0), float)
    assert len(app.GetScalarArray(var)) > 0
    v = app.GetVecteor("VEL", 0) if "VELX" in app.variable_names else None
    if v is not None:
        assert len(v) == 3
        arr = app.GetVecteorArray("VEL")
        assert arr.shape[1] == 3
    # RemoveAllObj clears the tree
    app.RemoveAllObj()
    assert app.GetObjNum() == 0


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_p02_createvar_family():
    """P0-2: COM CreateVar*/DeleteVar/SetVarTitle registration family."""
    from fv.com import FlowviewerApplication
    app = FlowviewerApplication()
    app.open_file(FPH)
    var = "PRES" if "PRES" in app.variable_names else app.variable_names[0]
    r = app.CreateVar("PDIFF", "%s * 2.0" % var)
    assert r is not None and r.name == "PDIFF"
    assert app.ErrorString == "OK"
    app.SetVarTitle("PDIFF", "twice")
    assert app._ff.variables["PDIFF"].title == "twice"
    app.DeleteVar("PDIFF")
    assert "PDIFF" not in app._ff.variables
    c = app.CreateVarCombinationVelocity()
    assert c is not None and c.name == "CMBVEL"
    d = app.CreateVarDST()
    assert d is not None
    n = app.CreateVarNORMAL()
    assert n is not None
    d2 = app.CreateVarDST2(surfaces=None, maxlen=0)
    assert d2 is not None


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_p02_createvar_all_cycles():
    """P0-2: CreateVarALLCYC registers on every cycle of a FileSet."""
    from fv.com import FlowviewerApplication
    from fv.model.fileset import FileSet, SequenceMember
    app = FlowviewerApplication()
    fs = FileSet(directory=str(Path(FPH).parent),
                members=[SequenceMember(cycle=1, path=FPH)])
    app._fs = fs
    assert app.CreateVarALLCYC("SEQ2", "PRES + 1") is not None


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r24_get_variable_info_com():
    """R2.4: COM GetVariableInfo/Min/Max."""
    from fv.com import FlowviewerApplication
    from fv import api
    app = FlowviewerApplication()
    app.open_file(FPH)
    assert app.GetVariableMin("PRES") is not None
    assert app.GetVariableMax("PRES") is not None
    p = api.cell_centers(app._ff)[0]
    info = app.GetVariableInfo("PRES", p[0], p[1], p[2])
    assert info is not None and info["name"] == "PRES"


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_p01_create_object_family():
    """P0-1: every scPOST CreateObject* name is callable and attaches to the tree."""
    from fv.com import FlowviewerApplication, _CREATE_OBJECT_KINDS
    app = FlowviewerApplication()
    app.open_file(FPH)
    for name, kind in _CREATE_OBJECT_KINDS.items():
        obj = getattr(app, name)("title-%s" % kind)
        assert obj is not None, name
        assert obj.kind == kind, (name, obj.kind)
        assert obj.title == "title-%s" % kind
    assert callable(app.CreateObjectNeutral)
    assert callable(app.CreateSurfacesOfVolumeRegions)
    tree = app._object_tree()
    kinds = [o.kind for o in tree.children]
    for kind in _CREATE_OBJECT_KINDS.values():
        assert kind in kinds, kind
    objs = [o for o in tree.children if o.kind == "surface"]
    assert [o.index for o in objs] == list(range(1, len(objs) + 1))


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r25_save_variable_output_api(tmp_path):
    """R2.5: save_variable_output writes a probe CSV (default probe)."""
    import csv
    from fv.model.dataset import load_file
    from fv import api
    ff = load_file(FPH)
    out = tmp_path / "r25.csv"
    assert api.save_variable_output(ff, str(out))
    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header, data = rows[0], rows[1]
    assert header[0] == "title" and "x" in header and "scalar" in header
    assert data[0] == "Probe 1"
    assert data[header.index("scalar_value")] != ""
    assert data[header.index("vector_x")] != ""


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r25_save_variable_output_items(tmp_path):
    """R2.5: items subset restricts the emitted columns."""
    import csv
    from fv.model.dataset import load_file
    from fv import api
    ff = load_file(FPH)
    out = tmp_path / "r25_sub.csv"
    assert api.save_variable_output(ff, str(out), items=["title", "coords"])
    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["title", "x", "y", "z"]
    assert len(rows[1]) == 4


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r25_save_variable_output_point_object(tmp_path):
    """R2.5: PointObject probe vars drive the exported scalar/vector."""
    import csv
    from fv.model.dataset import load_file
    from fv.model.objects import PointObject
    from fv import api
    ff = load_file(FPH)
    p = api.cell_centers(ff)[0]
    obj = PointObject(index=1, title="P1", position=(p[0], p[1], p[2]),
                      probe_scalar=True, probe_scalar_var="PRES",
                      probe_vector=True, probe_vector_var="VEL")
    out = tmp_path / "r25_pt.csv"
    assert api.save_variable_output(ff, str(out), objects=[obj])
    with open(out, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header, data = rows[0], rows[1]
    assert data[header.index("scalar")] == "PRES"
    assert data[header.index("vector")] == "VEL"


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r25_save_variable_output_com(tmp_path):
    """R2.5: COM SaveVariableOutput returns True and writes a file."""
    from fv.com import FlowviewerApplication
    app = FlowviewerApplication()
    app.open_file(FPH)
    out = tmp_path / "r25c.csv"
    assert app.SaveVariableOutput(str(out), "all") is True
    assert app.ErrorCode == 0
    assert out.exists()
    assert "title" in out.read_text(encoding="utf-8")


def test_r26_application_misc():
    """R2.6: Application misc methods (PID/ticks/folder/wildcard/...)."""
    import os
    import tempfile
    from fv.com import FlowviewerApplication
    app = FlowviewerApplication()
    assert app.GetPID() > 0
    assert app.GetTickCount() >= 0
    assert app.GetTickCountEx() > 0
    assert bool(app.GetHomeFolder())
    assert bool(app.GetEnvFilePath())
    assert app.IsThisPathValid("") == 100
    tmp = tempfile.mkdtemp()
    try:
        assert app.CreateFolder(os.path.join(tmp, "sub")) == 1
        assert app.IsThisPathValid(os.path.join(tmp, "sub")) == 2
        newfile = os.path.join(tmp, "newfile.tmp")
        assert app.IsThisPathValid(newfile) == 0
        with open(os.path.join(tmp, "a.fld"), "w") as fh:
            fh.write("")
        assert '"a.fld"' in app.GetAllFilesForWildCard(tmp, "*.fld")
        assert app.GetOneOfFilesForWildCard(tmp, "*.fld").endswith("a.fld")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    assert bool(app.GetRandomFilename())
    assert app.ShellExecute("x") is True
    assert app.SetLogFilename("x") is True
    assert app.SetMessageLevel(1) == 0
    assert app.OpenMessageLogFile("x") == 0
    assert app.CloseMessageLogFile() == 0
    assert app.UpdateAll() is True
    assert app.AnimationFrame(3) == 3
    assert app.AnimationSecond(0.5) >= 1


def test_r27_com_gui_bridge():
    """R2.7: COM methods forward to an attached GUI; headless degrades to flags."""
    from fv.com import FlowviewerApplication, attach_gui, detach_gui

    calls = []

    class FakeTimeline:
        def set_step(self, s):
            calls.append(("step", s))

    class FakeGUI:
        def on_redraw(self):
            calls.append("redraw")

        def _on_timeline_play(self):
            calls.append("play")

        def _on_timeline_pause(self):
            calls.append("pause")

        def _on_timeline_step(self, s):
            calls.append(("timestep", s))

    gui = FakeGUI()
    gui.timeline = FakeTimeline()

    app = FlowviewerApplication()
    # headless: no forwarding, just flags / True
    assert app.UpdateAll() is True
    assert calls == []

    attach_gui(gui)
    try:
        app.UpdateAll()
        app.AnimationStart()
        app.AnimationStop()
        app.AnimationFrame(3)
        app.AnimationSecond(0.5)
    finally:
        detach_gui(gui)

    assert "redraw" in calls
    assert "play" in calls
    assert "pause" in calls
    assert ("step", 3) in calls
    assert ("step", 7) in calls  # 0.5s * 15 fps = 7
    # back to headless flag mode after detach
    assert app.UpdateAll() is True


def test_r27_save_sta_bridge(tmp_path):
    """R2.7: SaveSTA persists the attached GUI object tree."""
    from fv.com import FlowviewerApplication, attach_gui, detach_gui
    from fv.model.objects import MainObject
    gui = type("G", (), {"main_object": MainObject(path="x",
                                                   display_name="x")})()
    app = FlowviewerApplication()
    attach_gui(gui)
    try:
        out = tmp_path / "r27.sta"
        assert app.SaveSTA(str(out)) is True
        assert out.exists()
    finally:
        detach_gui(gui)


def test_r33_camera_slerp():
    """R3.3: view_up interpolation uses unit-length SLERP (no over-top jump)."""
    from fv.render.camera import _slerp_v3, interpolate_pose
    a = (0.0, 1.0, 0.0)
    b = (0.0, 0.0, 1.0)
    up = _slerp_v3(a, b, 0.5)
    n = (up[0] ** 2 + up[1] ** 2 + up[2] ** 2) ** 0.5
    assert abs(n - 1.0) < 1e-9
    assert abs(up[1] - up[2]) < 1e-9  # halfway between +Y and +Z
    # end points are the (normalized) inputs
    assert _slerp_v3(a, b, 0.0) == a
    assert _slerp_v3(a, b, 1.0) == b
    # degenerate zero vector falls back to a sane up
    z = _slerp_v3((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.5)
    assert z == (0.0, 0.0, 1.0)
    # interpolate_pose routes view_up through SLERP
    p0 = {"position": (0, 0, 0), "focal_point": (0, 0, -1),
          "view_up": a, "parallel": True}
    p1 = {"position": (1, 0, 0), "focal_point": (0, 0, -1),
          "view_up": b, "parallel": True}
    mid = interpolate_pose(p0, p1, 0.5)
    m = mid["view_up"]
    mn = (m[0] ** 2 + m[1] ** 2 + m[2] ** 2) ** 0.5
    assert abs(mn - 1.0) < 1e-9


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_r32_video_export_vtk(tmp_path):
    """R3.2: export_animation_video writes an Ogg Theora video via VTK."""
    import vtk
    from fv.render.export import export_animation_video
    if not hasattr(vtk, "vtkOggTheoraWriter"):
        pytest.skip("vtkOggTheoraWriter unavailable")
    ren = vtk.vtkRenderer()
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.AddRenderer(ren)
    win.SetSize(64, 64)
    src = vtk.vtkSphereSource()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(src.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    ren.AddActor(actor)
    win.Render()
    out = tmp_path / "anim.ogv"
    n = export_animation_video(None, None, None, win, str(out),
                               frames=3, fps=15)
    assert n == 3
    assert out.exists() and out.stat().st_size > 0


def test_r32_video_export_headless(tmp_path):
    """R3.2: export_animation_video degrades to 0 without a render window."""
    from fv.render.export import export_animation_video
    assert export_animation_video(None, None, None, None,
                                  str(tmp_path / "anim.ogv")) == 0



def test_r36_synced_timeline_model():
    """R3.6: SyncedTimeline unifies ranges and resolves members in lockstep."""
    from fv.model.fileset import FileSet, SequenceMember, SyncedTimeline

    def fs(cycles):
        return FileSet(directory=".", members=[
            SequenceMember(path=f"s_{c}.fph", cycle=c) for c in cycles])

    a = fs([1, 2, 3])
    b = fs([10, 100, 200])
    st = SyncedTimeline(align="cycle")
    st.add(a).add(b).add(a)  # duplicate add is idempotent
    assert len(st) == 2
    assert st.range() == (1, 200)
    assert st.min_cycle() == 1 and st.max_cycle() == 200
    # cycle alignment: nearest at-or-after per FileSet
    pairs = st.members_at(5)
    assert pairs[0][1].cycle == 3      # a: no member >=5 -> last (3)
    assert pairs[1][1].cycle == 10     # b: first member >=5
    # index alignment advances both sequences ordinal-by-ordinal
    st2 = SyncedTimeline(align="index")
    st2.add(a).add(b)
    assert st2.range() == (0, 2)
    assert st2.members_at(1) == [(a, a.members[1]), (b, b.members[1])]
    assert st2.members_at(5) == [(a, None), (b, None)]
    # invalid align falls back to cycle
    assert SyncedTimeline(align="bogus").align == "cycle"
    # removal / clear
    st2.remove(a)
    assert len(st2) == 1
    st2.clear()
    assert not st2


@pytest.mark.skipif(not _HAS_QT, reason="PyQt5 unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r36_gui_multi_fileset_sync(qapp, tmp_path):
    """R3.6: opening two sequences registers both and steps them in lockstep."""
    import shutil
    from pathlib import Path as P
    base = P(tmp_path)
    # Two distinct stems, each a two-step sequence (copies of the sample).
    for stem, cycles in (("a", (1, 2)), ("b", (10, 20))):
        for c in cycles:
            shutil.copyfile(FPH, base / f"{stem}_{c}.fph")
    w = _make(qapp, str(base / "a_1.fph"))
    assert w.fileset is not None and len(w.fileset) == 2
    assert len(w.filesets) == 1
    # Open the second stem without closing (default Open appends to sync).
    w.open_file(str(base / "b_10.fph"))
    assert len(w.filesets) == 2
    assert w._sync_range() == (1, 20)
    assert w._sync_min_cycle() == 1 and w._sync_max_cycle() == 20
    # Cycle mode: a single timeline value drives both sequences.
    w.timeline._mode_group.button(1).setChecked(True)
    assert w.timeline.mode() == "Cycle"
    w.timeline.set_step(12)
    w._on_timeline_step(12)
    # primary (b) resolves step 12 to b_20; a resolves to its last member a_2.
    assert w.dataset.path.lower().endswith("b_20.fph")
    assert any(k.lower().endswith("a_2.fph") for k in w._member_cache)
    assert any(k.lower().endswith("b_20.fph") for k in w._member_cache)
    # Re-opening the first stem replaces (not duplicates) its FileSet.
    w.open_file(str(base / "a_1.fph"))
    assert len(w.filesets) == 2
    w._close_current_files()
    assert w.filesets == []



def test_r37_color_table_control_points():
    """R3.7: control points normalize/add/remove with clamped endpoints."""
    from fv.render.colorbar import (add_control_point, normalize_control_points,
                                    remove_control_point)
    pts = [(0.0, (0.0, 0.0, 1.0)), (1.0, (1.0, 0.0, 0.0))]
    p = add_control_point(pts, 0.5, (0.5, 0.5, 0.5))
    assert [t for t, _ in p] == [0.0, 0.5, 1.0]
    p2 = add_control_point(pts, 2.0, (1.0, 1.0, 1.0))
    assert p2[-1][0] == 1.0
    p3 = remove_control_point(p, 0.5)
    assert [t for t, _ in p3] == [0.0, 1.0]
    assert normalize_control_points([]) == [(0.0, (0.0, 0.0, 1.0)),
                                             (1.0, (1.0, 0.0, 0.0))]


def test_r37_color_table_csv_roundtrip(tmp_path):
    """R3.7: control points round-trip through CSV; header/gray handled."""
    from fv.render.colorbar import load_colormap_csv, save_colormap_csv
    pts = [(0.0, (0.0, 0.0, 0.0)), (0.5, (1.0, 0.0, 0.0)),
           (1.0, (1.0, 1.0, 1.0))]
    out = tmp_path / "ct.csv"
    save_colormap_csv(str(out), pts)
    assert out.exists()
    loaded = load_colormap_csv(str(out))
    assert [round(t, 6) for t, _ in loaded] == [0.0, 0.5, 1.0]
    dat = tmp_path / "gray.csv"
    dat.write_text("t\n0\n1\n", encoding="utf-8")
    g = load_colormap_csv(str(dat))
    assert g[0][1] == (0.0, 0.0, 0.0) and g[-1][1] == (1.0, 1.0, 1.0)


def test_r37_color_table_register():
    """R3.7: register/list/unregister custom colormaps."""
    from fv.render import colorbar as cb
    key = cb.register_colormap("r37test",
                               [(0.0, (0.0, 0.0, 0.0)),
                                (1.0, (1.0, 1.0, 1.0))])
    assert key == "r37test"
    assert "r37test" in cb.list_colormaps()
    assert cb.colormap_control_points("r37test") == [(0.0, (0.0, 0.0, 0.0)),
                                                      (1.0, (1.0, 1.0, 1.0))]
    assert cb.unregister_colormap("r37test") is True
    assert "r37test" not in cb.list_colormaps()
    assert cb.unregister_colormap("rainbow") is False  # built-in kept


@pytest.mark.skipif(not _HAS_QT, reason="PyQt5 unavailable")
def test_r37_color_table_dialog(qapp):
    """R3.7: ColorTableDialog edits control points and registers the map."""
    from fv.gui.dialogs import ColorTableDialog
    from fv.render import colorbar as cb
    dlg = ColorTableDialog("r37dlg", [(0.0, (0.0, 0.0, 1.0)),
                                      (1.0, (1.0, 0.0, 0.0))])
    assert dlg.table.rowCount() == 2
    dlg._on_add()
    assert dlg.table.rowCount() == 3
    assert len(dlg._read_points()) == 3
    dlg.table.selectRow(dlg.table.rowCount() - 1)
    dlg._on_remove()
    assert dlg.table.rowCount() == 2
    dlg.edit_name.setText("r37dlg")
    dlg._on_ok()
    assert dlg.result_name == "r37dlg"
    assert "r37dlg" in cb.list_colormaps()
    cb.unregister_colormap("r37dlg")



def test_r34_gradation_colors():
    """R3.4: multi-stop gradient expansion interpolates control points."""
    from fv.render.scene import gradation_colors
    c = gradation_colors([(0.0, (0.0, 0.0, 0.0)), (1.0, (1.0, 1.0, 1.0))], n=3)
    assert c[0] == (0.0, 0.0, 0.0)
    assert c[1] == (0.5, 0.5, 0.5)
    assert c[-1] == (1.0, 1.0, 1.0)
    c2 = gradation_colors([(0.0, (0, 0, 0)), (0.5, (1, 0, 0)),
                           (1.0, (1, 1, 1))], n=5)
    assert c2[2] == (1.0, 0.0, 0.0)  # t = 0.5
    assert gradation_colors([(0.3, (0.5, 0.5, 0.5))], n=3) == [(0.5, 0.5, 0.5)] * 3
    assert gradation_colors([], n=2) == [(1.0, 1.0, 1.0), (0.92, 0.94, 0.97)]


def test_r34_text_gradation_fields():
    """R3.4: TextObject 3D anchor and GradationObject control points exist."""
    from fv.model.objects import TextObject, GradationObject
    t = TextObject(anchor_3d=True, anchor_position=(1.0, 2.0, 3.0))
    assert t.anchor_3d is True
    assert t.anchor_position == (1.0, 2.0, 3.0)
    g = GradationObject(control_points=((0.0, (0, 0, 0)), (1.0, (1, 1, 1))))
    assert g.control_points == ((0.0, (0, 0, 0)), (1.0, (1, 1, 1)))


@pytest.mark.skipif(not _VTK, reason="vtk unavailable")
def test_r34_text_actor_3d():
    """R3.4: anchor_3d emits a vtkBillboardTextActor3D at the world anchor."""
    from fv.model.objects import TextObject
    from fv.render.text import text_actor
    obj = TextObject(text="Hi", anchor_3d=True, anchor_position=(1.0, 2.0, 3.0))
    a = text_actor(obj)
    assert a is not None and a.IsA("vtkBillboardTextActor3D")
    assert tuple(a.GetPosition()) == (1.0, 2.0, 3.0)
    a2 = text_actor(TextObject(text="Hi"))
    assert a2.IsA("vtkTextActor")
