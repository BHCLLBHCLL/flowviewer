"""R25-S3: embedded Python console (headless exec session + Qt widget).

``ConsoleSession`` is a Qt-free sandbox that executes code in its own
namespace while capturing stdout/stderr and exceptions - unit-testable
without a GUI. The Qt ``ConsolePane`` widget in :mod:`fv.gui.console` wraps
one session and gives the user a prompt, per-line execution and history.

Console sessions expose a curated subset of :mod:`fv.api` (file load,
spreadsheet/variable registration, derived-function registration) plus the
current FieldFile, so scPOST-style scripting can run inside the GUI.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from typing import Optional


class ConsoleSession:
    """Execute Python snippets in an isolated namespace (headless).

    ``context`` seeds the namespace (e.g. ``{"ff": ff, "open_file": ...}``).
    :meth:`run` returns ``(ok, output)`` where ``ok`` is True on success and
    ``output`` holds captured stdout/stderr plus any exception message.
    """

    def __init__(self, context: Optional[dict] = None):
        self.namespace: dict = {
            "__name__": "__console__",
            "__builtins__": __builtins__,
        }
        if context:
            self.namespace.update(context)

    def bind(self, **kwargs) -> None:
        """Inject extra names into the session namespace."""
        self.namespace.update(kwargs)

    @property
    def context(self) -> dict:
        """A shallow copy of the current namespace (for REPL tabcompletion)."""
        return dict(self.namespace)

    def run(self, code: str) -> tuple:
        """Execute *code*; return ``(ok, output)`` with output captured."""
        buf = io.StringIO()
        try:
            node = compile(code, "<console>", "exec")
            with redirect_stdout(buf), redirect_stderr(buf):
                exec(node, self.namespace)
            return True, buf.getvalue()
        except Exception as exc:  # interactive console: surface any error
            return False, ("%s%s: %s"
                           % (buf.getvalue(), type(exc).__name__, exc))


def default_context(ff=None):
    """Curated fv.api subset + the live FieldFile for a console session."""
    from . import api
    ctx = {
        "ff": ff,
        "open_file": api.open_file,
        "register_variable": api.register_variable,
        "register_derived_function": api.register_derived_function,
        "auto_scalarize": api.auto_scalarize,
        "velocity_gradient": api.velocity_gradient,
        "register_velocity_gradient": api.register_velocity_gradient,
        "register_vorticity": api.register_vorticity,
        "register_q_criterion": api.register_q_criterion,
    }
    return ctx
