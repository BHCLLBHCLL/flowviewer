"""R20 - multi-dataset statistics and automated reporting (beyond-scPOST).

Exercises :mod:`fv.model.report`: per-dataset variable stats, a flat
aggregate report across multiple datasets/cycles, pairwise deltas against a
reference dataset, and CSV serialisation.
"""

import os
import sys
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

FPH = r"D:\training\cgns\examples\tr03_9.fph"

from fv.model.report import (  # noqa: E402
    _shared_vars,
    aggregate_report,
    dataset_stats,
    delta_report,
    to_csv,
)


def _cycle(ff, offset):
    """A distinct dataset sharing ff's mesh with PRES shifted by offset."""
    base = np.asarray(ff.variables["PRES"].array)
    f2 = replace(ff)
    v = dict(f2.variables)
    v["PRES"] = replace(v["PRES"], array=base + offset)
    f2.variables = v
    return f2


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_dataset_stats_shape():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    st = dataset_stats(ff, variables=["PRES"])["PRES"]
    assert st["location"] == "cell"
    assert st["kind"] == "scalar"
    assert st["n"] == ff.n_cells
    assert st["min"] <= st["mean"] <= st["max"]
    assert st["rms"] >= 0.0


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_aggregate_report_rows_and_labels():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    cycles = [_cycle(ff, 0.0), _cycle(ff, 10.0), _cycle(ff, 20.0)]
    rows = aggregate_report(cycles, variables=["PRES"], labels=["c0", "c1", "c2"])
    assert [r["dataset"] for r in rows] == ["c0", "c1", "c2"]
    means = [r["mean"] for r in rows]
    assert means[1] == pytest.approx(means[0] + 10.0, rel=1e-9)
    assert means[2] == pytest.approx(means[0] + 20.0, rel=1e-9)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_delta_report_offset_equal_to_shift():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    ref = ff
    moved = _cycle(ff, 10.0)
    rows = delta_report([ref, moved], reference=0, variables=["PRES"],
                        labels=["ref", "moved"])
    by = {r["dataset"]: r for r in rows}
    assert by["ref"]["mean"] == pytest.approx(0.0, abs=1e-6)   # |A - A|
    assert by["moved"]["mean"] == pytest.approx(10.0, rel=1e-6)  # |(P+10) - P|


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_delta_signed_mode():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    moved = _cycle(ff, 10.0)
    rows = delta_report([ff, moved], reference=0, variables=["PRES"],
                        mode="signed", labels=["ref", "moved"])
    by = {r["dataset"]: r for r in rows}
    # signed diff = reference - current, so a +10 cycle gives -10
    assert by["moved"]["mean"] == pytest.approx(-10.0, rel=1e-6)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_reference_out_of_range_raises():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    with pytest.raises(ValueError):
        delta_report([ff], reference=3, variables=["PRES"])


def test_to_csv_empty():
    assert to_csv([]) == ""


def test_to_csv_header_and_columns():
    rows = [{"dataset": "a", "var": "P", "min": 1.0, "max": 2.0}]
    csv_text = to_csv(rows)
    assert csv_text.splitlines()[0].startswith("dataset,var,min,max")
    assert "a,P,1.0,2.0" in csv_text


def test_shared_vars_intersection():
    from types import SimpleNamespace
    a = SimpleNamespace(variables={"P": 1, "Q": 2})
    b = SimpleNamespace(variables={"Q": 2, "R": 3})
    assert _shared_vars([a, b]) == ["P", "Q", "R"]  # union, sorted
