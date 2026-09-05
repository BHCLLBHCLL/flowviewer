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
import json
import os
import shutil
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


@dataclass(frozen=True)
class Param:
    """A single tunable parameter exposed by an Analysis report kind.

    ``type`` drives both the dialog widget and pure coercion: ``int`` | ``float``
    | ``bool`` | ``choice`` | ``str`` | ``str_opt`` | ``tuple``. ``str_opt`` maps
    empty free text to ``None``; ``tuple`` stores an ordered set of tokens. All
    values are kept JSON-serializable so a snapshot can round-trip through the
    dialog and be re-fed to :func:`run_report`.
    """
    key: str
    label: str
    type: str
    default: Any = None
    choices: tuple = ()
    min: Optional[int] = None
    max: Optional[int] = None
    help: str = ""


_SOURCE_CHOICES = ("pod", "dmd")


def _field_frame_params() -> list[Param]:
    """Shared params for the whole-mesh field-map family (R58-R61)."""
    return [
        Param("source", "Reconstruction source", "choice", "pod", _SOURCE_CHOICES,
              help="pod (R53) or dmd (R55) mode shapes drive the frame sequence"),
        Param("cycles", "Cycle window (A:B)", "str_opt", None,
              help="e.g. 0:100; blank = all cycles"),
        Param("dt", "Sample period (s)", "float", None,
              help="blank = infer from the cycle axis"),
        Param("step", "Frame stride", "int", 1, min=1),
        Param("frames", "Frame count", "int", None, min=1,
              help="blank = use every frame in the window"),
        Param("k", "Mode count", "int", None, min=1,
              help="top-k modes for the reconstruction; blank = auto"),
        Param("p", "IDW power", "float", 2.0, min=0.1),
        Param("neighbors", "Neighbours", "int", 4, min=1),
        Param("preview", "Bin grid", "int", 24, min=2),
    ]


def _welch_params() -> list[Param]:
    """Params for the Welch / reference-probe field maps (R59-R60)."""
    return [
        Param("ref_probe", "Reference probe", "int", 0, min=0,
              help="probe index the field coheres/relates against"),
        Param("nperseg", "FFT segment", "int", None, min=2,
              help="Welch segment length; blank = auto"),
        Param("blocksize", "Block size", "int", 4096, min=16),
    ]


def _spatial_params() -> list[Param]:
    """Params for the modal-snapshot spatial reports (R54/R55/R62)."""
    return [
        Param("cycles", "Cycle window (A:B)", "str_opt", None,
              help="e.g. 0:100; blank = all cycles"),
        Param("dt", "Sample period (s)", "float", None,
              help="blank = infer from the cycle axis"),
        Param("step", "Frame stride", "int", 1, min=1),
        Param("frames", "Frame count", "int", None, min=1),
        Param("top", "Top modes", "int", 5, min=1),
        Param("cycle", "Snapshot cycle", "int", 0, min=0,
              help="reconstruction cycle for the snapshot"),
        Param("p", "IDW power", "float", 2.0, min=0.1),
        Param("neighbors", "Neighbours", "int", 4, min=1),
        Param("preview", "Bin grid", "int", 24, min=2),
    ]


def report_params(kind: str) -> list[Param]:
    """Ordered parameter schema for ``kind`` (the R67 parameter panel)."""
    if kind not in REPORTS:
        raise ValueError(f"unknown analysis report kind: {kind!r}")
    if kind == "spectral":
        return _field_frame_params()
    if kind == "coherence":
        return _field_frame_params() + _welch_params()
    if kind == "evolution":
        return _field_frame_params() + _welch_params()
    if kind == "console":
        return _field_frame_params() + _welch_params() + [
            Param("panels", "Panels (comma-separated)", "tuple",
                  ("spectral", "coherence", "spectevol"),
                  help="which tabs the Field Console shows, e.g. spectral,coherence"),
        ]
    if kind == "spatial_pod":
        return _spatial_params()
    if kind == "spatial_dmd":
        return _spatial_params() + [
            Param("dmd_top", "DMD top modes", "int", 3, min=1),
        ]
    if kind == "spatial_field":
        return _spatial_params() + _welch_params() + [
            Param("source", "Field-map source", "choice", "pod", _SOURCE_CHOICES,
                  help="pod (R53) or dmd (R55) reconstruction for the folded maps"),
        ]
    raise ValueError(f"unknown analysis report kind: {kind!r}")


