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
    obj.trim_xmin = True
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