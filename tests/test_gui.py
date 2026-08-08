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
        _filter_label, filter_extensions,
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
    w = _make(qapp, FPH)
    assert hasattr(w, "property_host")
    # Auto-shows Surface (1) after open
    assert w.property_host.current_object is not None
    assert w.property_host.current_object.label == "Surface (1)"
    assert w.property_host.current_panel is not None
    # Switch to Plane via activation
    w._on_object_activated("plane", "Plane (1)")
    assert w.property_host.current_object.label == "Plane (1)"
    # Apply rebuilds without modal exec_
    w.property_host._on_apply()
    assert "plane" in w.scene.actor_names()
    # Hide clears the host
    w.property_host._on_hide()
    assert w.property_host.current_panel is None


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
                    "Mesh", "Automove", "Trim"]
    assert pd.contour.combo.count() >= 1
    pd.apply_to(p)
    assert p.axis == "Z"


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