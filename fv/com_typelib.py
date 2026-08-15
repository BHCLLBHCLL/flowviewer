"""Build the flowviewer COM type library (typelib) with pythoncom (2-boundary).

A typelib lets win32com makepy generate the event class, which in turn lets
``win32com.client.DispatchWithEvents("flowviewer.Application", Sink)`` connect
directly.  The typelib declares:

* coclass FlowviewerApplication (CLSID = the registered class);
* IFlowviewerApplication  - default dispinterface (open_file(path));
* IFlowviewerApplicationEvents - [source] dispinterface (OnOpen(path), OnClose)
  with DISPIDs 1000/1001 matching ConnectionPoint._DISPIDS.

``ensure_typelib`` writes the .tlb next to this module (idempotent); the COM
registration picks it up via ``_reg_typelib_filename_``.
"""

from __future__ import annotations

import os

TYPELIB_GUID = "{F1A2B3C4-5D6E-4F7A-8B9C-0D1E2F3A4B5D}"
DEFAULT_IFACE_IID = "{D1A2B3C4-5D6E-4F7A-8B9C-0D1E2F3A4B5D}"
EVENTS_IID = "{E1A2B3C4-5D6E-4F7A-8B9C-0D1E2F3A4B5C}"
COCLASS_CLSID = "{A1B2C3D4-5E6F-4A7B-8C9D-0D1E2F3A4B5C}"
TYPELIB_VERSION = (1, 0)
TYPELIB_FILENAME = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "flowviewer.tlb")


def _funcdesc(memid, ret_vt, param_vts):
    """A dispatch FUNCDESC: memid, return vt, list of param vts."""
    import pythoncom
    fd = pythoncom.FUNCDESC()
    fd.memid = int(memid)
    fd.funckind = pythoncom.FUNC_DISPATCH
    fd.invkind = pythoncom.INVOKE_FUNC
    fd.callconv = 4  # CC_STDCALL
    fd.cParamsOpt = 0
    fd.oVft = 0
    fd.wFuncFlags = 0
    fd.rettype = ((ret_vt, None), 0, None)
    fd.args = [((vt, None), 0, None) for vt in param_vts]
    return fd


def _add_method(ti, index, name, memid, ret_vt, param_specs):
    """Add one dispatch method; param_specs is [(param_name, vt), ...]."""
    names = [name] + [pn for pn, _ in param_specs]
    vts = [vt for _, vt in param_specs]
    ti.AddFuncDesc(index, _funcdesc(memid, ret_vt, vts))
    ti.SetFuncAndParamNames(index, tuple(names))


def build_typelib(filename):
    """Write the flowviewer typelib to *filename* (overwrites)."""
    import pythoncom
    tlb = pythoncom.CreateTypeLib2(pythoncom.SYS_WIN32, filename)
    tlb.SetGuid(TYPELIB_GUID)
    tlb.SetVersion(*TYPELIB_VERSION)
    tlb.SetName("flowviewer")
    tlb.SetLcid(0)
    tlb.SetDocString("flowviewer post-processor type library")

    # [source] event interface: OnOpen(path) / OnClose()
    ev = tlb.CreateTypeInfo("IFlowviewerApplicationEvents",
                             pythoncom.TKIND_DISPATCH)
    ev.SetGuid(EVENTS_IID)
    ev.SetVersion(1, 0)
    ev.SetDocString("flowviewer application events")
    _add_method(ev, 0, "OnOpen", 1000, pythoncom.VT_VOID,
                [("path", pythoncom.VT_BSTR)])
    _add_method(ev, 1, "OnClose", 1001, pythoncom.VT_VOID, [])
    ev.LayOut()

    # default interface: open_file(path)
    app = tlb.CreateTypeInfo("IFlowviewerApplication",
                              pythoncom.TKIND_DISPATCH)
    app.SetGuid(DEFAULT_IFACE_IID)
    app.SetVersion(1, 0)
    app.SetDocString("flowviewer application")
    _add_method(app, 0, "open_file", 1000, pythoncom.VT_VOID,
                [("path", pythoncom.VT_BSTR)])
    app.LayOut()

    # coclass: default + source impltypes
    co = tlb.CreateTypeInfo("FlowviewerApplication",
                             pythoncom.TKIND_COCLASS)
    co.SetGuid(COCLASS_CLSID)
    co.SetVersion(1, 0)
    co.SetDocString("flowviewer.Application")
    co.AddImplType(0, co.AddRefTypeInfo(app))
    co.SetImplTypeFlags(0, pythoncom.IMPLTYPEFLAG_FDEFAULT)
    co.AddImplType(1, co.AddRefTypeInfo(ev))
    co.SetImplTypeFlags(1, pythoncom.IMPLTYPEFLAG_FSOURCE)
    co.LayOut()

    tlb.SaveAllChanges()
    del ev, app, co, tlb
    return filename


def ensure_typelib(filename=None):
    """Generate the bundled typelib when missing; returns its path or None."""
    target = filename or TYPELIB_FILENAME
    try:
        if not os.path.exists(target):
            build_typelib(target)
        return target
    except Exception:
        return None
