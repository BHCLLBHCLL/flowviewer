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
                     "streamline", "volume", "colorbar", "point",
                     "light", "pathline", "cylinder", "circle",
                     "text", "bitmap", "information", "mirror",
                     "timeseries", "maxmin", "graph", "grouping",
                     "curve", "periodical", "measure", "folder",
                     "bar", "regionbc", "gradation", "camera", "region",
                     "turbo", "ufo")

# Create-menu entry: (label, object kind). "Vector" maps to a Plane —
# scPOST has no standalone vector object; the Plane Vector tab is the
# most complete glyph pipeline (positions/projection/fixed length).
_CREATE_MENU = (
    ("Surface", "surface"),
    ("Plane", "plane"),
    ("Cylinder", "cylinder"),
    ("Circle", "circle"),
    ("Point", "point"),
    ("Volume", "volume"),
    ("Isosurface", "isosurface"),
    ("Streamline", "streamline"),
    ("Pathline", "pathline"),
    ("Vector", "plane"),
    ("Colorbar", "colorbar"),
    ("Light", "light"),
    ("Text", "text"),
    ("Graph", "graph"),
)

# Secondary objects (scPOST Create-menu tail) offered under a submenu.
_CREATE_MORE = (
    ("Bar", "bar"),
    ("Bitmap", "bitmap"),
    ("Curve", "curve"),
    ("Folder", "folder"),
    ("Gradation", "gradation"),
    ("Grouping", "grouping"),
    ("Information", "information"),
    ("Max and Min", "maxmin"),
    ("Measure", "measure"),
    ("Mirror Copy", "mirror"),
    ("Periodical Copy", "periodical"),
    ("Region", "region"),
    ("Region BC", "regionbc"),
    ("Time Series", "timeseries"),
    ("Turbo", "turbo"),
    ("UFO", "ufo"),
)

_CREATE_DISPLAY = {
    "Iso": "isosurface",
    "Stream": "streamline",
    "Volume": "volume",
    "Vector": "plane",
    "Colorbar": "colorbar",
    "Point": "point",
    "Surface": "surface",
    "Plane": "plane",
    "Cylinder": "cylinder",
    "Circle": "circle",
    "Text": "text",
    "Graph": "graph",
}


def _kind_for_text(text: str) -> Optional[str]:
    return _CREATE_DISPLAY.get(text)


