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
                    "Texture", "Font"]
    assert pd.contour.combo.count() >= 1
    pd.apply_to(p)
    assert p.axis == "Z"
    assert p.contour_var in [pd.contour.combo.itemData(i)
                             for i in range(pd.contour.combo.count())]
    assert p.contour_var in ff.variables


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
def test_plane_integration_csv_output(qapp):
    """Integration result written to CSV when Output-to-file checked (P1.3)."""
    import csv
    import tempfile
    from fv.model.dataset import load_file
    from fv.model.objects import PlaneObject
    from fv.gui.object_dialogs import PlaneDialog
    ff = load_file(FPH)
    obj = PlaneObject(index=1, axis="Z", coordinate=0.0)
    obj.contour_var = "PRES"
    with tempfile.TemporaryDirectory(
            dir=r"C:\Users\sdcll\AppData\Local\Temp\opencode") as td:
        out_csv = Path(td) / "integral.csv"
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
def test_plane_colorbar_texture():
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
    tmp = _Path(r"C:\Users\sdcll\AppData\Local\Temp\opencode\flowviewer_p39.bmp")
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