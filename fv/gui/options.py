"""Application options: QSettings-backed persistence (DEV_PLAN §3.1).

Provides typed get/set helpers around ``QSettings`` so the GUI persists
window geometry, last-opened directory and environment display flags.
Works headless too (in-memory fallback) so tests can exercise it without QT.
"""

from __future__ import annotations

from typing import Optional

try:
    from PyQt5.QtCore import QSettings
    _HAS_QT = True
except Exception:  # pragma: no cover - headless
    _HAS_QT = False

_ORG = "flowviewer"
_APP = "flowviewer"


class Options:
    """Small settings facade with sane defaults + QSettings persistence."""

    def __init__(self, *, organization: str = _ORG, application: str = _APP,
                 qt_settings=None):
        if _HAS_QT and qt_settings is None:
            self._qs = QSettings(organization, application)
        else:
            self._qs = qt_settings
        self._mem: dict = {
            "last_dir": "",
            "station_mode": "Static",
            "env_gradient_bg": True,
            "env_show_status": True,
            "env_show_units": True,
        }

    # ── typed access ────────────────────────────────────────────────────────

    def _coerce(self, value, default):
        """Coerce a QSettings-stored value back to the caller's type.

        QSettings serialises booleans to ``"true"/"false"`` strings on some
        platforms; ``get`` restores the Python type from ``default``.
        """
        if isinstance(default, bool):
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "on")
            return bool(value)
        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        if isinstance(default, float):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default
        return value

    def get(self, key: str, default=None):
        if key in self._mem:
            return self._coerce(self._mem[key], default)
        if self._qs is not None:
            v = self._qs.value(key)
            if v is not None:
                return self._coerce(v, default)
        return default

    def set(self, key: str, value) -> None:
        self._mem[key] = value
        if self._qs is not None:
            self._qs.setValue(key, value)

    # ── convenience ─────────────────────────────────────────────────────────

    @property
    def length_unit(self) -> str:
        return self.get("length_unit", "m")

    @length_unit.setter
    def length_unit(self, value: str) -> None:
        self.set("length_unit", str(value))

    @property
    def angle_unit(self) -> str:
        return self.get("angle_unit", "deg")

    @angle_unit.setter
    def angle_unit(self, value: str) -> None:
        self.set("angle_unit", str(value))

    @property
    def last_dir(self) -> Optional[str]:
        return self.get("last_dir")

    @last_dir.setter
    def last_dir(self, value: Optional[str]) -> None:
        if value:
            self.set("last_dir", str(value))

    def load_window(self, window) -> None:
        """Restore main-window geometry/state, if saved previously."""
        if _HAS_QT and self._qs is not None:
            geo = self._qs.value("window_geometry")
            if geo is not None:
                window.restoreGeometry(geo)
            state = self._qs.value("window_state")
            if state is not None:
                window.restoreState(state)

    def save_window(self, window) -> None:
        if _HAS_QT and self._qs is not None:
            self._qs.setValue("window_geometry", window.saveGeometry())
            self._qs.setValue("window_state", window.saveState())
