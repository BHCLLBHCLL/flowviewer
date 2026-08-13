"""Background loading worker (DEV_PLAN §3.1) — wired to File→Open (P0.6).

'LoadWorker' parses a field file on a QThreadPool thread so a large
file need not block the GUI; 'finished'/'failed' signals carry the
result back to the main thread (queued).  Falls back to synchronous
loading when PyQt5 is unavailable so callers work headless.
"""

from __future__ import annotations

from typing import Optional

try:
    from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
    _HAS_QT = True
except Exception:  # pragma: no cover - headless
    _HAS_QT = False
    QObject = object
    QRunnable = object
    QThreadPool = None
    pyqtSignal = None


if _HAS_QT:

    class _LoadSignals(QObject):
        """Cross-thread result carriers (queued to the main thread)."""

        finished = pyqtSignal(object)   # FieldFile
        failed = pyqtSignal(str)        # error message

    class LoadWorker(QRunnable):
        """Runs 'fv.model.dataset.load_file' on a pool thread."""

        def __init__(self, filepath: str, *, threads: int = 1,
                     parent=None):
            super().__init__()
            self._filepath = filepath
            self._threads = threads
            self.signals = _LoadSignals()

        @property
        def filepath(self) -> str:
            return self._filepath

        def run(self):
            """Parse the file (pool thread) and emit the result."""
            try:
                from ..model.dataset import load_file
                ff = load_file(self._filepath)
                self.signals.finished.emit(ff)
            except Exception as exc:  # noqa: BLE001
                self.signals.failed.emit(str(exc))

else:

    class LoadWorker:  # pragma: no cover - headless fallback
        """Synchronous stand-in: exposes the progress/finished protocol."""

        def __init__(self, filepath: str, *, threads: int = 1,
                     parent=None):
            self._filepath = filepath
            self._threads = threads
            self.progress = None
            self.finished = None
            self.failed = None

        @property
        def filepath(self) -> str:
            return self._filepath

        def run(self):
            from ..model.dataset import load_file
            try:
                return load_file(self._filepath)
            except Exception:  # noqa: BLE001
                return None


def launch_load(filepath: str, *, threads: int = 1,
                on_finished=None, on_failed=None):
    """Parse *filepath* off the GUI thread (P0.6).

    Uses the global QThreadPool so thread life-cycle is managed by Qt;
    'on_finished(ff)' / 'on_failed(msg)' run queued on the main thread.
    Without Qt the load runs synchronously and callbacks fire inline.
    """
    worker = LoadWorker(filepath, threads=threads)
    if not _HAS_QT:
        # Headless: parse synchronously and fire callbacks inline.
        try:
            from ..model.dataset import load_file
            ff = load_file(filepath)
        except Exception as exc:  # noqa: BLE001
            if on_failed is not None:
                on_failed(str(exc))
            return worker
        if on_finished is not None:
            on_finished(ff)
        return worker
    if on_finished is not None:
        worker.signals.finished.connect(on_finished)
    if on_failed is not None:
        worker.signals.failed.connect(on_failed)
    QThreadPool.globalInstance().start(worker)
    return worker