def _object_position(obj) -> tuple:
    """Best-effort anchor position for an object's name label (C3)."""
    for attr in ("position", "point", "center", "point1"):
        v = getattr(obj, attr, None)
        if isinstance(v, (tuple, list)) and len(v) == 3:
            return tuple(float(x) for x in v)
    return (0.0, 0.0, 0.0)

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
        self._member_cache: dict = {}  # {path: FieldFile} shared by playback/interp
        self._play_timer = None
        self._playing = False
        self._iren_ready = False
        self._orientation = None
        self._mouse_mode = "trackball"
        self.vtk_widget = None
        self.renderer = None
        # Global Light (P0.3): scPOST keeps one Light under Global Objects
        from ..model.objects import CameraObject, LightObject
        from ..model.objects import ColorbarObject, GradationObject, GlobalWindow
        self._global_light = LightObject(index=1)
        self._global_camera = CameraObject(index=1)
        self.global_window = GlobalWindow(
            colorbar=ColorbarObject(index=1),
            gradation=GradationObject(index=1),
            camera=self._global_camera,
            light=self._global_light)
        self._load_workers = []             # keep LoadWorker/QThread alive (P0.6)
        self._undo_stack = []               # P2.8 deep-copied children lists
        self._redo_stack = []

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

        # R2.7: expose this instance to the COM automation bridge.
        try:
            from ..com import attach_gui
            attach_gui(self)
        except Exception:
            pass

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
        if getattr(self.object_tree, "delete_requested", None) is not None:
            self.object_tree.delete_requested.connect(
                lambda label: self.on_delete_object(label))
            self.object_tree.duplicate_requested.connect(
                lambda label: self.on_duplicate_object(label))
        if getattr(self.object_tree, "rename_requested", None) is not None:
            self.object_tree.rename_requested.connect(
                lambda label: self.on_rename_object(label))
            self.object_tree.lock_requested.connect(
                lambda label: self.on_toggle_lock(label))

        # scPOST Control Window: tree (upper) + Draw grip + tiled settings
        self.property_host = PropertyHost(self)
        self.property_host.applied.connect(self._on_property_applied)
        if getattr(self.property_host, "before_apply", None) is not None:
            self.property_host.before_apply.connect(self._on_before_apply)
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
        if getattr(self.timeline, "interp_requested", None) is not None:
            self.timeline.interp_requested.connect(self._on_timeline_interp)
            self.timeline.time_set_requested.connect(
                self._on_timeline_time_request)
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
        self._cells_label = QLabel("Cells —")   # R0.8
        self._pick_label = QLabel("Pick —")     # R0.8
        self._cycle_label = QLabel("Cycle —")
        sb = self.statusBar()
        sb.addPermanentWidget(self._coord_label, 1)
        for w in (self._mode_label, self._op_label, self._cells_label,
                  self._pick_label, self._cycle_label):
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
        add(m, "Export STL…", self.on_export_stl)
        add(m, "Export OBJ…", self.on_export_obj)
        add(m, "Export VRML…", self.on_export_vrml)
        add(m, "Export glTF…", self.on_export_gltf)
        add(m, "Export Animation Frames…", self.on_export_animation_frames)
        add(m, "Export Animation Video…", self.on_export_animation_video)
        m.addSeparator()
        add(m, "Exit", self.close)

        # Create (scPOST Create menu)
        m = mb.addMenu("Create")
        for name, _kind in _CREATE_MENU:
            add(m, name, lambda _=False, k=_kind: self._create_object(k))
        m.addSeparator()
        sub = m.addMenu("More Objects")
        for name, _kind in _CREATE_MORE:
            add(sub, name, lambda _=False, k=_kind: self._create_object(k))

        # Edit (undo/redo over object-tree changes, P0.3)
        m = mb.addMenu("Edit")
        add(m, "Undo", self.on_undo, QKeySequence.Undo)
        add(m, "Redo", self.on_redo, QKeySequence.Redo)
        m.addSeparator()
        add(m, "Delete Object",
            lambda _=False: self.on_delete_object(), QKeySequence.Delete)
        add(m, "Duplicate Object",
            lambda _=False: self.on_duplicate_object(), "Ctrl+D")
        m.addSeparator()
        add(m, "Delete Selected",
            lambda _=False: self.on_delete_selected())
        add(m, "Hide Selected",
            lambda _=False: self.on_hide_selected(True))
        add(m, "Show Selected",
            lambda _=False: self.on_hide_selected(False))

        # Display
        m = mb.addMenu("Display")
        add(m, "Redraw", self.on_redraw)
        add(m, "Show All", self.on_show_all_objects)
        add(m, "Hide All", self.on_hide_all_objects)
        add(m, "Variable Registration…", self.on_variable_registration)

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
        add(m, "VR Mode", self.on_vr_mode)
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
            self._open_camera_dialog)
        act(self.tb_option, "Unit", "unit", "Unit settings",
            self.on_unit_settings)
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

        # Start where the user last opened/saved (P0.6): options.last_dir,
        # then the current dataset's folder, then cwd.
        start = None
        last = self.options.last_dir
        if last and Path(last).is_dir():
            start = str(last)
        if start is None and self.dataset is not None \
                and getattr(self.dataset, "path", None):
            start = str(Path(self.dataset.path).parent)
        start = start or str(Path.cwd())
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
        self._open_file_async(path)

    def open_file(self, filepath: str, options=None) -> None:
        """Synchronous open (CLI / tests); the GUI uses _open_file_async."""
        from ..model.dataset import load_file
        if options is not None and getattr(options, "close_current", False):
            self._close_current_files()
        self.status.showMessage(f"Loading {Path(filepath).name} …")
        self.message_win.log(f"Loading {filepath} …")
        try:
            ff = load_file(filepath)
        except Exception as exc:  # noqa: BLE001
            self._on_load_failed(str(exc), filepath=filepath)
            return
        self._finalize_open(ff, options=options)

    def _open_file_async(self, filepath: str, options=None) -> None:
        """File → Open: parse on a worker thread (P0.6)."""
        if options is not None and getattr(options, "close_current", False):
            self._close_current_files()
        self.status.showMessage(f"Loading {Path(filepath).name} …")
        self.message_win.log(f"Loading {filepath} …")
        try:
            from .tasks import _HAS_QT
        except Exception:  # pragma: no cover - headless
            _HAS_QT = False
        if not _HAS_QT:
            self.open_file(filepath, options=None)
            return
        from .tasks import launch_load
        holder: list = []

        def _done(ff):
            self._finalize_open(ff, options)
            if holder and holder[0] in self._load_workers:
                self._load_workers.remove(holder[0])

        def _failed(msg):
            self._on_load_failed(msg)
            if holder and holder[0] in self._load_workers:
                self._load_workers.remove(holder[0])

        worker = launch_load(filepath, on_finished=_done, on_failed=_failed)
        holder.append(worker)
        self._load_workers.append(worker)

    def _on_load_failed(self, msg: str, *, filepath: str = "") -> None:
        """Report a failed load to status bar + message window."""
        self.status.showMessage(f"Error: {msg}")
        if filepath:
            self.message_win.log(f"Error loading {filepath}: {msg}", "ERROR")
        else:
            self.message_win.log(f"Error: {msg}", "ERROR")

    def _finalize_open(self, ff, options=None) -> None:
        """Wire a parsed FieldFile into the window (shared tail)."""
        from ..model.objects import MainObject
        self.dataset = ff
        if ff not in self.datasets:
            self.datasets.append(ff)
        # Remember the folder for the next Open dialog (P0.6)
        try:
            self.options.last_dir = str(Path(ff.path).parent)
        except Exception:  # pragma: no cover - options are best-effort
            pass
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
        self._member_cache = {}
        if options is None or not getattr(options, "single_file", False):
            from ..model.fileset import scan_sequence
            try:
                self.fileset = scan_sequence(str(Path(ff.path)))
            except Exception:  # noqa: BLE001
                self.fileset = None
        if self.fileset and len(self.fileset) > 1:
            lo, hi = self.fileset.min_cycle(), self.fileset.max_cycle()
            if lo is not None and hi is not None:
                self.timeline.set_range(lo, hi)
                self.message_win.log(
                    f"FileSet: {len(self.fileset)} steps "
                    f"({Path(ff.path).name} in sequence)")
                if not (lo <= cyc <= hi):
                    cyc = lo
        else:
            self.timeline.set_range(cyc, cyc)
        self.timeline.set_step(cyc)
        self._cycle_label.setText(f"Cycle {cyc}")
        try:  # R0.8: cell count in the status bar
            self._cells_label.setText(f"Cells {self.dataset.n_cells:,}")
        except Exception:  # noqa: BLE001
            self._cells_label.setText("Cells —")
        if ff.time is not None:
            self.timeline.edit_time.setText(self.timeline.format_time(ff.time))
        self.setWindowTitle(f"flowviewer — {Path(ff.path).name}")
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
        self._member_cache = {}
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

    def _export_dialog(self, caption: str, filter_: str, default: str) -> str:
        """Common save-file prompt; returns the chosen path or ''."""
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, caption, default, filter_)
        return path or ""

    def on_export_obj(self) -> None:
        """File > Export OBJ… (4, FBX-neutral)."""
        if self.dataset is None:
            self.status.showMessage("Open a field file first", 4000)
            return
        from ..render.export import export_surface_obj
        path = self._export_dialog("Export OBJ", "OBJ (*.obj)", "model.obj")
        if not path:
            return
        ok = export_surface_obj(self.dataset, path)
        self.message_win.log(f"Export OBJ {'OK' if ok else 'failed'}: {path}")
        self.status.showMessage(f"OBJ {'exported' if ok else 'failed'}", 4000)

    def on_export_stl(self) -> None:
        """File > Export STL… (P3.2)."""
        if self.dataset is None:
            self.status.showMessage("Open a field file first", 4000)
            return
        from ..render.export import export_surface_stl
        path = self._export_dialog("Export STL", "STL (*.stl)", "model.stl")
        if not path:
            return
        ok = export_surface_stl(self.dataset, path)
        self.message_win.log(f"Export STL {'OK' if ok else 'failed'}: {path}")
        self.status.showMessage(f"STL {'exported' if ok else 'failed'}", 4000)

    def on_export_vrml(self) -> None:
        """File > Export VRML… (P3.2)."""
        path = self._export_dialog("Export VRML", "VRML (*.wrl)", "scene.wrl")
        if not path:
            return
        from ..render.export import export_scene_vrml
        rw = (self.vtk_widget.GetRenderWindow()
              if self.vtk_widget is not None else None)
        ok = export_scene_vrml(rw, path) if rw is not None else False
        self.message_win.log(f"Export VRML {'OK' if ok else 'failed'}: {path}")

    def on_export_gltf(self) -> None:
        """File > Export glTF… (P3.2)."""
        path = self._export_dialog("Export glTF", "glTF (*.gltf)", "scene.gltf")
        if not path:
            return
        from ..render.export import export_scene_gltf
        rw = (self.vtk_widget.GetRenderWindow()
              if self.vtk_widget is not None else None)
        ok = export_scene_gltf(rw, path) if rw is not None else False
        self.message_win.log(f"Export glTF {'OK' if ok else 'failed'}: {path}")

    def on_export_animation_frames(self) -> None:
        """File > Export Animation Frames… (G5): automove PNG sequence."""
        if not self._enable_3d or self.vtk_widget is None:
            self.message_win.log("Animation export needs 3D mode", "WARN")
            return
        if self.dataset is None or self.main_object is None:
            self.status.showMessage("Open a field file first", 4000)
            return
        from PyQt5.QtWidgets import QFileDialog, QInputDialog
        frames, ok = QInputDialog.getInt(
            self, "Export Animation Frames", "Frames:", 30, 2, 500)
        if not ok:
            return
        out_dir = QFileDialog.getExistingDirectory(
            self, "Output folder", "")
        if not out_dir:
            return
        from ..render.export import export_animation_frames
        n = export_animation_frames(
            self.dataset, self.main_object, self.scene,
            self.vtk_widget.GetRenderWindow(), out_dir,
            frames=frames, fps=15)
        self.message_win.log(
            f"Exported {n} animation frames to {out_dir}")
        self.status.showMessage(f"Exported {n} frames", 5000)

    def on_export_animation_video(self) -> None:
        """File > Export Animation Video… (R3.2): encode MP4/AVI via ffmpeg."""
        if not self._enable_3d or self.vtk_widget is None:
            self.message_win.log("Animation export needs 3D mode", "WARN")
            return
        if self.dataset is None or self.main_object is None:
            self.status.showMessage("Open a field file first", 4000)
            return
        from PyQt5.QtWidgets import QFileDialog, QInputDialog
        frames, ok = QInputDialog.getInt(
            self, "Export Animation Video", "Frames:", 30, 2, 500)
        if not ok:
            return
        default = (f"{Path(self.dataset.path).stem}.ogv"
                   if self.dataset else "animation.ogv")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Animation Video", default,
            "Ogg Theora video (*.ogv);;AVI video (*.avi)")
        if not path:
            return
        from ..render.export import export_animation_video
        n = export_animation_video(
            self.dataset, self.main_object, self.scene,
            self.vtk_widget.GetRenderWindow(), path,
            frames=frames, fps=15)
        if n:
            self.message_win.log(f"Exported {n}-frame video → {path}")
            self.status.showMessage(f"Exported {n}-frame video", 5000)
        else:
            self.message_win.log("Video export failed (ffmpeg missing?)",
                                 "ERROR")

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

    def on_vr_mode(self) -> None:
        """View → VR Mode: open a VR render window when a backend exists (7d)."""
        from ..render.vr import create_vr_window, release_vr_window, vr_backend
        backend = vr_backend()
        if backend == "none":
            self.message_win.log(
                "VR: no OpenVR/VR backend (install vtk + SteamVR)", "WARN")
            return
        handle = create_vr_window(background=(0.1, 0.1, 0.1))
        if handle is None:
            self.message_win.log(
                "VR: backend reported but window construction failed", "WARN")
            return
        self._vr_handle = handle
        self.message_win.log(
            f"VR: {backend} window created (HMD driver required to render)")
    def on_compare_view(self) -> None:
        """View → Compare: side-by-side snapshot of the two last datasets."""
        if len(self.datasets) < 2:
            self.message_win.log(
                "Compare: needs ≥2 loaded datasets (File → Open each)",
                "WARN")
            return
        names = "  vs  ".join(Path(d.path).name for d in self.datasets[-2:])
        a, b = self.datasets[-2:]
        self.message_win.log("Compare (P3.4):")
        self.message_win.log(f"  {Path(a.path).name}: {a.n_cells:,} cells, "
                            f"{a.n_vertices:,} verts, {len(a.variables)} vars")
        self.message_win.log(f"  {Path(b.path).name}: {b.n_cells:,} cells, "
                            f"{b.n_vertices:,} verts, {len(b.variables)} vars")
        common = sorted(set(a.variables) & set(b.variables))
        self.message_win.log(f"  common variables: {', '.join(common[:8]) or '-'}")
        summary = {}
        try:
            from ..model.compare import compare_summary
            summary = compare_summary(a, b)
            self.message_win.log("  |A−B| difference statistics:")
            for var, st in summary.items():
                self.message_win.log(
                    f"    {var}: min={st['min']:.4g} max={st['max']:.4g} "
                    f"mean={st['mean']:.4g} rms={st['rms']:.4g}")
        except Exception as exc:  # pragma: no cover - best effort
            self.message_win.log(f"  diff statistics unavailable: {exc}", "WARN")
        self.status.showMessage(f"Compare: {names}", 5000)
        if self._enable_3d:
            from .dialogs import CompareDialog
            dlg = CompareDialog(a, b, parent=self, enable_3d=True,
                                summary=summary)
            dlg.exec_()
        else:
            self.message_win.log("Compare: split view needs 3D mode", "WARN")

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

    def _snapshot_children(self) -> None:
        """Push the current Main children onto the undo stack (P2.8)."""
        import copy
        if self.main_object is None:
            return
        self._undo_stack.append(copy.deepcopy(self.main_object.children))
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _restore_children(self, snap) -> None:
        if self.main_object is None or self.dataset is None:
            return
        self.main_object.children = snap
        self.scene.build(self.dataset, main=self.main_object)
        if self._enable_3d:
            self.scene.fit()
            self._refresh_gl()
        self.object_tree.load_main(self.main_object)

    def on_undo(self) -> None:
        """Edit > Undo (Ctrl+Z): restore the previous object state (P2.8)."""
        if not self._undo_stack or self.main_object is None:
            self.status.showMessage("Nothing to undo", 2000)
            return
        import copy
        self._redo_stack.append(copy.deepcopy(self.main_object.children))
        self._restore_children(self._undo_stack.pop())
        self.message_win.log("Undo")

    def on_redo(self) -> None:
        """Edit > Redo (Ctrl+Y): re-apply the last undone state (P2.8)."""
        if not self._redo_stack or self.main_object is None:
            self.status.showMessage("Nothing to redo", 2000)
            return
        import copy
        self._undo_stack.append(copy.deepcopy(self.main_object.children))
        self._restore_children(self._redo_stack.pop())
        self.message_win.log("Redo")

    # ── object delete / duplicate (R0.2) ─────────────────────────────
    def _resolve_object(self, label):
        """Find a child object by label (None when absent)."""
        if self.main_object is None or label is None:
            return None
        for o in self.main_object.children:
            if getattr(o, "label", None) == label:
                return o
        return None

    def on_delete_object(self, label=None) -> None:
        """Edit > Delete / tree context menu: remove an object (R0.2)."""
        if self.main_object is None:
            return
        if label is None:
            label = self.object_tree.selected_object_label()
        obj = self._resolve_object(label)
        if obj is None:
            self.status.showMessage("Delete: no object selected", 2000)
            return
        if getattr(obj, "locked", False):
            self.status.showMessage(
                f"{label} is locked — unlock first", 3000)
            return
        self._snapshot_children()  # undo checkpoint (R0.3)
        self.main_object.children.remove(obj)
        # Drop the label from any folder membership
        for o in self.main_object.children:
            members = getattr(o, "member_labels", None)
            if members and label in members:
                o.member_labels = [m for m in members if m != label]
        self.scene.build(self.dataset, main=self.main_object) \
            if self.dataset is not None else None
        if self._enable_3d:
            self.scene.fit()
            self._refresh_gl()
        self.object_tree.load_main(self.main_object)
        panel = getattr(self.property_host, "current_panel", None)
        shown = getattr(panel, "obj", None)
        if shown is not None and getattr(shown, "label", None) == label:
            self.property_host.clear()
        self.message_win.log(f"Deleted {label}")
        self.status.showMessage(f"Deleted {label}", 3000)

    def on_duplicate_object(self, label=None) -> None:
        """Edit > Duplicate / tree context menu: copy an object (R0.2)."""
        import copy as _copy
        if self.main_object is None or self.dataset is None:
            return
        if label is None:
            label = self.object_tree.selected_object_label()
        obj = self._resolve_object(label)
        if obj is None:
            self.status.showMessage("Duplicate: no object selected", 2000)
            return
        self._snapshot_children()  # undo checkpoint (R0.3)
        clone = _copy.deepcopy(obj)
        clone.index = obj.index + 1
        used = {o.label for o in self.main_object.children}
        while clone.label in used:
            clone.index += 1
        self.main_object.children.append(clone)
        self.scene.build(self.dataset, main=self.main_object)
        if self._enable_3d:
            self._refresh_gl()
        self.object_tree.load_main(self.main_object)
        self.message_win.log(f"Duplicated {label} -> {clone.label}")

    def on_rename_object(self, label=None) -> None:
        """Tree context menu: rename an object's title (R1.2)."""
        if self.main_object is None:
            return
        if label is None:
            label = self.object_tree.selected_object_label()
        obj = self._resolve_object(label)
        if obj is None:
            self.status.showMessage("Rename: no object selected", 2000)
            return
        from PyQt5.QtWidgets import QInputDialog
        new, ok = QInputDialog.getText(
            self, "Rename Object", "Title:",
            text=getattr(obj, "title", "") or obj.kind.capitalize())
        if ok and new.strip():
            self._apply_rename(obj, new.strip())

    def _apply_rename(self, obj, new_title: str) -> str:
        """Set an object title and refresh the tree (R1.2); returns label."""
        if new_title == (getattr(obj, "title", "") or obj.kind.capitalize()):
            return obj.label
        self._snapshot_children()
        obj.title = new_title
        self.object_tree.load_main(self.main_object)
        self.message_win.log(f"Renamed -> {obj.label}")
        return obj.label

    def on_toggle_lock(self, label=None) -> None:
        """Tree context menu: toggle an object's lock flag (R1.2)."""
        if self.main_object is None:
            return
        if label is None:
            label = self.object_tree.selected_object_label()
        obj = self._resolve_object(label)
        if obj is None:
            self.status.showMessage("Lock: no object selected", 2000)
            return
        obj.locked = not bool(getattr(obj, "locked", False))
        self.object_tree.load_main(self.main_object)
        state = "locked" if obj.locked else "unlocked"
        self.message_win.log(f"{obj.label} {state}")
        self.status.showMessage(f"{obj.label} {state}", 3000)

    def on_delete_selected(self) -> None:
        """Edit > Delete Selected: remove rubber-band-selected objects (R1.2)."""
        labels = sorted(getattr(self, "_selected_labels", set()))
        if not labels:
            self.status.showMessage("Delete Selected: nothing selected", 2000)
            return
        for label in labels:
            self.on_delete_object(label)
        self._selected_labels = set()

    def on_hide_selected(self, hide: bool = True) -> None:
        """Edit > Hide/Show Selected: batch-toggle visibility (R1.2)."""
        labels = list(getattr(self, "_selected_labels", set()))
        if not labels:
            self.status.showMessage("No selection", 2000)
            return
        self._snapshot_children()
        for label in labels:
            obj = self._resolve_object(label)
            if obj is not None:
                obj.visible = not hide
        self.scene.build(self.dataset, main=self.main_object)
        if self._enable_3d:
            self.scene.fit()
            self._refresh_gl()
        self.object_tree.load_main(self.main_object)
        self.message_win.log(
            f"{'Hid' if hide else 'Showed'} {len(labels)} selected object(s)")

    def _open_camera_dialog(self) -> None:
        """Option > Camera / tree Camera: camera settings (5b)."""
        self.property_host.show_object(
            "camera", self._global_camera, field_file=None, siblings=[])
        panel = self.property_host.current_panel
        if panel is not None and hasattr(panel, "scene"):
            panel.scene = self.scene
        self.property_host.setVisible(True)

    def on_variable_registration(self) -> None:
        """Display > Variable Registration… (P1.1)."""
        if self.dataset is None:
            self.message_win.log(
                "Variable Registration: open a field file first", "WARN")
            self.status.showMessage("Open a field file first", 4000)
            return
        from .dialogs import VariableRegistrationDialog
        dlg = VariableRegistrationDialog(self.dataset, parent=self)
        dlg.exec_()

    def on_redraw(self) -> None:
        """Display → Redraw: force a full repaint + refresh scene."""
        self._refresh_gl()
        if self.dataset is not None and self.main_object is not None:
            self.scene.build(self.dataset, main=self.main_object)
            if self._enable_3d:
                self._refresh_gl()
        self.message_win.log("Redraw")

    def on_unit_settings(self) -> None:
        """Option → Unit settings: display length/angle units (R0.4)."""
        bounds = None
        if self.dataset is not None:
            try:
                from ..api import get_bounding_box
                bounds = get_bounding_box(self.dataset)
            except Exception:  # noqa: BLE001
                bounds = None
        from .dialogs import UnitDialog
        dlg = UnitDialog(self, bounds=bounds,
                         length_unit=self.options.length_unit,
                         angle_unit=self.options.angle_unit)
        if dlg.exec_():
            self.options.length_unit = dlg.length_unit
            self.options.angle_unit = dlg.angle_unit
            self.message_win.log(
                f"Unit settings: length [{dlg.length_unit}] "
                f"angle [{dlg.angle_unit}]")
            self.status.showMessage(
                f"Units: {dlg.length_unit} / {dlg.angle_unit}", 3000)

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
        elif name == "Light (1)":
            self._global_light.enabled = on
            self.scene.apply_light(self._global_light)
            self._refresh_gl()
        elif name in ("Option", "Camera", "Unit"):
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
            self.on_unit_settings()
        elif name == "Option":
            self.on_environment_settings()
        elif name == "Camera":
            self._open_camera_dialog()
        elif name.startswith("Draw Window"):
            self._nyi("Draw Window settings")
        elif name == "Light (1)":
            self.property_host.show_object(
                "light", self._global_light, field_file=None, siblings=[])
            self.property_host.setVisible(True)

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
        # Object-name billboard (C3)
        self.scene.show_object_name(obj.label, _object_position(obj))

    # ── drag handles (G1) ─────────────────────────────────────────────────

    def _setup_drag_handlers(self) -> None:
        """Wire the Draw Window interactor for plane drag (G1)."""
        self._drag_obj = None
        if not self._enable_3d or self.vtk_widget is None:
            return
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        if iren is None:
            return
        import vtk
        cmd = vtk.vtkCallbackCommand()
        cmd.SetCallback(self._on_vtk_drag_event)
        for ev in ("LeftButtonPressEvent", "MouseMoveEvent",
                   "LeftButtonReleaseEvent"):
            iren.AddObserver(ev, cmd)

    def _on_vtk_drag_event(self, caller, event, *args) -> None:
        """Interactor callback: dispatch by event name."""
        try:
            x, y = caller.GetEventPosition()
        except Exception:
            return
        if event == "LeftButtonPressEvent":
            self._drag_start(x, y)
        elif event == "MouseMoveEvent":
            self._drag_move(x, y)
        elif event == "LeftButtonReleaseEvent":
            self._drag_end()

    def _drag_start(self, x: int, y: int) -> None:
        """Begin dragging a plane: pick, then attach to it (G1)."""
        self._drag_obj = None
        if self.dataset is None:
            return
        pt, _owner = self.scene.pick_actor(x, y)
        if pt is None:
            return
        draggable = ("plane", "cylinder", "circle", "point")
        panel_obj = self.property_host.current_object
        if getattr(panel_obj, "kind", "") in draggable:
            self._drag_obj = panel_obj
        else:
            for o in (self.main_object.children
                      if self.main_object is not None else []):
                if getattr(o, "kind", "") in draggable:
                    self._drag_obj = o
                    break
        if self._drag_obj is not None:
            self.status.showMessage(
                f"Dragging {self._drag_obj.label} — release to finish", 0)

    def _drag_move(self, x: int, y: int) -> None:
        """While dragging: move the object to the picked point (G1/E3)."""
        if self._drag_obj is None or self.dataset is None:
            return
        moved = self._move_object_to_pick(self._drag_obj, x, y)
        if moved and self._enable_3d:
            self._refresh_gl()

    def _move_object_to_pick(self, obj, x: int, y: int) -> bool:
        """Move a draggable object to the picked world point (E3)."""
        kind = getattr(obj, "kind", "")
        if kind == "plane":
            return self.scene.move_plane_to_pick(x, y, plane_obj=obj)
        pt, _owner = self.scene.pick_actor(x, y)
        if pt is None:
            return False
        if kind in ("cylinder", "circle"):
            obj.center = tuple(pt)
            self.scene.apply_to_object(self.dataset, obj)
            return True
        if kind == "point":
            obj.position = tuple(pt)
            self.scene.apply_to_object(self.dataset, obj)
            return True
        return False

    def _drag_end(self) -> None:
        """Finish dragging; report the new position."""
        if self._drag_obj is not None:
            self.message_win.log(f"Plane moved: {self._drag_obj.label}")
            self.status.showMessage(
                f"Plane {self._drag_obj.label} moved", 3000)
        self._drag_obj = None

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

    def _on_before_apply(self, obj) -> None:
        """Pre-apply undo checkpoint: object state is still pristine (R0.3)."""
        if (self.main_object is not None
                and obj in getattr(self.main_object, "children", [])):
            self._snapshot_children()

    def _on_property_applied(self, obj) -> None:
        """After Draw / apply_now → rebuild the affected object.

        Uses the incremental ``Scene.apply_to_object`` path when the scene is
        already built so sibling actors / camera stay untouched (I-gap).
        """
        if getattr(obj, "kind", "") == "light":
            self.scene.apply_light(obj)
            if self._enable_3d:
                self._refresh_gl()
            self.message_win.log("Draw: applied Light")
            self.status.showMessage("Draw: Light", 3000)
            return
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
        if kind == "light":
            # Global object: open the Light settings pane directly
            self.property_host.show_object(
                "light", self._global_light, field_file=None, siblings=[])
            self.property_host.setVisible(True)
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
            "particle": objmod.ParticleObject,
            "cylinder": objmod.CylinderObject,
            "circle": objmod.CircleObject,
            "text": objmod.TextObject,
            "graph": objmod.GraphObject,
            "pathline": objmod.PathlineObject,
            "bitmap": objmod.BitmapObject,
            "information": objmod.InformationObject,
            "mirror": objmod.MirrorCopyObject,
            "timeseries": objmod.TimeSeriesObject,
            "maxmin": objmod.MaxMinObject,
            "grouping": objmod.GroupingObject,
            "curve": objmod.CurveObject,
            "periodical": objmod.PeriodicalCopyObject,
            "measure": objmod.MeasureObject,
            "bar": objmod.BarObject,
            "regionbc": objmod.RegionBCObject,
            "gradation": objmod.GradationObject,
            "region": objmod.RegionObject,
            "turbo": objmod.TurboObject,
            "ufo": objmod.UFOObject,
            "folder": objmod.FolderObject,
        }
        maker = makers.get(kind)
        if maker is None:
            self._nyi(f"Create {kind}")
            return
        self._snapshot_children()  # undo checkpoint before mutating (P0.3)
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
                from ..model.fileset import load_member
                try:
                    loaded = load_member(
                        self.fileset, member.cycle,
                        cache=self._member_cache)
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
                    self.timeline.format_time(loaded.time))
                msg = (f"{loaded.kind.upper()}: {loaded.n_cells:,} cells, "
                       f"{loaded.n_vertices:,} vertices, "
                       f"{len(loaded.variables)} variables"
                       f" | Cycle={loaded.cycle} Time={loaded.time}")
                self.status.showMessage(msg)
                self.message_win.log(msg)
        # Automove planes animate with the timeline slider (P3.10);
        # particle objects advance their multi-frame time series (P0.5)
        has_auto = any(
            getattr(o, "automove_enabled", False)
            for o in getattr(self.main_object, "children", []))
        has_particles = any(
            getattr(o, "kind", "") == "particle"
            for o in getattr(self.main_object, "children", []))
        if has_auto or has_particles:
            self.scene.animate(step)
            if self._enable_3d:
                self._refresh_gl()

    def _on_timeline_interp(self, frac_cycle: float) -> None:
        """Time mode: fractional cycle id -> interpolated FieldFile (R0.1)."""
        if not self.fileset or not self.main_object:
            return
        from ..model.fileset import interpolate_at
        # Convert a fractional cycle *number* (Step units) to a 1-based
        # member position id: the fraction is normalized by the cycle gap.
        cyc_lo = int(frac_cycle)
        frac = float(frac_cycle) - cyc_lo
        members = self.fileset.members
        pos = next((i for i, m in enumerate(members) if m.cycle == cyc_lo),
                   None)
        if pos is None:
            self.message_win.log(
                f"Interpolate: no member at cycle {cyc_lo}", "WARN")
            return
        if frac > 0.0 and pos + 1 < len(members):
            gap = members[pos + 1].cycle - cyc_lo
            if gap > 0:
                frac = min(1.0, frac / gap)
            pos_id = (pos + 1) + frac
        else:
            pos_id = float(pos + 1)
        try:
            loaded = interpolate_at(self.fileset, pos_id,
                                    cache=self._member_cache)
        except Exception as exc:  # noqa: BLE001
            self.message_win.log(f"Interpolate failed: {exc}", "ERROR")
            return
        if loaded is None:
            return
        self.dataset = loaded
        self.scene.build(loaded, main=self.main_object)
        if self._enable_3d:
            self._refresh_gl()
        if loaded.time is not None:
            self.timeline.edit_time.setText(
                self.timeline.format_time(loaded.time))
        self._cycle_label.setText(f"Cycle {frac_cycle:g}")
        msg = (f"Interpolated cycle {frac_cycle:g} "
               f"(id {pos_id:.3f}) Time={loaded.time}")
        self.status.showMessage(msg)
        self.message_win.log(msg)

    def _on_timeline_time_request(self, t: float) -> None:
        """Time mode: physical time -> bracketing members -> interpolate."""
        if not self.fileset or not self.main_object:
            return
        members = self.fileset.members
        for m in members:
            if m.time is None:
                m.refresh_meta()
        times = [m.time for m in members]
        if not times or any(v is None for v in times):
            self.message_win.log(
                "Time interpolation: members carry no Time meta", "WARN")
            return
        if t <= times[0]:
            self._on_timeline_interp(float(members[0].cycle))
            return
        if t >= times[-1]:
            self._on_timeline_interp(float(members[-1].cycle))
            return
        from ..model.fileset import interpolate_at
        for i in range(len(times) - 1):
            if times[i] <= t <= times[i + 1]:
                span = times[i + 1] - times[i]
                frac = 0.0 if span <= 0 else (t - times[i]) / span
                pos_id = (i + 1) + frac
                try:
                    loaded = interpolate_at(
                        self.fileset, pos_id, cache=self._member_cache)
                except Exception as exc:  # noqa: BLE001
                    self.message_win.log(
                        f"Time interpolation failed: {exc}", "ERROR")
                    return
                if loaded is None:
                    return
                self.dataset = loaded
                self.scene.build(loaded, main=self.main_object)
                if self._enable_3d:
                    self._refresh_gl()
                self.timeline.edit_time.setText(
                    self.timeline.format_time(t))
                self._cycle_label.setText(
                    f"Cycle {members[i].cycle}+{frac:.2f}")
                self.message_win.log(
                    f"Interpolated time {t:g} "
                    f"(members {members[i].cycle}/{members[i + 1].cycle})")
                return

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
            self._set_select_style(iren)
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

    def _set_select_style(self, iren) -> None:
        """R1.2: rubber-band pick style — drag to select objects."""
        if vtk is None:
            self._set_trackball_style(iren)
            return
        try:
            from vtkmodules.vtkInteractionStyle import (
                vtkInteractorStyleRubberBandPick)
        except Exception:
            vtkInteractorStyleRubberBandPick = vtk.vtkInteractorStyleRubberBandPick
        self._area_picker = vtk.vtkAreaPicker()
        iren.SetPicker(self._area_picker)
        style = vtkInteractorStyleRubberBandPick()
        iren.SetInteractorStyle(style)
        style.AddObserver("SelectionChangedEvent", self._on_area_selection)
        self._select_style = style
        self.message_win.log("Mouse: Select — drag to select objects")

    def _on_area_selection(self, caller, event) -> None:
        """R1.2: rubber band released — collect the picked objects."""
        if getattr(self, "_area_picker", None) is None:
            return
        props = self._area_picker.GetProp3Ds()
        selected = set()
        if props is not None:
            n = props.GetNumberOfItems()
            props.InitTraversal()
            for _ in range(n):
                prop = props.GetNextProp3D()
                if prop is None:
                    break
                owner = self.scene._actor_object.get(prop)
                if owner is not None and owner[1] is not None:
                    selected.add(getattr(owner[1], "label", id(owner[1])))
        self._selected_labels = selected
        n = len(selected)
        self.status.showMessage(f"Selected {n} object(s)", 4000)
        self.message_win.log(
            f"Selected {n} object(s): " + (", ".join(sorted(selected)) or "(none)"))

    # ── showEvent delayed interactor init ─────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            if getattr(self, "options", None) is not None:
                self.options.save_window(self)
        finally:
            try:
                from ..com import detach_gui
                detach_gui(self)
            except Exception:
                pass
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
        """Left-click pick: probe scalar/vector on the clicked object (R1.1)."""
        if not self._enable_3d or self.renderer is None:
            return
        if self.dataset is None or self.main_object is None:
            return
        x, y = obj.GetEventPosition()
        point, owner = self.scene.pick_actor(x, y)
        if point is None:
            return
        if self._try_fill_measure_pick(point):
            return
        if owner is None:
            return
        _kind, picked = owner
        scalar_var, vector_var, scalar_on, vector_on = self._pick_vars(picked)
        if not scalar_var and not vector_var:
            return
        from ..render.point import probe_at
        res = probe_at(self.dataset, point, scalar_var, vector_var,
                       scalar_on=scalar_on, vector_on=vector_on)
        lines = [f"Pick at ({point[0]:.4g}, {point[1]:.4g}, {point[2]:.4g})"]
        summary = []
        if "scalar" in res:
            name, val = res["scalar"]
            lines.append(f"  {name} = {val:.6g}")
            summary.append(f"{name}={val:.6g}")
        if "vector" in res:
            name, (vx, vy, vz) = res["vector"]
            lines.append(f"  {name} = ({vx:.6g}, {vy:.6g}, {vz:.6g})")
            summary.append(f"{name}=({vx:.3g},{vy:.3g},{vz:.3g})")
        self.message_win.log("\n".join(lines))
        if summary:  # R0.8: picked values in the status bar
            self._pick_label.setText("Pick " + " | ".join(summary))

    def _pick_vars(self, obj):
        """R1.1: map a picked object's displayed fields to probe variables."""
        kind = getattr(obj, "kind", "")
        scalar_var = vector_var = ""
        scalar_on = vector_on = False
        if kind == "plane":
            scalar_var = getattr(obj, "pick_scalar_var", "") or ""
            vector_var = getattr(obj, "pick_vector_var", "") or ""
            scalar_on = getattr(obj, "pick_scalar", True)
            vector_on = getattr(obj, "pick_vector", False)
        elif kind == "surface":
            if getattr(obj, "show_contour", False):
                scalar_var = getattr(obj, "contour_var", "") or ""
                scalar_on = bool(scalar_var)
            if getattr(obj, "show_vector", False):
                vector_var = getattr(obj, "vector_var", "") or ""
                vector_on = bool(vector_var)
        elif kind == "isosurface":
            scalar_var = getattr(obj, "contour_var", "") or ""
            scalar_on = bool(scalar_var)
            if getattr(obj, "show_vector", False):
                vector_var = getattr(obj, "vector_var", "") or ""
                vector_on = bool(vector_var)
        elif kind == "volume":
            if getattr(obj, "show_scalar", True):
                scalar_var = getattr(obj, "scalar_var", "") or ""
                scalar_on = bool(scalar_var)
            if getattr(obj, "show_vector", False):
                vector_var = getattr(obj, "vector_var", "") or ""
                vector_on = bool(vector_var)
        elif kind == "streamline":
            scalar_var = getattr(obj, "color_var", "") or ""
            scalar_on = bool(scalar_var)
            vector_var = getattr(obj, "vector_var", "") or ""
            vector_on = bool(vector_var)
        return scalar_var, vector_var, scalar_on, vector_on

    def _try_fill_measure_pick(self, point) -> bool:
        """R1.3: fill an armed MeasureDialog point pick; True if consumed."""
        panel = getattr(self.property_host, "current_panel", None)
        if panel is None:
            return False
        idx = getattr(panel, "_pick_index", None)
        if idx is None or not hasattr(panel, "set_pick_point"):
            return False
        panel.set_pick_point(idx, point)
        panel._pick_index = None
        self.status.showMessage(f"Measure point {idx + 1} set", 2000)
        return True


def run_gui(filepath: Optional[str] = None) -> int:
    if QApplication is None:
        print("PyQt5 not installed; cannot start GUI", file=sys.stderr)
        return 2
    app = QApplication.instance() or QApplication(sys.argv)
    win = FlowViewer(filepath=filepath, enable_3d=True)
    win.show()
    return app.exec_()
