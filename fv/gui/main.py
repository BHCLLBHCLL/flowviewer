"""FlowViewer main window — scPOST-style layout (cabdecoding chrome)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

try:
    from PyQt5 import QtCore, QtWidgets
    from PyQt5.QtCore import QSize, Qt
    from PyQt5.QtGui import QKeySequence
    from PyQt5.QtWidgets import (
        QAction, QApplication, QLabel, QMainWindow, QSplitter, QToolBar,
    )
    try:
        from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
        import vtk
        _HAS_GUI_DEPS = True
    except Exception:  # pragma: no cover
        QVTKRenderWindowInteractor = None
        vtk = None
        _HAS_GUI_DEPS = False
except Exception:  # pragma: no cover - headless
    _HAS_GUI_DEPS = False
    QtWidgets = None
    QMainWindow = object  # type: ignore
    QKeySequence = None  # type: ignore
    QApplication = None


class FlowViewer(QMainWindow if _HAS_GUI_DEPS else object):
    """scPOST-style main window.

    Layout (Post_Layout_of_Windows)::

        Menu: File | Create | Display | View | Option | Toolbar | Help
        ToolBar: File | Create | Display | View | Mouse | Option
        ┌ Control Window ─┬ Draw Window ──────────────────┐
        │ POST application│  VTK (gradient + gnomon)      │
        │  tree           ├ Message ──────┬ Timeline ─────┤
        └─────────────────┴───────────────┴───────────────┘
        StatusBar: (x,y,z) | mode | …

    ``enable_3d=False`` swaps the VTK widget for a placeholder so the window
    can be built headlessly (offscreen tests).
    """

    def __init__(self, filepath: Optional[str] = None, enable_3d: bool = True):
        if not _HAS_GUI_DEPS:
            raise RuntimeError("PyQt5/vtk not installed")
        super().__init__()
        self.setWindowTitle("flowviewer")
        self.resize(1600, 900)
        self._enable_3d = enable_3d
        self.datasets: list = []
        self.dataset = None
        self._iren_ready = False
        self._orientation = None
        self._mouse_mode = "trackball"
        self.vtk_widget = None
        self.renderer = None

        from ..render.scene import Scene
        self.scene = Scene(enable_3d=enable_3d)
        self._apply_style()
        self._build_central()
        self._build_menus()
        self._build_toolbars()
        self._build_statusbar()
        if filepath:
            self.open_file(filepath)
        else:
            self.message_win.log("Ready — File → Open to load FLD / FPH / GPH")

    # ── chrome ────────────────────────────────────────────────────────────

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background: #e8e8e8; }
            QMenuBar { background: #f0f0f0; }
            QToolBar { background: #f5f5f5; border: none; spacing: 2px;
                       padding: 2px; }
            QToolBar QToolButton {
                padding: 2px 6px 1px 6px; margin: 1px;
                border: 1px solid transparent; border-radius: 3px;
            }
            QToolBar QToolButton:hover {
                background: #e3f2fd; border: 1px solid #90caf9;
            }
            QToolBar QToolButton:pressed { background: #bbdefb; }
            #PaneFrame, #PaneBody {
                background: #ffffff;
                border: 1px solid #9a9a9a;
            }
            #PaneBody { border: none; }
            #PaneTitleBar {
                background: #d8d8d8;
                border-bottom: 1px solid #9a9a9a;
            }
            #PaneTitle { font-weight: bold; color: #333; }
            QStatusBar { background: #f0f0f0; }
            QTreeWidget { border: none; outline: none; }
            QTreeWidget::item { padding: 2px 0; }
        """)

    def _build_central(self) -> None:
        from .panes import MessageWindow, ObjectTree, PaneFrame, TimelineWindow

        self.object_tree = ObjectTree(self)
        self.object_tree.visibility_changed.connect(self._on_tree_visibility)
        self.object_tree.item_activated_name.connect(self._on_tree_activated)
        left = PaneFrame("Control Window", self.object_tree)

        if self._enable_3d:
            self.vtk_widget = QVTKRenderWindowInteractor(self)
            self.renderer = vtk.vtkRenderer()
            self.renderer.SetBackground(0.93, 0.93, 0.94)
            self.renderer.SetBackground2(0.78, 0.82, 0.90)
            self.renderer.GradientBackgroundOn()
            self.renderer.GetActiveCamera().ParallelProjectionOn()
            self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
            self.scene.renderer = self.renderer
            draw_body = self.vtk_widget
        else:
            self.vtk_widget = None
            draw_body = QLabel("3D disabled (headless test mode)", self)
            draw_body.setAlignment(Qt.AlignCenter)
        self.draw_pane = PaneFrame("Draw Window", draw_body)

        self.message_win = MessageWindow(self)
        self.msg_pane = PaneFrame("Message", self.message_win)

        self.timeline = TimelineWindow(self)
        self.timeline.mode_changed.connect(
            lambda m: self.message_win.log(f"Timeline mode: {m}"))
        self.timeline.step_changed.connect(self._on_timeline_step)
        self.timeline.play_requested.connect(
            lambda: self._nyi("Timeline Play"))
        self.timeline_pane = PaneFrame("Timeline Window", self.timeline)

        bottom = QSplitter(Qt.Horizontal, self)
        bottom.addWidget(self.msg_pane)
        bottom.addWidget(self.timeline_pane)
        bottom.setStretchFactor(0, 2)
        bottom.setStretchFactor(1, 3)
        bottom.setSizes([400, 600])

        right = QSplitter(Qt.Vertical, self)
        right.addWidget(self.draw_pane)
        right.addWidget(bottom)
        right.setStretchFactor(0, 5)
        right.setStretchFactor(1, 1)
        right.setSizes([640, 180])

        main = QSplitter(Qt.Horizontal, self)
        main.addWidget(left)
        main.addWidget(right)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        main.setSizes([300, 1300])
        self.setCentralWidget(main)
        self._main_splitter = main
        self._right_splitter = right

    def _build_statusbar(self) -> None:
        self._coord_label = QLabel("( —, —, — )")
        self._mode_label = QLabel("Navigation")
        self._op_label = QLabel("Trackball")
        self._cycle_label = QLabel("Cycle —")
        sb = self.statusBar()
        sb.addPermanentWidget(self._coord_label, 1)
        for w in (self._mode_label, self._op_label, self._cycle_label):
            sb.addPermanentWidget(w)
        self.status = sb
        self.status.showMessage("Ready")

    # ── menus / toolbars ──────────────────────────────────────────────────

    def _nyi(self, name: str) -> None:
        self.message_win.log(f"[{name}] not yet implemented", "WARN")
        self.status.showMessage(f"{name}: not yet implemented", 4000)

    def _build_menus(self) -> None:
        mb = self.menuBar()

        def add(menu, text, slot=None, shortcut=None):
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(shortcut)
            if slot:
                act.triggered.connect(slot)
            else:
                act.triggered.connect(
                    lambda _=False, t=text: self._nyi(t))
            menu.addAction(act)
            return act

        # File
        m = mb.addMenu("File")
        add(m, "Open…", self.on_open_dialog, QKeySequence.Open)
        add(m, "Save Status")
        add(m, "Print")
        m.addSeparator()
        add(m, "Exit", self.close)

        # Create (scPOST Create menu — stubs)
        m = mb.addMenu("Create")
        for name in (
            "Surface", "Plane", "Cylinder", "Circle", "Point",
            "Volume", "Isosurface", "Streamline", "Vector",
            "Colorbar", "Light", "Text", "Graph",
        ):
            add(m, name, lambda _=False, n=name: self._nyi(f"Create {n}"))

        # Display
        m = mb.addMenu("Display")
        add(m, "Redraw")
        add(m, "Show All", lambda: self._nyi("Show All"))
        add(m, "Hide All", lambda: self._nyi("Hide All"))

        # View
        m = mb.addMenu("View")
        add(m, "Fit", self.on_fit, "F")
        m.addSeparator()
        add(m, "YZ (X)", lambda: self.on_plane_view("x"), "X")
        add(m, "XZ (Y)", lambda: self.on_plane_view("y"), "Y")
        add(m, "XY (Z)", lambda: self.on_plane_view("z"), "Z")
        m.addSeparator()
        add(m, "Iso Metric")
        add(m, "Compare")
        m.addSeparator()
        self._act_view_msg = QAction("Message Window", self, checkable=True)
        self._act_view_msg.setChecked(True)
        self._act_view_msg.toggled.connect(self._toggle_message)
        m.addAction(self._act_view_msg)
        self._act_view_tl = QAction("Timeline Window", self, checkable=True)
        self._act_view_tl.setChecked(True)
        self._act_view_tl.toggled.connect(self._toggle_timeline)
        m.addAction(self._act_view_tl)
        self._act_view_status = QAction("Status Bar", self, checkable=True)
        self._act_view_status.setChecked(True)
        self._act_view_status.toggled.connect(
            lambda on: self.statusBar().setVisible(on))
        m.addAction(self._act_view_status)

        # Option
        m = mb.addMenu("Option")
        add(m, "Mouse 1-Button Mode")
        add(m, "Mouse 2-Button Mode")
        add(m, "Mouse 3-Button Mode",
            lambda: self._set_mouse_mode("trackball"))
        m.addSeparator()
        add(m, "Environment Settings")
        add(m, "Diagnostics")

        # Toolbar
        m = mb.addMenu("Toolbar")
        for attr, label in (
            ("tb_file", "File"),
            ("tb_create", "Create"),
            ("tb_display", "Display"),
            ("tb_view", "View"),
            ("tb_mouse", "Mouse"),
            ("tb_option", "Option"),
        ):
            act = QAction(label, self, checkable=True)
            act.setChecked(True)
            act.toggled.connect(
                lambda on, a=attr: self._toggle_toolbar(a, on))
            m.addAction(act)

        # Help
        m = mb.addMenu("Help")
        add(m, "About flowviewer", self._about)

    def _build_toolbars(self) -> None:
        from .icons import AppIcons
        icon_sz = 22

        def tb(name: str) -> QToolBar:
            bar = QToolBar(name, self)
            bar.setObjectName(name)
            bar.setMovable(False)
            bar.setIconSize(QSize(icon_sz, icon_sz))
            bar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            return bar

        def act(bar, text, icon, tip, slot):
            a = QAction(AppIcons.get(icon, icon_sz), text, self)
            a.setToolTip(tip)
            a.triggered.connect(slot)
            bar.addAction(a)
            return a

        self.tb_file = tb("File")
        act(self.tb_file, "Open", "open", "Open Field File", self.on_open_dialog)
        act(self.tb_file, "Save", "save", "Save Status",
            lambda: self._nyi("Save Status"))
        act(self.tb_file, "Print", "print", "Print",
            lambda: self._nyi("Print"))
        self.addToolBar(self.tb_file)

        self.tb_create = tb("Create")
        for text, icon in (
            ("Surface", "surface"),
            ("Plane", "plane_xy"),
            ("Iso", "isosurface"),
            ("Stream", "streamline"),
            ("Volume", "volume"),
            ("Vector", "vector"),
            ("Colorbar", "colorbar"),
            ("Point", "point"),
        ):
            act(self.tb_create, text, icon, f"Create {text}",
                lambda _=False, n=text: self._nyi(f"Create {n}"))
        self.addToolBar(self.tb_create)

        self.tb_display = tb("Display")
        act(self.tb_display, "Contour", "contour", "Contour display",
            lambda: self._nyi("Contour"))
        act(self.tb_display, "Show", "show_all", "Show All",
            lambda: self._nyi("Show All"))
        act(self.tb_display, "Redraw", "display", "Redraw",
            lambda: self._refresh_gl())
        self.addToolBar(self.tb_display)

        self.tb_view = tb("View")
        act(self.tb_view, "YZ", "plane_yz", "YZ view (X)",
            lambda: self.on_plane_view("x"))
        act(self.tb_view, "XZ", "plane_xz", "XZ view (Y)",
            lambda: self.on_plane_view("y"))
        act(self.tb_view, "XY", "plane_xy", "XY view (Z)",
            lambda: self.on_plane_view("z"))
        act(self.tb_view, "Fit", "fit", "Fit (F)", self.on_fit)
        act(self.tb_view, "Reset", "show_all", "Reset view", self.on_fit)
        self.addToolBar(self.tb_view)

        self.tb_mouse = tb("Mouse")
        self._act_trackball = act(
            self.tb_mouse, "Trackball", "rotate",
            "Trackball — L rotate / M pan / R zoom",
            lambda: self._set_mouse_mode("trackball"))
        self._act_rubber = act(
            self.tb_mouse, "Rubber", "zoom",
            "Rubber-band zoom",
            lambda: self._set_mouse_mode("rubber"))
        self._act_select = act(
            self.tb_mouse, "Select", "select",
            "Select mode",
            lambda: self._set_mouse_mode("select"))
        self._act_trackball.setCheckable(True)
        self._act_rubber.setCheckable(True)
        self._act_select.setCheckable(True)
        self._act_trackball.setChecked(True)
        self.addToolBar(self.tb_mouse)

        self.tb_option = tb("Option")
        act(self.tb_option, "Option", "option", "Environment Settings",
            lambda: self._nyi("Environment Settings"))
        act(self.tb_option, "Camera", "camera", "Camera",
            lambda: self._nyi("Camera"))
        act(self.tb_option, "Unit", "unit", "Unit settings",
            lambda: self._nyi("Unit settings"))
        self.addToolBar(self.tb_option)

    def _toggle_toolbar(self, attr: str, on: bool) -> None:
        bar = getattr(self, attr, None)
        if bar is not None:
            bar.setVisible(on)

    def _toggle_message(self, on: bool) -> None:
        self.msg_pane.setVisible(on)

    def _toggle_timeline(self, on: bool) -> None:
        self.timeline_pane.setVisible(on)

    def _about(self) -> None:
        from PyQt5.QtWidgets import QMessageBox
        from .. import __version__
        QMessageBox.about(
            self, "About flowviewer",
            f"<b>flowviewer</b> {__version__}<br>"
            "scPOST-style post-processor for FLD / FPH / GPH<br>"
            "PyQt5 + VTK")

    # ── actions ───────────────────────────────────────────────────────────

    def on_open_dialog(self) -> None:
        from .dialogs import OpenDialog
        dlg = OpenDialog(self)
        dlg.browse()
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            path = dlg.selected_path()
            if path:
                self.open_file(path)

    def open_file(self, filepath: str) -> None:
        from ..model.dataset import load_file
        self.status.showMessage(f"Loading {Path(filepath).name} …")
        self.message_win.log(f"Loading {filepath} …")
        try:
            ff = load_file(filepath)
        except Exception as exc:  # noqa: BLE001
            self.status.showMessage(f"Error: {exc}")
            self.message_win.log(f"Error loading {filepath}: {exc}", "ERROR")
            return
        self.dataset = ff
        if ff not in self.datasets:
            self.datasets.append(ff)
        self.scene.build(ff)
        if self._enable_3d:
            self.scene.fit()
            self._refresh_gl()
        self._populate_tree(ff)
        self.timeline.set_range(0, 0)
        self._cycle_label.setText("Cycle 0")
        self.setWindowTitle(f"flowviewer — {Path(filepath).name}")
        msg = (f"{ff.kind.upper()}: {ff.n_cells:,} cells, "
               f"{ff.n_vertices:,} vertices, {len(ff.variables)} variables")
        self.status.showMessage(msg)
        self.message_win.log(msg)

    def on_fit(self) -> None:
        self.scene.fit()
        self._refresh_gl()

    def on_plane_view(self, plane: str) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        from ..render.axes import plane_view_camera
        cam = self.renderer.GetActiveCamera()
        pos, up = plane_view_camera(plane)
        cam.SetPosition(*pos)
        cam.SetViewUp(*up)
        cam.SetFocalPoint(0, 0, 0)
        self.renderer.ResetCamera()
        self._ensure_parallel_camera()
        self._refresh_gl()

    def _ensure_parallel_camera(self) -> None:
        if self.renderer is not None:
            self.renderer.GetActiveCamera().ParallelProjectionOn()

    def _refresh_gl(self) -> None:
        if self._enable_3d and self.vtk_widget is not None:
            self.vtk_widget.GetRenderWindow().Render()

    def _populate_tree(self, ff) -> None:
        roots: list[tuple] = [("Main", [Path(ff.path).name])]
        if ff.parts:
            roots.append(("Parts", ff.parts))
        if ff.variable_names():
            roots.append(("Variables", ff.variable_names()))
        if ff.surface_regions:
            roots.append(("Boundary", [n for n, _ in ff.surface_regions]))
        elif ff.bc_plan:
            roots.append(("Boundary", [n for n, _, c in ff.bc_plan if c]))
        self.object_tree.clear_and_rebuild(roots)

    def _on_tree_visibility(self, name: str, on: bool) -> None:
        key = name.split(":")[0].strip()
        if key.startswith("Draw Window"):
            self.draw_pane.setVisible(on)
        elif key.startswith("Message"):
            self.msg_pane.setVisible(on)
            self._act_view_msg.blockSignals(True)
            self._act_view_msg.setChecked(on)
            self._act_view_msg.blockSignals(False)
        elif key.startswith("Timeline"):
            self.timeline_pane.setVisible(on)
            self._act_view_tl.blockSignals(True)
            self._act_view_tl.setChecked(on)
            self._act_view_tl.blockSignals(False)
        elif name in ("Option", "Camera", "Unit"):
            pass  # visibility only; settings via double-click
        else:
            # layer toggle for loaded objects
            layer = name.lower()
            if layer in ("main", "grid", "boundary", "parts", "variables"):
                self.scene.set_layer_visible(
                    "grid" if layer in ("main", "grid", "parts") else "bc",
                    on)
                self._refresh_gl()

    def _on_tree_activated(self, name: str) -> None:
        if name == "Unit":
            self._nyi("Unit settings")
        elif name == "Option":
            self._nyi("Option")
        elif name == "Camera":
            self._nyi("Camera")
        elif name.startswith("Draw Window"):
            self._nyi("Draw Window settings")

    def _on_timeline_step(self, step: int) -> None:
        self._cycle_label.setText(f"Cycle {step}")
        # Cycle switching arrives in a later milestone

    def _set_mouse_mode(self, mode: str) -> None:
        self._mouse_mode = mode
        self._op_label.setText(mode.capitalize())
        for act, name in (
            (self._act_trackball, "trackball"),
            (self._act_rubber, "rubber"),
            (self._act_select, "select"),
        ):
            act.setChecked(mode == name)
        if not self._enable_3d or self.vtk_widget is None or not self._iren_ready:
            return
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        if mode == "rubber":
            try:
                from vtkmodules.vtkInteractionStyle import (
                    vtkInteractorStyleRubberBandZoom)
            except Exception:
                vtkInteractorStyleRubberBandZoom = (
                    vtk.vtkInteractorStyleRubberBandZoom)
            iren.SetInteractorStyle(vtkInteractorStyleRubberBandZoom())
            self.message_win.log("Mouse: Rubber-band zoom")
        elif mode == "select":
            self.message_win.log("Mouse: Select (not yet wired)", "WARN")
            self._set_trackball_style(iren)
        else:
            self._set_trackball_style(iren)
            self.message_win.log(
                "Mouse: Trackball — L-rotate / M-pan / R-zoom")

    def _set_trackball_style(self, iren) -> None:
        try:
            from vtkmodules.vtkInteractionStyle import (
                vtkInteractorStyleTrackballCamera)
        except Exception:
            vtkInteractorStyleTrackballCamera = (
                vtk.vtkInteractorStyleTrackballCamera)
        self._trackball_style = vtkInteractorStyleTrackballCamera()
        iren.SetInteractorStyle(self._trackball_style)

    # ── showEvent delayed interactor init ─────────────────────────────────

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._enable_3d and not self._iren_ready and self.vtk_widget is not None:
            self._ensure_interactor()

    def _ensure_interactor(self) -> None:
        if not self._enable_3d or self.vtk_widget is None or self._iren_ready:
            return
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        self._set_trackball_style(iren)
        iren.AddObserver("MouseMoveEvent", self._on_vtk_mouse, 1.0)
        iren.Initialize()
        self._iren_ready = True
        self._set_orientation_marker(True)
        self._refresh_gl()

    def _set_orientation_marker(self, on: bool) -> None:
        if not self._enable_3d or self.vtk_widget is None:
            return
        if self._orientation is not None:
            try:
                self._orientation.SetEnabled(0)
            except Exception:
                pass
            self._orientation = None
        if not on:
            return
        try:
            from ..render.axes import orientation_marker_widget
            iren = self.vtk_widget.GetRenderWindow().GetInteractor()
            self._orientation = orientation_marker_widget(
                iren, corner="top-right")
        except Exception as exc:  # noqa: BLE001
            self.message_win.log(f"Orientation marker failed: {exc}", "WARN")

    def _on_vtk_mouse(self, obj, event) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        x, y = obj.GetEventPosition()
        picker = vtk.vtkWorldPointPicker()
        if picker.Pick(x, y, 0, self.renderer):
            p = picker.GetPickPosition()
            self._coord_label.setText(
                f"( {p[0]:.4g}, {p[1]:.4g}, {p[2]:.4g} )")


def run_gui(filepath: Optional[str] = None) -> int:
    if QApplication is None:
        print("PyQt5 not installed; cannot start GUI", file=sys.stderr)
        return 2
    app = QApplication.instance() or QApplication(sys.argv)
    win = FlowViewer(filepath=filepath, enable_3d=True)
    win.show()
    return app.exec_()
