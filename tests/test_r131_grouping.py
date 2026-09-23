"""R131 - a Grouping must actually toggle its members.

R124 found the gap while chasing a field-gate exemption: the Grouping dialog
collects member and nested-subgroup labels, objects.grouping_members resolves
them, and nothing ever called it -- so toggling a grouping in the object tree
changed nothing at all. This pins the resolution rules and the wiring.

The objects here are duck-typed stand-ins (label / visible / member_labels /
subgroups): grouping_members only reads those attributes, so the test exercises
the real resolver without constructing GUI dataclasses.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fv.model.objects import grouping_members, set_grouping_visibility  # noqa: E402


class _Node:
    """Stand-in for a renderable object or a grouping."""

    def __init__(self, label, members=(), subgroups=()):
        self.label = label
        self.visible = True
        self.member_labels = list(members)
        self.subgroups = list(subgroups)


def _scene():
    a, b, c = _Node("A"), _Node("B"), _Node("C")
    g1 = _Node("G1", ["A", "B"])
    g2 = _Node("G2", ["C"], ["G1"])
    return (a, b, c), g1, g2, {"A": a, "B": b, "C": c, "G1": g1, "G2": g2}


def test_r131_nested_groupings_resolve_in_order_without_duplicates():
    _leaves, _g1, g2, by_label = _scene()
    assert grouping_members(g2, by_label) == ["A", "B", "C"]
    assert grouping_members(by_label["G1"], by_label) == ["A", "B"]


def test_r131_grouping_visibility_reaches_every_member():
    (a, b, c), _g1, g2, by_label = _scene()
    labels = set_grouping_visibility(g2, by_label, False)
    assert labels == ["A", "B", "C"]
    assert (a.visible, b.visible, c.visible) == (False, False, False)
    set_grouping_visibility(g2, by_label, True)
    assert (a.visible, b.visible, c.visible) == (True, True, True)


def test_r131_a_subgroup_cycle_terminates():
    by_label = {
        "C1": _Node("C1", subgroups=["C2"]),
        "C2": _Node("C2", subgroups=["C1"]),
    }
    assert grouping_members(by_label["C1"], by_label) == []


def test_r131_missing_members_are_reported_not_fatal():
    _leaves, g1, _g2, by_label = _scene()
    g1.member_labels = ["A", "nope"]
    assert set_grouping_visibility(g1, by_label, False) == ["A", "nope"]


def test_r131_the_gui_toggles_groupings_through_that_helper():
    """The wiring must not silently revert to doing nothing."""
    src = (Path(__file__).resolve().parents[1] / "fv" / "gui"
           / "main.py").read_text(encoding="utf-8")
    assert "set_grouping_visibility" in src
    assert 'kind == "grouping"' in src