def default_params(kind: str) -> dict:
    """The default parameter snapshot for ``kind`` (all ``Param`` defaults)."""
    return {p.key: p.default for p in report_params(kind)}


def normalize_params(kind: str, raw: dict) -> dict:
    """Coerce + clamp a raw dict into a safe parameter snapshot for ``kind``.

    Unknown keys are dropped; missing keys take their ``Param`` default; values
    are cast per ``Param.type`` (empty free text maps to the default, optional
    numerics map blank to ``None``). The returned snapshot is JSON-serializable.
    """
    out = {}
    for p in report_params(kind):
        out[p.key] = _coerce(p, raw.get(p.key, p.default))
    return out


def param_summary(kind: str, params: dict) -> str:
    """Short human-readable summary of an active parameter snapshot."""
    if not params:
        return "defaults"
    parts = []
    for p in report_params(kind):
        v = params.get(p.key, p.default)
        if v in (None, "", p.default):
            continue
        parts.append(f"{p.key}={v}")
    return ", ".join(parts) if parts else "defaults"


def _coerce(p: Param, v: Any) -> Any:
    """Coerce a single raw value to ``p.type`` with range clamping."""
    if v is None:
        return p.default
    if p.type == "int":
        try:
            i = int(v)
        except (TypeError, ValueError):
            return p.default
        if p.min is not None:
            i = max(i, p.min)
        if p.max is not None:
            i = min(i, p.max)
        return i
    if p.type == "float":
        if isinstance(v, str) and not v.strip():
            return p.default
        try:
            f = float(v)
        except (TypeError, ValueError):
            return p.default
        if p.min is not None:
            f = max(f, p.min)
        if p.max is not None:
            f = min(f, p.max)
        return f
    if p.type == "bool":
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return p.default
    if p.type == "choice":
        return v if v in p.choices else p.default
    if p.type == "tuple":
        if isinstance(v, (tuple, list)):
            return tuple(str(x) for x in v)
        if isinstance(v, str) and v.strip():
            return tuple(x.strip() for x in v.split(",") if x.strip())
        return p.default
    if p.type == "str_opt":
        str_v = str(v)
        return None if not str_v.strip() else str_v
    if isinstance(v, str):
        return v.strip() if v else ""
    return str(v)


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
               preview: int = 24, k=None, p: float = 2.0, neighbors: int = 4,
               ref_probe: int = 0, nperseg=None, blocksize: int = 4096,
               dmd_top: int = 3, cycle: int = 0,
               panels=("spectral", "coherence", "spectevol"),
               field_name: str = "", source: Optional[str] = None) -> Optional[str]:
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
          "preview": preview, "top": top, "k": k, "p": p, "neighbors": neighbors,
          "ref_probe": ref_probe, "nperseg": nperseg, "blocksize": blocksize,
          "dmd_top": dmd_top, "cycle": cycle, "panels": panels}
    if source:
        kw["source"] = source
    if kind in ("spectral", "coherence", "evolution", "console") and field_name:
        kw["field"] = field_name
    if kind == "spatial_dmd":
        kw["dmd"] = True
    if kind == "spatial_field":
        kw["field"] = True
        kw.setdefault("source", "pod")
    summary = _call(rk.write, vert, artifact, out_dir, **kw)
    rel = summary.get("html") if isinstance(summary, dict) else None
    if rel:
        return str(Path(out_dir) / rel)
    return str(Path(out_dir))


def field_names(ts) -> list[str]:
    """Monitoring-point / series names available on a ``TimeSeriesObject``."""
    if ts is None:
        return []
    return [str(n) for n in (ts.series or {}).keys()]


