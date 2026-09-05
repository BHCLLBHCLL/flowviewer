"""R64: GUI hooks for the standalone analysis-report family.

R58-R63 emit self-contained HTML reports (spectral field, coherence field,
spectro-evolution, the tabbed field console and the spatial POD/DMD/full-field
report) purely from ``(verts, artifact)``. R64 wires those into the GUI: an
``Analysis`` menu lists the report kinds, and a dockable ``ReportPanel``
(WebEngine-backed when available, otherwise an "open in browser" fallback)
shows the generated HTML. The pure pieces live here so they stay
headless-testable; ``reportview`` owns only the Qt widget. No PyQt import here
— this module must import cleanly without a display.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from ..coherencemap import build_coherence_report, write_coherence_report
from ..fieldconsole import build_console, write_console
from ..spatialreport import build_spatial_report, write_spatial_report
from ..spectevol import build_spectevol_report, write_spectevol_report
from ..spectralmap import build_spectral_report, write_spectral_report


@dataclass(frozen=True)
class ReportKind:
    """A report generator: display ``title`` + the pure ``build``/``write``."""

    key: str
    title: str
    build: Callable[..., Any]
    write: Callable[..., Any]


REPORTS: dict[str, ReportKind] = {
    "spectral": ReportKind("spectral", "Spectral Field Map (R58)",
                           build_spectral_report, write_spectral_report),
    "coherence": ReportKind("coherence", "Coherence Field Map (R59)",
                            build_coherence_report, write_coherence_report),
    "evolution": ReportKind("evolution", "Spectro-evolution Field (R60)",
                            build_spectevol_report, write_spectevol_report),
    "console": ReportKind("console", "Field Console (R61)",
                          build_console, write_console),
    "spatial_pod": ReportKind("spatial_pod", "Spatial POD Report (R54)",
                              build_spatial_report, write_spatial_report),
    "spatial_dmd": ReportKind("spatial_dmd", "Spatial DMD Report (R55)",
                              build_spatial_report, write_spatial_report),
    "spatial_field": ReportKind("spatial_field", "Full-field Maps (R62)",
                                build_spatial_report, write_spatial_report),
}


def report_menu() -> list[tuple[str, str]]:
    """Ordered ``(key, title)`` pairs for the GUI Analysis menu."""
    return [(k, r.title) for k, r in REPORTS.items()]


def prepare_verts(dataset) -> np.ndarray:
    """Extract an ``(N, 3)`` vertex array from a ``FieldFile``/dataset object.

    Returns an empty ``(0, 3)`` array when the dataset carries no vertex
    buffer (e.g. an unopened or point-only dataset) so callers can degrade
    gracefully instead of crashing.
    """
    verts = getattr(dataset, "vertices", None)
    if verts is None:
        return np.empty((0, 3), dtype=np.float64)
    return np.asarray(verts, dtype=np.float64).reshape((-1, 3))


def _call(fn: Callable[..., Any], verts: np.ndarray, artifact: dict,
          out_dir: str, **kw: Any) -> Any:
    """Invoke ``fn(verts, artifact, out_dir, **kw)`` keeping only accepted kw."""
    params = inspect.signature(fn).parameters
    ok = {k: v for k, v in kw.items() if k in params}
    return fn(verts, artifact, out_dir, **ok)


def run_report(kind: str, verts, artifact, out_dir: str, *, dt=None,
               cycles=None, step: int = 1, frames=None, dmd: bool = False,
               field: bool = False, top: Optional[int] = 5,
               preview: int = 24) -> Optional[str]:
    """Generate + write the ``kind`` report and return its HTML path (or None).

    Returns ``None`` — without raising — when ``artifact`` is missing so the
    GUI can show a status hint instead of crashing. ``kind`` must be a key of
    ``REPORTS``; unknown keys raise ``ValueError``. Only the keyword arguments a
    particular ``write`` accepts are forwarded, keeping the per-pipeline
    signatures (spectral family vs spatial family) mutually safe.
    """
    rk = REPORTS.get(kind)
    if rk is None:
        raise ValueError(f"unknown analysis report kind: {kind!r}")
    if artifact is None:
        return None
    vert = np.asarray(verts, dtype=np.float64)
    kw = {"dt": dt, "cycles": cycles, "step": step, "frames": frames,
          "preview": preview, "top": top}
    if kind == "spatial_dmd":
        kw["dmd"] = True
    if kind == "spatial_field":
        kw["field"] = True
        kw["source"] = "pod"
    summary = _call(rk.write, vert, artifact, out_dir, **kw)
    rel = summary.get("html") if isinstance(summary, dict) else None
    if rel:
        return str(Path(out_dir) / rel)
    return str(Path(out_dir))
