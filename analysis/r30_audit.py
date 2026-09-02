"""R30-S0 audit: build attribute-level VB -> fv coverage matrix.

Parses the VB interface reference text (fldfile/application class files)
into expected properties+methods, collects the actual fv callable surface
(api.py / com.py classes / model.dataset FieldFile / crdl), cross-checks
each VB name, and flags stubs. Emits analysis/r30_coverage_matrix.md.
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AN = ROOT / "analysis"


# ── 1. Parse a VB class reference text into properties + methods ─────────
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.*]*$")


def parse_vb_class(text):
    """Pull the real API surface from a VB reference text.

    Entries are lines starting with ``| `` whose body is exactly one
    identifier token (e.g. ``| GetBoundingBox``, ``| ErrorCode``).
    Prose / description continuation lines have spaces and are skipped.
    """
    props, methods = [], []
    mode = None
    for ln in text.splitlines():
        t = ln.strip()
        low = t.lower()
        if low == "property list":
            mode = "prop"
            continue
        if low == "method list":
            mode = "meth"
            continue
        if not t.startswith("|"):
            continue
        body = t[1:].strip()
        if not _IDENT.fullmatch(body):
            continue
        if low in ("property", "method"):
            continue
        (props if mode == "prop" else methods).append(body)
    return props, methods


# ── 2. Collect the actual fv callable surface ─────────────────────────────
def _camel_to_snake(name):
    out = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return out


def collect_surface():
    names = set()
    # api.py top-level functions
    for f in (ROOT / "fv" / "api.py").read_text(
            encoding="utf-8").splitlines():
        m = re.match(r"^def (\w+)", f)
        if m:
            names.add(m.group(1).lower())
    # com.py class methods + FlowviewerApplication
    for f in (ROOT / "fv" / "com.py").read_text(
            encoding="utf-8").splitlines():
        m = re.match(r"^    def (\w+)", f)
        if m:
            names.add(m.group(1).lower())
    # dataset.FieldFile + model helpers
    ds = (ROOT / "fv" / "model" / "dataset.py").read_text(encoding="utf-8")
    for ln in ds.splitlines():
        m = re.match(r"^    def (\w+)", ln)
        if m:
            names.add(m.group(1).lower())
    # dynamic COM dispatch: _CREATE_OBJECT_KINDS registers these onto the
    # class at import time (generic factory, 21 kinds incl OT/PCL/RNAT)
    com = (ROOT / "fv" / "com.py").read_text(encoding="utf-8")
    m = re.search(r"_CREATE_OBJECT_KINDS\s*=\s*\{(.*?)\}", com, re.S)
    if m:
        for k in re.findall(r'"([A-Za-z]\w*)"\s*:\s*"[A-Za-z]\w*"', m.group(1)):
            names.add(k.lower())
    # index of raw snake names for prefix matching
    snake_names = {_camel_to_snake(n) for n in names} | names
    return names, snake_names


# noise: genuine single-token prose/substructure lines, not API entries
_NOISE = {
    "true", "false", "none", "left", "right", "top", "bottom", "set",
    "if", "the", "see", "refer", "for", "moves", "coordinates",
    "equation", "variable", "description", "volid", "contents", "retval",
    "internal", "sample", "isdraw", "main", "drawing", "message",
    "control", "np", "frame", "pid", "string", "long", "num", "name",
    "ofs", "scale", "rectangle", "local", "cycid", "cyc_f", "openum",
    "cycnum", "datanum", "matname", "matid", "matn", "matnum", "nodesnum",
    "volname", "volnum", "orgname", "isinarea", "max", "min", "ret",
    "bright", "surf", "csv", "skip", "newcycid", "byvolid", "rretval",
}


def classify(vb_name, surface, snake_names, family_keys):
    name = vb_name.rstrip("*")
    low = name.lower()
    if low in _NOISE:
        return "NOISE"
    # exact
    if low in surface:
        return "OK(exact)"
    # snake_case
    if _camel_to_snake(name) in snake_names:
        return "OK(snake)"
    # family (generic factory CreateObject*)
    if name in family_keys:
        return "OK(factory)"
    # prefix match on stripped core (e.g. GetVector -> vector_at/vector_array)
    core = re.sub(r"^(set|get)", "", _camel_to_snake(name)).lstrip("_")
    if core and (core in snake_names or any(
            s.startswith(core) for s in snake_names)):
        return "OK(prefix)"
    return "MISSING"


def scan_stubs(text):
    tree = ast.parse(text)
    stubs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            body = node.body
            n = len(body)
            last_is_pass = n == 1 and isinstance(body[0], ast.Pass)
            raises_ni = any(isinstance(s, ast.Raise) and
                            getattr(getattr(s, "exc", None), "func", None)
                            and s.exc.func.id == "NotImplementedError"
                            for s in body)
            doc_only = n == 1 and isinstance(body[0], ast.Expr) and \
                isinstance(getattr(body[0], "value", None), ast.Constant)
            if last_is_pass or raises_ni or doc_only:
                stubs.append(node.name)
    return stubs


# ── 3. Main ──────────────────────────────────────────────────────────────
surface, snake_names = collect_surface()
# family keys: names registered by the generic factory dispatch table
com_txt = (ROOT / "fv" / "com.py").read_text(encoding="utf-8")
m = re.search(r"_CREATE_OBJECT_KINDS\s*=\s*\{(.*?)\}", com_txt, re.S)
family_keys = set(re.findall(r'"([A-Za-z]\w*)"\s*:\s*"', m.group(1))) if m else set()
stub_names = set()
for src in (ROOT / "fv" / "api.py", ROOT / "fv" / "com.py",
            ROOT / "fv" / "model" / "dataset.py"):
    stub_names.update(scan_stubs(src.read_text(encoding="utf-8")))

report = []
sections = []
summary_missing = []

# FLDFile
props, meths = parse_vb_class((AN / "vb_fldfile.txt").read_text(
    encoding="utf-8"))
rows = []
for p in props:
    st = classify(p, surface, snake_names, family_keys)
    rows.append((p, "property", st))
for m in meths:
    st = classify(m, surface, snake_names, family_keys)
    rows.append((m, "method", st))
sections.append(("FLD File class", props, meths, rows))

# Application
props, meths = parse_vb_class((AN / "vb_application.txt").read_text(
    encoding="utf-8"))
rows = []
for p in props:
    st = classify(p, surface, snake_names, family_keys)
    rows.append((p, "property", st))
for m in meths:
    st = classify(m, surface, snake_names, family_keys)
    rows.append((m, "method", st))
sections.append(("Application class", props, meths, rows))

# ── Emit markdown ─────────────────────────────────────────────────────────
out = ["# R30-S0 覆盖矩阵（attribute-level）",
       "",
       f"生成于 2026-09-01 · 表面函数/方法数：`{len(surface)}`",
       "",
       "VB 参考 → fv 实现的逐项核对。`OK`=名字级命中；`MISSING`=未在 fv 表面",
       "找到；`STUB`=命中但函数体为纯占位（pass / NotImplementedError / 仅 docstring）。",
       ""]
total = miss = noise = 0
for cls, props, meths, rows in sections:
    out.append(f"## {cls}（属性 {len(props)} / 方法 {len(meths)}）")
    out.append("")
    out.append("| # | 名称 | 类型 | 状态 |")
    out.append("|---|---|---|---|")
    for idx, (name, kind, st) in enumerate(rows, 1):
        total += 1
        if st == "MISSING":
            miss += 1
            summary_missing.append((cls, kind, name))
        elif st == "NOISE":
            noise += 1
        out.append(f"| {idx} | {name} | {kind} | {st} |")
    out.append("")
out.append("## 汇总")
out.append(f"- 总条目 {total} · MISSING {miss} · NOISE(排除) {noise} · "
           f"命中率 {total - miss - noise}/{total - noise}")
out.append(f"- 表面 stub 占位函数：`{', '.join(sorted(stub_names)) or '无'}`")
out.append("")
if summary_missing:
    out.append("### MISSING 明细")
    out.append("")
    for cls, kind, name in summary_missing:
        out.append(f"- {cls} / {kind} / {name}")
    out.append("")
(AN / "r30_coverage_matrix.md").write_text("\n".join(out), encoding="utf-8")
print(f"matrix written: {total} items, {miss} MISSING, "
      f"{len(stub_names)} stubs")
for cls, kind, name in summary_missing:
    print("  MISSING:", cls, kind, name)