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


_RENDERABLE_KINDS = ("surface", "plane", "particle", "isosurface",
                     "streamline", "volume", "colorbar", "point")

# Create-menu entry: (label, object kind). Non-core kinds map to interop
# objects that reuse a render pipeline (vector → isosurface vector tab).
_CREATE_MENU = (
    ("Surface", "surface"),
    ("Plane", "plane"),
    ("Cylinder", None),
    ("Circle", None),
    ("Point", "point"),
    ("Volume", "volume"),
    ("Isosurface", "isosurface"),
    ("Streamline", "streamline"),
    ("Vector", None),
    ("Colorbar", "colorbar"),
    ("Light", "light"),
    ("Text", None),
    ("Graph", None),
)

_CREATE_DISPLAY = {
    "Iso": "isosurface",
    "Stream": "streamline",
    "Volume": "volume",
    "Vector": None,
    "Colorbar": "colorbar",
    "Point": "point",
    "Surface": "surface",
    "Plane": "plane",
}


def _kind_for_text(text: str) -> Optional[str]:
    return _CREATE_DISPLAY.get(text)


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
        from .options import Options
        self.options = Options()
        self._enable_3d = enable_3d
        self.datasets: list = []
        self.dataset = None
        self.main_object = None
        self.fileset = None
        self._play_timer = None
        self._playing = False
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
        self.options.load_window(self)
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
        from .panes import (
            DrawSplitter, MessageWindow, ObjectTree, PaneFrame, PropertyHost,
            TimelineWindow,
        )

        self.object_tree = ObjectTree(self)
        self.object_tree.visibility_changed.connect(self._on_tree_visibility)
        self.object_tree.item_activated_name.connect(self._on_tree_activated)
        self.object_tree.object_activated.connect(self._on_object_activated)

        # scPOST Control Window: tree (upper) + Draw grip + tiled settings
        self.property_host = PropertyHost(self)
        self.property_host.applied.connect(self._on_property_applied)
        left_split = DrawSplitter(Qt.Vertical, self)
        left_split.addWidget(PaneFrame("Control Window", self.object_tree))
        left_split.addWidget(self.property_host)
        left_split.setStretchFactor(0, 3)
        left_split.setStretchFactor(1, 2)
        left_split.setSizes([320, 280])
        left_split.draw_requested.connect(self._on_draw_clicked)
        self._left_splitter = left_split
        left = left_split

        if self._enable_3d:
            self.vtk_widget = QVTKRenderWindowInteractor(self)
            self.renderer = vtk.vtkRenderer()
            # scPOST Draw Window: near-white + light gradient
            self.renderer.SetBackground(1.0, 1.0, 1.0)
            self.renderer.SetBackground2(0.92, 0.94, 0.97)
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
        self.timeline.play_requested.connect(self._on_timeline_play)
        self.timeline.pause_requested.connect(self._on_timeline_pause)
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
        add(m, "Save Status", self.on_save_status)
        add(m, "Print", self.on_print)
        add(m, "Export PNG…", self.on_export_png)
        m.addSeparator()
        add(m, "Exit", self.close)

        # Create (scPOST Create menu)
        m = mb.addMenu("Create")
        for name, _kind in _CREATE_MENU:
            add(m, name, lambda _=False, k=_kind: self._create_object(k))

        # Display
        m = mb.addMenu("Display")
        add(m, "Redraw", self.on_redraw)
        add(m, "Show All", self.on_show_all_objects)
        add(m, "Hide All", self.on_hide_all_objects)

        # View
        m = mb.addMenu("View")
        add(m, "Fit", self.on_fit, "F")
        m.addSeparator()
        add(m, "YZ (X)", lambda: self.on_plane_view("x"), "X")
        add(m, "XZ (Y)", lambda: self.on_plane_view("y"), "Y")
        add(m, "XY (Z)", lambda: self.on_plane_view("z"), "Z")
        m.addSeparator()
        add(m, "Iso Metric", self.on_iso_metric, "I")
        add(m, "Compare", self.on_compare_view)
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
        add(m, "Mouse 1-Button Mode",
            lambda: self._set_mouse_mode("trackball"))
        add(m, "Mouse 2-Button Mode",
            lambda: self._set_mouse_mode("rubber"))
        add(m, "Mouse 3-Button Mode",
            lambda: self._set_mouse_mode("trackball"))
        m.addSeparator()
        add(m, "Environment Settings", self.on_environment_settings)
        add(m, "Diagnostics", self.on_diagnostics)

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
            self.on_save_status)
        act(self.tb_file, "Print", "print", "Print", self.on_print)
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
                lambda _=False, n=text: self._create_object(_kind_for_text(n)))
        self.addToolBar(self.tb_create)

        self.tb_display = tb("Display")
        act(self.tb_display, "Contour", "contour", "Contour display",
            self.on_contour_display)
        act(self.tb_display, "Show", "show_all", "Show All",
            self.on_show_all_objects)
        act(self.tb_display, "Redraw", "display", "Redraw",
            lambda: self.on_redraw())
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
            self.on_environment_settings)
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
        """File → Open…: native Explorer dialog with correct Qt filters."""
        from PyQt5.QtWidgets import QFileDialog
        from .dialogs import qt_file_filters

        start = str(Path.cwd())
        if self.dataset is not None and getattr(self.dataset, "path", None):
            start = str(Path(self.dataset.path).parent)
        filters, selected = qt_file_filters(0)  # Field files (*.fld *.fph …)
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Field File", start, filters, selected)
        if not path:
            return
        from ..model import loaders
        if not loaders.can_load(path):
            self.message_win.log(loaders.describe(path), "WARN")
            self.status.showMessage(
                f"Open: {Path(path).name} — not yet supported", 6000)
            return
        self.open_file(path)

    def open_file(self, filepath: str, options=None) -> None:
        from ..model.dataset import load_file
        from ..model.objects import MainObject
        if options is not None and getattr(options, "close_current", False):
            self._close_current_files()
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
        # scPOST Magic-open defaults: Surface(1) / Plane(1) [/ Particle(1)]
        self.main_object = MainObject.from_field_file(ff, magic=True)
        self.scene.build(ff, main=self.main_object)
        if self._enable_3d:
            self.scene.fit()
            self._refresh_gl()
        self.object_tree.load_main(self.main_object)
        # Auto-open first object settings in the tiled pane (scPOST-like)
        if self.main_object.children:
            first = self.main_object.children[0]
            self.property_host.show_object(
                first.kind, first, field_file=ff)
            item = self.object_tree._items.get(first.label)
            if item is not None:
                self.object_tree.blockSignals(True)
                self.object_tree.setCurrentItem(item)
                self.object_tree.blockSignals(False)
        cyc = ff.cycle if ff.cycle is not None else 0
        self.fileset = None
        if options is None or not getattr(options, "single_file", False):
            from ..model.fileset import scan_sequence
            try:
                self.fileset = scan_sequence(str(Path(filepath)))
            except Exception:  # noqa: BLE001
                self.fileset = None
        if self.fileset and len(self.fileset) > 1:
            lo, hi = self.fileset.min_cycle(), self.fileset.max_cycle()
            if lo is not None and hi is not None:
                self.timeline.set_range(lo, hi)
                self.message_win.log(
                    f"FileSet: {len(self.fileset)} steps "
                    f"({Path(filepath).name} in sequence)")
                if not (lo <= cyc <= hi):
                    cyc = lo
        else:
            self.timeline.set_range(cyc, cyc)
        self.timeline.set_step(cyc)
        self._cycle_label.setText(f"Cycle {cyc}")
        if ff.time is not None:
            self.timeline.edit_time.setText(f"{ff.time:.6g}")
        self.setWindowTitle(f"flowviewer — {Path(filepath).name}")
        kids = ", ".join(o.label for o in self.main_object.children)
        msg = (f"{ff.kind.upper()}: {ff.n_cells:,} cells, "
               f"{ff.n_vertices:,} vertices, {len(ff.variables)} variables"
               f" | Cycle={ff.cycle} Time={ff.time}")
        self.status.showMessage(msg)
        self.message_win.log(msg)
        self.message_win.log(
            f"Initialized objects: {kids}"
            + (" (+ particles)" if ff.has_particles else ""))
        if options is not None:
            if getattr(options, "accelerate_memory", False):
                self.message_win.log(
                    "Option: accelerate using more memory "
                    "(hash table — deferred)")
            if getattr(options, "read_faster", False):
                self.message_win.log(
                    "Option: read faster by estimating file size "
                    "(old field files — deferred)")

    def _close_current_files(self) -> None:
        """Clear loaded datasets / scene (Read after closing current files)."""
        self.datasets.clear()
        self.dataset = None
        self.main_object = None
        self.fileset = None
        self._on_timeline_pause()
        self.scene.reset()
        self.object_tree.build_startup_tree()
        self.property_host.clear()
        self.timeline.set_range(0, 0)
        self._cycle_label.setText("Cycle —")
        self.setWindowTitle("flowviewer")
        self.message_win.log("Closed current files")
        self._refresh_gl()

    def on_save_status(self) -> None:
        """File → Save Status: persist the object tree to a JSON ``.sta``."""
        if self.main_object is None:
            self.message_win.log("Save Status: no file loaded", "WARN")
            return
        from PyQt5.QtWidgets import QFileDialog
        default = (f"{Path(self.dataset.path).stem}.sta"
                   if self.dataset else "flowviewer.sta")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Status", default, "Status files (*.sta)")
        if not path:
            return
        from ..render.export import save_status
        ok = save_status(self.main_object, path)
        self.message_win.log(
            f"Save Status {'OK' if ok else 'failed'}: {path}",
            "" if ok else "ERROR")
        if ok:
            self.status.showMessage(f"Saved status → {Path(path).name}", 5000)

    def on_print(self) -> None:
        """File → Print: send the rendered scene to the printer."""
        from ..render.export import print_scene
        ok = print_scene(self.scene, parent=self)
        self.message_win.log(
            "Print: sent to printer" if ok else "Print: nothing to print",
            "" if ok else "WARN")

    def on_export_png(self) -> None:
        """File → Export PNG…: render the current scene to an image file."""
        if not (self._enable_3d and self.renderer is not None):
            self.message_win.log(
                "Export PNG: no render window (headless)", "WARN")
            return
        from PyQt5.QtWidgets import QFileDialog
        default = (f"{Path(self.dataset.path).stem}.png"
                   if self.dataset else "export.png")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", default, "PNG image (*.png)")
        if not path:
            return
        from ..render.export import snapshot_png
        ok = snapshot_png(self.renderer, path)
        self.message_win.log(
            f"Export PNG {'OK' if ok else 'failed'}: {path}",
            "" if ok else "ERROR")
        if ok:
            self.status.showMessage(f"Exported → {Path(path).name}", 5000)

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

    def on_iso_metric(self) -> None:
        """View → Iso Metric: camera along the (+,+,+) diagonal."""
        if not self._enable_3d or self.renderer is None:
            return
        from ..render.axes import iso_metric_camera
        cam = self.renderer.GetActiveCamera()
        pos, up = iso_metric_camera()
        cam.SetPosition(*pos)
        cam.SetViewUp(*up)
        cam.SetFocalPoint(0, 0, 0)
        self.renderer.ResetCamera()
        self._ensure_parallel_camera()
        self._refresh_gl()
        self.message_win.log("View: Iso Metric")

    def on_compare_view(self) -> None:
        """View → Compare: side-by-side snapshot of the two last datasets."""
        if len(self.datasets) < 2:
            self.message_win.log(
                "Compare: needs ≥2 loaded datasets (File → Open each)",
                "WARN")
            return
        names = "  vs  ".join(Path(d.path).name for d in self.datasets[-2:])
        self.message_win.log(f"Compare view: {names} (split-screen, TBD)")

    def on_contour_display(self) -> None:
        """Display → Contour: rebuild scene showing contour colours."""
        if self.dataset is None or self.main_object is None:
            self.message_win.log("Contour: open a field file first", "WARN")
            return
        self.scene.build(self.dataset, main=self.main_object)
        if self._enable_3d:
            self.scene.fit()
            self._refresh_gl()
        self.message_win.log("Display: Contour recomputed")

    def on_show_all_objects(self) -> None:
        self._set_all_objects_visible(True)

    def on_hide_all_objects(self) -> None:
        self._set_all_objects_visible(False)

    def _set_all_objects_visible(self, on: bool) -> None:
        if self.main_object is None:
            self.message_win.log("No file loaded", "WARN")
            return
        for o in getattr(self.main_object, "children", []) or []:
            o.visible = on
        self.scene.build(self.dataset, main=self.main_object)
        if self._enable_3d:
            self.scene.fit()
            self._refresh_gl()
        self.message_win.log(f"Display: {'Show' if on else 'Hide'} all objects")
        self.object_tree.load_main(self.main_object)

    def on_redraw(self) -> None:
        """Display → Redraw: force a full repaint + refresh scene."""
        self._refresh_gl()
        if self.dataset is not None and self.main_object is not None:
            self.scene.build(self.dataset, main=self.main_object)
            if self._enable_3d:
                self._refresh_gl()
        self.message_win.log("Redraw")

    def on_environment_settings(self) -> None:
        """Option → Environment Settings: minimal settings dialog."""
        from .dialogs import EnvironmentDialog
        dlg = EnvironmentDialog(self)
        dlg.exec_()

    def on_diagnostics(self) -> None:
        """Option → Diagnostics: dump internal state to the message log."""
        lines = [
            "Diagnostics:",
            f"  dataset: {getattr(self.dataset, 'kind', None)} "
            f"({getattr(self.dataset, 'n_cells', 0):,} cells)",
            f"  objects: {len(self.main_object.children) if self.main_object else 0}",
            f"  scene actors: {len(self.scene.actor_names())} layers",
            f"  fileset: {len(self.fileset) if self.fileset else 0} steps",
            f"  mouse: {self._mouse_mode}",
        ]
        for line in lines:
            self.message_win.log(line)

    def _refresh_gl(self) -> None:
        if self._enable_3d and self.vtk_widget is not None:
            self.vtk_widget.GetRenderWindow().Render()

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
        elif name in ("Option", "Camera", "Unit", "Light (1)"):
            return
        else:
            kind = self.object_tree._object_kinds.get(name, "")
            layer = {
                "surface": "surface",
                "plane": "plane",
                "particle": "particle",
                "isosurface": "isosurface",
                "streamline": "streamline",
                "volume": "volume",
                "colorbar": "colorbar",
                "point": "point",
                "main": "grid",
            }.get(kind, "")
            if layer:
                # Surface shares the wireframe grid actors
                if layer == "surface":
                    self.scene.set_layer_visible("grid", on)
                    self.scene.set_layer_visible("surface", on)
                else:
                    self.scene.set_layer_visible(layer, on)
                if self.main_object is not None:
                    for obj in self.main_object.children:
                        if obj.label == name:
                            obj.visible = on
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

    def _on_object_activated(self, kind: str, label: str) -> None:
        """Select / double-click a renderable object → tiled settings pane."""
        if self.main_object is None or self.dataset is None:
            return
        if kind not in _RENDERABLE_KINDS:
            return
        obj = next((o for o in self.main_object.children
                    if o.label == label), None)
        if obj is None:
            return
        siblings = [o for o in self.main_object.children if o is not obj]
        self.property_host.show_object(kind, obj, field_file=self.dataset,
                                       siblings=siblings)
        # Ensure the lower pane is visible after hide
        self.property_host.setVisible(True)

    def _on_draw_clicked(self) -> None:
        """scPOST Draw (mallet) on the Control Window splitter grip.

        Commits the current settings pane and redraws the Draw Window —
        replaces per-panel Apply buttons.
        """
        if self.property_host.current_panel is None:
            # No settings pane — just refresh the current scene
            self._refresh_gl()
            self.status.showMessage("Draw", 2000)
            return
        if not self.property_host.apply_now():
            self._refresh_gl()

    def _on_property_applied(self, obj) -> None:
        """After Draw / apply_now → rebuild the affected object.

        Uses the incremental ``Scene.apply_to_object`` path when the scene is
        already built so sibling actors / camera stay untouched (I-gap).
        """
        if self.dataset is None or self.main_object is None:
            return
        if self.scene._field_file is not None:
            self.scene.apply_to_object(self.dataset, obj)
        else:
            self.scene.build(self.dataset, main=self.main_object)
        if self._enable_3d:
            self._refresh_gl()
        label = getattr(obj, "label", str(obj))
        self.message_win.log(f"Draw: applied {label}")
        self.status.showMessage(f"Draw: {label}", 3000)

    def _create_object(self, kind: Optional[str]) -> None:
        """Create menu / toolbar: instantiate an object under the Main node."""
        if kind is None:
            self._nyi("Create (kind not implemented)")
            return
        if self.dataset is None or self.main_object is None:
            self.message_win.log(
                "Create: open a field file first (File → Open)", "WARN")
            return
        from ..model import objects as objmod
        makers = {
            "surface": objmod.SurfaceObject,
            "plane": objmod.PlaneObject,
            "point": objmod.PointObject,
            "volume": objmod.VolumeObject,
            "isosurface": objmod.IsosurfaceObject,
            "streamline": objmod.StreamlineObject,
            "colorbar": objmod.ColorbarObject,
        }
        maker = makers.get(kind)
        if maker is None:
            self._nyi(f"Create {kind}")
            return
        used = {o.label for o in self.main_object.children}
        index = 1
        while f"{kind.capitalize()} ({index})" in used:
            index += 1
        obj = maker(index=index)
        self.main_object.children.append(obj)
        self.scene.build(self.dataset, main=self.main_object)
        if self._enable_3d:
            self.scene.fit()
            self._refresh_gl()
        self.object_tree.load_main(self.main_object)
        siblings = [o for o in self.main_object.children if o is not obj]
        self.property_host.show_object(kind, obj, field_file=self.dataset,
                                       siblings=siblings)
        self.property_host.setVisible(True)
        self.message_win.log(f"Created {getattr(obj, 'label', kind)}")

    def _on_timeline_step(self, step: int) -> None:
        self._cycle_label.setText(f"Cycle {step}")
        if self.dataset is None or self.main_object is None:
            return
        # Cycle / Time mode → load the corresponding sequence member's data
        if self.fileset and self.timeline.mode() in ("Cycle", "Time"):
            member = self.fileset.find(int(step))
            loaded = None
            if member is not None:
                from ..model.dataset import load_file
                try:
                    loaded = load_file(member.path)
                except Exception as exc:  # noqa: BLE001
                    self.message_win.log(
                        f"Cycle load failed: {member.path}: {exc}", "ERROR")
            if loaded is not None and loaded is not self.dataset:
                self.dataset = loaded
                self.scene.build(loaded, main=self.main_object)
                if self._enable_3d:
                    self.scene.fit()
                    self._refresh_gl()
                self.timeline.edit_time.setText(
                    f"{loaded.time:.6g}" if loaded.time is not None else "")
                msg = (f"{loaded.kind.upper()}: {loaded.n_cells:,} cells, "
                       f"{loaded.n_vertices:,} vertices, "
                       f"{len(loaded.variables)} variables"
                       f" | Cycle={loaded.cycle} Time={loaded.time}")
                self.status.showMessage(msg)
                self.message_win.log(msg)
        # Automove planes animate with the timeline slider (P3.10)
        has_auto = any(
            getattr(o, "automove_enabled", False)
            for o in getattr(self.main_object, "children", []))
        if has_auto:
            self.scene.animate(step)
            if self._enable_3d:
                self._refresh_gl()

    def _on_timeline_play(self) -> None:
        """Play steps forward through the FileSet cycle range."""
        if self.fileset is None or not self.fileset or QtCore is None:
            return
        self._playing = True
        if self._play_timer is None:
            self._play_timer = QtCore.QTimer(self)
            self._play_timer.setInterval(250)
            self._play_timer.timeout.connect(self._play_tick)
        self._play_timer.start()

    def _play_tick(self) -> None:
        if not self._playing:
            return
        if self.fileset is None or not self.fileset:
            self._on_timeline_pause()
            return
        step = self.timeline.current_step() + 1
        hi = self.fileset.max_cycle() or 0
        if step > hi:
            if self.timeline.chk_loop.isChecked():
                step = self.fileset.min_cycle() or 0
            else:
                self._on_timeline_pause()
                return
        self.timeline.set_step(step)
        self._on_timeline_step(step)

    def _on_timeline_pause(self) -> None:
        self._playing = False
        if self._play_timer is not None:
            self._play_timer.stop()

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

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            if getattr(self, "options", None) is not None:
                self.options.save_window(self)
        finally:
            super().closeEvent(event)

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
        iren.AddObserver("LeftButtonPressEvent", self._on_vtk_pick, 1.0)
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
                iren, corner="bottom-left")
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

    def _on_vtk_pick(self, obj, event) -> None:
        """Left-click pick: probe scalar/vector on the picked plane (P3.11)."""
        if not self._enable_3d or self.renderer is None:
            return
        if self.dataset is None or self.main_object is None:
            return
        x, y = obj.GetEventPosition()
        point, owner = self.scene.pick_actor(x, y)
        if point is None or owner is None:
            return
        kind, plane = owner
        if kind != "plane":
            return
        if not (getattr(plane, "pick_scalar", True)
                or getattr(plane, "pick_vector", False)):
            return
        from ..render.plane import pick_point
        res = pick_point(self.dataset, plane, point)
        lines = [f"Pick at ({point[0]:.4g}, {point[1]:.4g}, {point[2]:.4g})"]
        if "scalar" in res:
            name, val = res["scalar"]
            lines.append(f"  {name} = {val:.6g}")
        if "vector" in res:
            name, (vx, vy, vz) = res["vector"]
            lines.append(f"  {name} = ({vx:.6g}, {vy:.6g}, {vz:.6g})")
        self.message_win.log("\n".join(lines))


def run_gui(filepath: Optional[str] = None) -> int:
    if QApplication is None:
        print("PyQt5 not installed; cannot start GUI", file=sys.stderr)
        return 2
    app = QApplication.instance() or QApplication(sys.argv)
    win = FlowViewer(filepath=filepath, enable_3d=True)
    win.show()
    return app.exec_()
