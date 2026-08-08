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
    assert w.object_tree.topLevelItemCount() >= 3
    assert w.scene.actor_names() == ["grid", "bc"]
    assert w.status.currentMessage().startswith("FPH")


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_window_fld_layout(qapp):
    w = _make(qapp, FLD)
    assert w.dataset.kind == "fld"
    assert w.dataset.n_cells == 18_240
    assert w.scene.actor_names() == ["grid", "bc"]


def test_window_without_file(qapp):
    w = _make(qapp, None)
    assert w.object_tree.topLevelItemCount() == 0
    assert w.scene.actor_names() == []


def test_headless_imports():
    import fv.gui.main  # noqa: F401
    import fv.render.scene  # noqa: F401
    assert fv.gui.main._HAS_GUI_DEPS in (True, False)


def test_scene_fph_actor_build(qapp):
    from fv.gui.main import FlowViewer
    w = FlowViewer(filepath=FPH, enable_3d=False)
    assert w.scene.layer_count("grid") == 1
    assert w.scene.actor_names() == ["grid", "bc"]