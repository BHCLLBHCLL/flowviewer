"""Background loading worker (DEV_PLAN §3.1) — not yet wired to the UI.

``LoadWorker`` runs :func:`fv.model.dataset.load_file` on a ``QThread`` so a
large file need not block the GUI; ``progress`` and ``finished`` signals
carry the result back to the main thread.  Falls back to synchronous loading
when PyQt5 is unavailable so callers work headless.
"""

from __future__ import annotations

from typing import Optional

try:
    from PyQt5.QtCore import QObject, QThread, pyqtSignal
    _HAS_QT = True
except Exception:  # pragma: no cover - headless
    _HAS_QT = False
    QObject = object
    pyqtSignal = None


if _HAS_QT:

    class LoadWorker(QObject):
        """Runs :func:`fv.model.dataset.load_file` on a worker thread."""

        progress = pyqtSignal(int, str)       # step, message
        finished = pyqtSignal(object)        # FieldFile or None on error
        failed = pyqtSignal(str)             # error message

        def __init__(self, filepath: str, *, threads: int = 1, parent=None):
            super().__init__(parent)
            self._filepath = filepath
            self._threads = threads

        @property
        def filepath(self) -> str:
            return self._filepath

        def _load(self):
            try:
                self.progress.emit(1, f"Loading {self._filepath} …")
                from ..model.dataset import load_file
                ff = load_file(self._filepath)
                self.progress.emit(100, "Done")
                self.finished.emit(ff)
                return ff
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(str(exc))
                return None

        def run(self) -> Optional[object]:
            return self._load()

else:

    class LoadWorker:  # pragma: no cover - headless fallback
        """Synchronous stand-in: exposes the progress/finished protocol."""

        def __init__(self, filepath: str, *, threads: int = 1, parent=None):
            self._filepath = filepath
            self._threads = threads
            self.progress = None
            self.finished = None
            self.failed = None

        @property
        def filepath(self) -> str:
            return self._filepath

        def run(self) -> Optional[object]:
            from ..model.dataset import load_file
            try:
                return load_file(self._filepath)
            except Exception:  # noqa: BLE001
                return None


def launch_load(filepath: str, *, threads: int = 1,
                on_finished=None, on_failed=None):
    """Start :class:`LoadWorker` on a thread and connect callbacks.

    Returns the worker; ``on_finished(ff)`` runs with the parsed FieldFile,
    ``on_failed(msg)`` with the error text.
    """
    worker = LoadWorker(filepath, threads=threads)
    if on_finished is not None:
        worker.finished.connect(on_finished)
    if on_failed is not None:
        worker.failed.connect(on_failed)
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    return worker