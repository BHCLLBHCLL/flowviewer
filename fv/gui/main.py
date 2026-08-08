"""FlowViewer main window (P1 layout) and Qt app bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

try:
    from PyQt5 import QtCore, QtWidgets
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QKeySequence
    from PyQt5.QtWidgets import (
        QAction, QApplication, QFileDialog, QLabel, QMainWindow, QSplitter,
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
    """scPost-style main window: Control | Draw(+Message) + Timeline + Status.

    ``enable_3d=False`` swaps the VTK widget for a placeholder so the window
    can be built headlessly (offscreen tests).
    """

    def __init__(self, filepath: Optional[str] = None, enable_3d: bool = True):
        if not _HAS_GUI_DEPS:
            raise RuntimeError("PyQt5/vtk not installed")
        super().__init__()
        self.setWindowTitle("flowviewer")
        self.resize(1500, 900)
        self._enable_3d = enable_3d
        self.datasets: list = []
        self._iren_ready = False
        self.vtk_widget = None
        self.renderer = None

        from ..render.scene import Scene
        self.scene = Scene(enable_3d=enable_3d)
        self._build_central()
        self._build_menus()
        self._build_statusbar()
        if filepath:
            self.open_file(filepath)

    # ── layout ────────────────────────────────────────────────────────────

    def _build_central(self) -> None:
        from .panes import MessageWindow, ObjectTree, PaneFrame

        self.object_tree = ObjectTree(self)
        left = PaneFrame("Control Window", self.object_tree)

        if self._enable_3d:
            self.vtk_widget = QVTKRenderWindowInteractor(self)
            self.renderer = vtk.vtkRenderer()
            self.renderer.SetBackground(0.15, 0.17, 0.2)
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
        msg_pane = PaneFrame("Message", self.message_win)

        right = QSplitter(Qt.Vertical, self)
        right.addWidget(self.draw_pane)
        right.addWidget(msg_pane)
        right.setStretchFactor(0, 5)
        right.setStretchFactor(1, 1)
        right.setSizes([640, 150])

        main = QSplitter(Qt.Horizontal, self)
        main.addWidget(left)
        main.addWidget(right)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        main.setSizes([320, 1180])
        self.setCentralWidget(main)

    def _build_statusbar(self) -> None:
        self._coord_label = QLabel("( —, —, — )")
        self._mode_label = QLabel("Navigation")
        sb = self.statusBar()
        sb.addPermanentWidget(self._coord_label, 1)
        sb.addPermanentWidget(self._mode_label)
        self.status = sb
        self.status.showMessage("Ready")

    def _build_menus(self) -> None:
        mb = self.menuBar()
        file_m = mb.addMenu("File")
        act_open = QAction("Open…", self)
        act_open.setShortcut(QKeySequence.Open)
        act_open.triggered.connect(self.on_open_dialog)
        file_m.addAction(act_open)
        file_m.addSeparator()
        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self.close)
        file_m.addAction(act_exit)

        view_m = mb.addMenu("View")
        act_fit = QAction("Fit", self)
        act_fit.triggered.connect(self.on_fit)
        view_m.addAction(act_fit)
        for label, key in (("YZ (X)", "x"), ("XZ (Y)", "y"), ("XY (Z)", "z")):
            act = QAction(label, self)
            act.triggered.connect(
                lambda _=False, plane=key: self.on_plane_view(plane))
            view_m.addAction(act)

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
        try:
            ff = load_file(filepath)
        except Exception as exc:  # noqa: BLE001
            self.status.showMessage(f"Error: {exc}")
            self.message_win.write(f"Error loading {filepath}: {exc}")
            return
        self.dataset = ff
        self.scene.build(ff)
        if self._enable_3d:
            self.scene.fit()
            self._refresh_gl()
        self._populate_tree(ff)
        self.setWindowTitle(f"flowviewer — {Path(filepath).name}")
        self.status.showMessage(
            f"{ff.kind.upper()}: {ff.n_cells:,} cells, {ff.n_vertices:,} "
            f"vertices, {len(ff.variables)} variables")

    def on_fit(self) -> None:
        self.scene.fit()
        self._refresh_gl()

    def on_plane_view(self, plane: str) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        cam = self.renderer.GetActiveCamera()
        p = plane.lower()
        if p == "x":
            cam.SetPosition(1, 0, 0); cam.SetViewUp(0, 0, 1)
        elif p == "y":
            cam.SetPosition(0, 1, 0); cam.SetViewUp(0, 0, 1)
        else:
            cam.SetPosition(0, 0, 1); cam.SetViewUp(0, 1, 0)
        cam.SetFocalPoint(0, 0, 0)
        self.renderer.ResetCamera()
        self._refresh_gl()

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

    # ── showEvent delayed interactor init (avoids blank first draw) ──────

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._enable_3d and not self._iren_ready and self.vtk_widget is not None:
            self._ensure_interactor()

    def _ensure_interactor(self) -> None:
        if not self._enable_3d or self.vtk_widget is None or self._iren_ready:
            return
        try:
            from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
        except Exception:  # pragma: no cover
            vtkInteractorStyleTrackballCamera = vtk.vtkInteractorStyleTrackballCamera
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        self._trackball_style = vtkInteractorStyleTrackballCamera()
        iren.SetInteractorStyle(self._trackball_style)
        iren.AddObserver("MouseMoveEvent", self._on_vtk_mouse, 1.0)
        iren.Initialize()
        self._iren_ready = True
        self._refresh_gl()

    def _on_vtk_mouse(self, obj, event) -> None:
        if not self._enable_3d or self.renderer is None:
            return
        iren = obj
        x, y = iren.GetEventPosition()
        picker = vtk.vtkWorldPointPicker()
        if picker.Pick(x, y, 0, self.renderer):
            p = picker.GetPickPosition()
            self._coord_label.setText(f"( {p[0]:.4g}, {p[1]:.4g}, {p[2]:.4g} )")


def run_gui(filepath: Optional[str] = None) -> int:
    if QApplication is None:
        print("PyQt5 not installed; cannot start GUI", file=sys.stderr)
        return 2
    app = QApplication.instance() or QApplication(sys.argv)
    win = FlowViewer(filepath=filepath, enable_3d=True)
    win.show()
    return app.exec_()