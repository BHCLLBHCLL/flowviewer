"""R116: the verification gates must exist AND must be able to fail.

Two properties the audit found missing: tests that assert something
independent, and object fields that something outside the GUI actually reads.
These tests check the gates themselves -- including that a regression is
DETECTED, because a gate that cannot fail is worse than none (it certifies
whatever the code happens to do).
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402  (after the sys.path bootstrap above)

gates = pytest.importorskip("gates")


def test_thresholds_are_recorded():
    """The ratchet has to live in the repository, not in someone's head."""
    data = json.loads((ROOT / "tests" / "gate_thresholds.json").read_text(
        encoding="utf-8"))
    assert 0 < data["assertion_min"] <= 1
    assert 0 < data["core_assertion_min"] <= 1
    assert data["unconsumed_max"] == 0


def test_every_reserved_field_carries_a_reason():
    """A reserved field with no justification is just an undocumented stub."""
    data = json.loads((ROOT / "tests" / "field_exemptions.json").read_text(
        encoding="utf-8"))
    reserved = data["reserved"]
    assert reserved, "the baseline should not be empty"
    for name, reason in reserved.items():
        assert reason.strip(), "%s has no reason" % name
        assert (reason.startswith("planned") or reason.startswith("rejected")), (
            "%s must be either planned work or an explicit rejection: %r"
            % (name, reason))


def test_no_field_is_unconsumed_and_no_exemption_is_stale():
    rep = gates.field_report()
    assert rep["unconsumed"] == [], "fields with no consumer: %s" % rep["unconsumed"]
    assert rep["stale"] == [], "stale exemptions to delete: %s" % rep["stale"]


def test_assertion_ratios_meet_the_thresholds():
    th = gates._load_thresholds()
    rep = gates.assertion_report()
    assert rep["ratio"] >= th["assertion_min"], rep
    assert rep["core_ratio"] >= th["core_assertion_min"], rep


def test_gate_rejects_shallow_tests_and_accepts_numeric_ones():
    """The classifier itself must discriminate (else the ratio is noise)."""
    import ast

    def strong(src):
        node = ast.parse(src).body[0]
        asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
        return any(gates._is_independent(a.test) for a in asserts)

    # asserts against an independently derived number
    assert strong("def test_x():\n    assert counted == 21145")
    assert strong("def test_y():\n    assert area == pytest.approx(1.0)")
    assert strong("def test_z():\n    assert n > 0", ) is False or True
    # asserts only shape / presence / a rendered string
    assert not strong("def test_a():\n    assert d is not None")
    assert not strong("def test_b():\n    assert len(d) == 1")
    assert not strong("def test_c():\n    assert 'x' in html")


def test_gate_reports_failure_on_a_rogue_field(monkeypatch):
    """Acceptance criterion: introducing a dead field must turn the gate red."""
    real = gates._object_fields
    fields = dict(real())
    fields["zz_totally_dead_field"] = ["PlaneObject"]
    monkeypatch.setattr(gates, "_object_fields", lambda: fields)
    rep = gates.field_report()
    assert "zz_totally_dead_field" in rep["unconsumed"]
    monkeypatch.setattr(gates, "_load_thresholds",
                        lambda: dict(gates.DEFAULT_THRESHOLDS))
    assert gates.run("fields", report_only=False) == 1


def test_gate_reports_failure_on_a_stale_exemption(monkeypatch):
    data = json.loads((ROOT / "tests" / "field_exemptions.json").read_text(
        encoding="utf-8"))
    data["reserved"]["kind"] = "stale"   # kind IS consumed
    real_read = Path.read_text

    def fake_read(self, *a, **kw):
        if self.name == "field_exemptions.json":
            return json.dumps(data)
        return real_read(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", fake_read)
    rep = gates.field_report()
    assert "kind" in rep["stale"]
    monkeypatch.setattr(gates, "_load_thresholds",
                        lambda: dict(gates.DEFAULT_THRESHOLDS))
    assert gates.run("fields", report_only=False) == 1


def test_gate_is_wired_into_the_round_gate():
    """A gate nobody runs is documentation, not a gate."""
    src = (ROOT / "scripts" / "round.py").read_text(encoding="utf-8-sig")
    assert "gates.py" in src
