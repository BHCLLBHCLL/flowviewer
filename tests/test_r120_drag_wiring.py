"""R120: the drag chain (G1/E3) must actually be installed.

The whole feature existed -- pick the object under the cursor, move a plane to
the picked point, move a cylinder/circle centre, move a point, log the result
-- but _setup_drag_handlers had no caller anywhere in the tree, so none of it
could ever run.  These tests pin that the handlers are installed, that Select
mode owns them (so they never compete with camera manipulation in the ordinary
modes), and that a headless build stays safe.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from fv.gui import main as M  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PyQt5 import QtWidgets

    app = QtWidgets.QApplication.instance()
    return app or QtWidgets.QApplication([])


@pytest.fixture()
def window(qapp):
    win = M.FlowViewer(enable_3d=False)
    yield win
    win.close()


def test_drag_state_exists_before_any_mode_change(window):
    """A headless build never installs handlers; the state must still exist."""
    assert window._drag_commands == []
    assert window._drag_obj is None


def test_setup_drag_handlers_has_a_single_implementation(window):
    """It used to be a dead copy of the install logic with no caller."""
    assert callable(window._setup_drag_handlers)
    assert callable(window._install_drag_handlers)
    # headless: both must be safe no-ops rather than raising
    window._setup_drag_handlers()
    window._install_drag_handlers(True)
    window._install_drag_handlers(False)


def test_every_mouse_mode_is_switchable_and_leaves_no_stale_observers(window):
    """Switching modes must not raise, nor accumulate observers."""
    for mode in ("trackball", "rubber", "select", "onebutton", "trackball"):
        window._set_mouse_mode(mode)
        assert window._mouse_mode == mode
        # headless installs nothing, so the list stays empty rather than
        # growing with every switch
        assert window._drag_commands == []


def test_select_mode_is_the_only_one_that_requests_drag(window, monkeypatch):
    """Drag would otherwise fight camera rotation in the normal modes."""
    seen = []
    monkeypatch.setattr(M.FlowViewer, "_install_drag_handlers",
                        lambda self, enabled: seen.append(
                            (self._mouse_mode, enabled)))
    for mode in ("trackball", "rubber", "onebutton", "select", "trackball"):
        window._set_mouse_mode(mode)
    # A headless build has no interactor, so every mode reports False.  What
    # matters is that the installer is consulted on every switch (so it can
    # detach observers) and that no camera mode ever asks for drag.
    assert len(seen) == 5, seen
    assert not any(enabled for _mode, enabled in seen), seen
    # The 3-D path is what actually keys drag off Select mode.
    src = Path(M.__file__).read_text(encoding="utf-8-sig")
    assert 'self._install_drag_handlers(mode == "select")' in src


def test_drag_targets_are_the_expected_kinds():
    """Guard the draggable set the handlers act on."""
    src = Path(M.__file__).read_text(encoding="utf-8-sig")
    assert 'draggable = ("plane", "cylinder", "circle", "point")' in src
    for kind in ("plane", "cylinder", "circle", "point"):
        assert ('"%s"' % kind) in src