def artifact_from_timeseries(ts, field=None) -> dict:
    """Build an R38-style trace artifact from a ``TimeSeriesObject``-like object.

    Each named ``series`` becomes a probe; its coordinate (when present in the
    object's ``probes`` ``(name, x, y, z)`` list) becomes the probe's ``xyz``.
    ``field`` selects a single series; ``None`` uses *every* series as a probe
    (the multi-probe form the POD / DMD / spatial report family expects). The
    returned dict matches :func:`fv.spectralmap.build_spectral_report` and the
    other report builders: ``{name, cycles, probes:[{query, node, xyz, values}]}``.
    """
    cycles = list(ts.cycles or [])
    coord: dict = {}
    for item in (ts.probes or []):
        try:
            coord[str(item[0])] = tuple(float(v) for v in item[1:4])
        except (TypeError, ValueError, IndexError):
            coord[str(item[0])] = None
    probes: list = []
    for name, values in (ts.series or {}).items():
        if field is not None and str(name) != str(field):
            continue
        xyz = coord.get(str(name))
        q = (0.0, 0.0, 0.0) if xyz is None else xyz
        vals = list(values) if values is not None else []
        probes.append({
            "query": q,
            "node": -1,
            "xyz": xyz,
            "values": [float(v) for v in vals],
        })
    if not probes:
        raise ValueError(
            "timeseries carries no series"
            + (f" for field {field!r}" if field is not None else ""))
    return {"name": str(field) if field is not None else "Time Series",
            "cycles": cycles, "probes": probes}


def artifact_summary(artifact) -> str:
    """Short human-readable summary of an artifact (status-bar display)."""
    if not artifact:
        return "none"
    probes = list(artifact.get("probes", []) or [])
    return (f"{artifact.get('name') or '?'} · {len(probes)} probe(s), "
            f"{len(list(artifact.get('cycles', []) or []))} cycle(s)")


def copy_report(src, dest_dir, name=None) -> Optional[Path]:
    """Copy a self-contained HTML report to ``dest_dir`` and return the path.

    The R58-R65 report family emits single-file HTML (inline JS/CSS), so a
    report is copied as one file. Creates ``dest_dir`` when needed and returns
    ``None`` -- without raising -- when ``src`` is missing or unreadable.
    """
    p = Path(src)
    if not p.is_file():
        return None
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / (name or p.name)
    try:
        shutil.copyfile(p, out)
    except OSError:
        return None
    return out

def default_preset_path() -> Path:
    """Stable per-user location for the named parameter-preset file."""
    return Path.home() / ".flowviewer" / "analysis_presets.json"


class PresetStore:
    """Named parameter-preset store, optionally persisted to a JSON file.

    Layout: ``{kind: {name: normalized_params}}``. ``save`` normalises incoming
    params via :func:`normalize_params` (so only known, coerced keys are stored)
    and raises on an unknown ``kind``. With ``path=None`` the store is in-memory
    only (ideal for tests); otherwise every mutation is flushed to the JSON file
    so presets survive restarts. All values are JSON-serializable by design.
    """

    def __init__(self, path: Optional[os.PathLike] = None):
        self._path = None if path is None else Path(path)
        self._data: dict = {}
        if self._path is not None and self._path.is_file():
            try:
                loaded = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._data = loaded
            except (OSError, ValueError):
                self._data = {}

    @property
    def path(self) -> Optional[Path]:
        """The backing JSON file, or ``None`` for an in-memory store."""
        return self._path

    def _persist(self) -> None:
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8")

    def save(self, kind: str, name: str, params: dict) -> dict:
        """Store ``params`` under ``(kind, name)``; returns the normalised dict."""
        snapshot = normalize_params(kind, params)
        self._data.setdefault(kind, {})[str(name)] = snapshot
        self._persist()
        return snapshot

    def load(self, kind: str, name: str) -> Optional[dict]:
        """Return the stored snapshot, or ``None`` when missing/invalid."""
        bucket = self._data.get(kind)
        if not bucket:
            return None
        snap = bucket.get(str(name))
        return dict(snap) if isinstance(snap, dict) else None

    def delete(self, kind: str, name: str) -> bool:
        """Remove one preset; returns ``True`` if it existed."""
        bucket = self._data.get(kind)
        if not bucket or str(name) not in bucket:
            return False
        del bucket[str(name)]
        if not bucket:
            self._data.pop(kind, None)
        self._persist()
        return True

    def names(self, kind: str) -> list:
        """Sorted preset names for ``kind``."""
        return sorted((self._data.get(kind) or {}).keys())

    def kinds(self) -> list:
        """Sorted kinds that hold at least one preset."""
        return sorted(k for k, bucket in self._data.items() if bucket)

    def clear(self) -> None:
        """Drop every preset."""
        self._data = {}
        self._persist()

