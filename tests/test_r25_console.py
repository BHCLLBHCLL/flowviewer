"""R25-S3 - embedded Python console: stdout capture, error surfacing and the
scPOST-derived-function smoke test inside a headless ConsoleSession.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

FPH = r"D:\training\cgns\examples\tr03_9.fph"
_HAS_FPH = Path(FPH).exists()


@pytest.fixture()
def session():
    from fv.console import ConsoleSession
    return ConsoleSession()


def test_console_captures_stdout(session):
    ok, out = session.run("print('hello', 1 + 1)")
    assert ok is True
    assert "hello 2" in out


def test_console_surfaces_exception(session):
    ok, out = session.run("1 / 0")
    assert ok is False
    assert "ZeroDivisionError" in out


def test_console_namespace_carries_over(session):
    session.run("x = 21")
    ok, out = session.run("x * 2")
    assert ok is True
    assert out.strip() == ""
    assert session.namespace.get("x") == 21
    assert session.run("x + 1")[0] is True


def test_default_context_bindings():
    from fv.console import default_context
    ctx = default_context()
    for key in ("open_file", "register_variable",
                "register_derived_function", "auto_scalarize"):
        assert key in ctx and callable(ctx[key])


@pytest.mark.skipif(not _HAS_FPH, reason="sample not present")
def test_console_register_derived_function_smoke():
    """register_derived_function works from inside an embedded console."""
    from fv.console import ConsoleSession, default_context
    from fv.model.dataset import load_file

    ff = load_file(FPH)
    sess = ConsoleSession(default_context(ff))
    ok, out = sess.run(
        "register_derived_function(ff, 'PRES2',"
        " lambda **kw: kw['PRES'] * 2.0)")
    assert ok is True
    assert "PRES2" in ff.variables
    import numpy as np
    assert np.asarray(ff.variables["PRES2"].array).shape == \
        np.asarray(ff.variables["PRES"].array).shape
