"""Variable Registration expression engine (scPOST CreateVar subset, P1.1).

Registers derived variables on a FieldFile from a safe arithmetic
expression over existing variables:

- numbers and existing scalar variable names (e.g. PRES, VELX);
- operators  +  -  *  /  ^  (power)  with parentheses and unary minus;
- logic  &  (and)  @  (or)  -> 1.0 / 0.0 element-wise;
- functions  abs(x)  sqrt(x)  min(a,b)  max(a,b)  mag(VEC)  (vector
  magnitude over the VECX/VECY/VECZ components);
- comparisons  ifgt(a,b)  ifet(a,b)  ifeq(a,b)  -> 1.0 / 0.0.

The parser is a small recursive-descent evaluator with an explicit
token whitelist - no code execution, no attribute access.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .dataset import FIELD_KIND_SCALAR, FIELD_KIND_VECTOR, VarInfo


# tokeniser

_OPS = {"+", "-", "*", "/", "^", "&", "@"}

_FUNCS = {
    "abs": 1, "sqrt": 1, "min": 2, "max": 2, "mag": 1,
    "ifgt": 2, "ifet": 2, "ifeq": 2,
}

_DELTA_FUNCS = {"delx": "X", "dely": "Y", "delz": "Z"}

_VARNAME_FUNCS = {"delx", "dely", "delz", "grad", "div", "rot"}

_UNARY = {"-", "+"}


def tokenize(expr: str) -> list:
    """Split an expression into (kind, value) tokens."""
    toks = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        if c.isspace():
            i += 1
            continue
        if c.isdigit() or (c == "." and i + 1 < n and expr[i + 1].isdigit()):
            j = i
            while j < n and (expr[j].isdigit() or expr[j] in ".eE+-"):
                if expr[j] in "+-" and j > i and expr[j - 1] not in "eE":
                    break
                j += 1
            toks.append(("num", float(expr[i:j])))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            toks.append(("name", expr[i:j]))
            i = j
            continue
        if c in _OPS or c in "(),":
            toks.append(("op", c))
            i += 1
            continue
        raise ValueError("unexpected character " + repr(c) + " at " + str(i))
    toks.append(("end", ""))
    return toks


# recursive-descent evaluator

class _Eval:
    """Safe evaluator: the only external values are arrays from the
    variable map passed to evaluate()."""

    def __init__(self, toks: list, vars_: dict, n: int, ff=None):
        self._toks = toks
        self._vars = vars_
        self._n = n
        self._pos = 0
        self._ff = ff

    def _peek(self):
        return self._toks[self._pos]

    def _next(self):
        t = self._toks[self._pos]
        self._pos += 1
        return t

    def _expect_op(self, op: str) -> None:
        t = self._next()
        if t != ("op", op):
            raise ValueError("expected " + repr(op) + ", got " + repr(t))

    def evaluate(self):
        val = self._expr()
        if self._peek()[0] != "end":
            raise ValueError("trailing tokens")
        return val

    def _expr(self):
        """or-level:  a @ b"""
        v = self._term()
        while self._peek() == ("op", "@"):
            self._next()
            w = self._term()
            v = np.where((v != 0) | (w != 0), 1.0, 0.0)
        return v

    def _term(self):
        """and-level:  a & b"""
        v = self._factor()
        while self._peek() == ("op", "&"):
            self._next()
            w = self._factor()
            v = np.where((v != 0) & (w != 0), 1.0, 0.0)
        return v

    def _factor(self):
        """additive level:  a + b   a - b"""
        v = self._power()
        while self._peek()[0] == "op" and self._peek()[1] in "+-":
            op = self._next()[1]
            w = self._power()
            v = v + w if op == "+" else v - w
        return v

    def _power(self):
        """multiplicative + power level:  a * b  a / b  a ^ b"""
        v = self._unary()
        while self._peek()[0] == "op" and self._peek()[1] in "*/^":
            op = self._next()[1]
            w = self._unary()
            if op == "*":
                v = v * w
            elif op == "/":
                with np.errstate(divide="ignore", invalid="ignore"):
                    v = np.divide(v, w)
            else:
                with np.errstate(invalid="ignore"):
                    v = np.power(v, w)
        return v

    def _unary(self):
        if self._peek()[0] == "op" and self._peek()[1] in _UNARY:
            op = self._next()[1]
            v = self._unary()
            return -v if op == "-" else v
        return self._atom()

    def _atom(self):
        t = self._next()
        if t[0] == "num":
            return np.full(self._n, float(t[1]))
        if t[0] == "op" and t[1] == "(":
            v = self._expr()
            self._expect_op(")")
            return v
        if t[0] == "name":
            name = t[1]
            if name in _VARNAME_FUNCS:
                self._expect_op("(")
                vt = self._next()
                if vt[0] != "name":
                    raise ValueError(name + " takes a variable name")
                self._expect_op(")")
                return self._call_varname(name, vt[1])
            if name in self._vars:
                a = self._vars[name]
                return a if a.ndim == 1 else np.linalg.norm(a, axis=1)
            if name in _FUNCS:
                self._expect_op("(")
                args = [self._expr()]
                while self._peek() == ("op", ","):
                    self._next()
                    args.append(self._expr())
                self._expect_op(")")
                return self._call(name, args)
            raise ValueError("unknown variable or function: " + repr(name))
        raise ValueError("unexpected token " + repr(t))

    def _call_varname(self, name: str, var: str):
        """Differential operators over node fields (B1/B2)."""
        if self._ff is None:
            raise ValueError(name + " needs a field file")
        ff = self._ff
        if name in _DELTA_FUNCS:
            return _axis_difference(ff, var, _DELTA_FUNCS[name])
        if name == "grad":
            comps = [_axis_difference(ff, var, ax) for ax in "XYZ"]
            return np.column_stack(comps)
        if name == "div":
            comps = [_axis_difference(ff, var + c, ax)
                     for ax, c in (("X", "X"), ("Y", "Y"), ("Z", "Z"))]
            return comps[0] + comps[1] + comps[2]
        if name == "rot":
            def _d(comp, ax):
                return _axis_difference(ff, var + comp, ax)
            rx = _d("Y", "Z") - _d("Z", "Y")
            ry = _d("Z", "X") - _d("X", "Z")
            rz = _d("X", "Y") - _d("Y", "X")
            return np.column_stack([rx, ry, rz])
        raise ValueError("unknown operator " + repr(name))

    def _call(self, name: str, args: list):
        expect = _FUNCS[name]
        if len(args) != expect:
            raise ValueError(name + " takes " + str(expect) + " argument(s)")
        if name == "abs":
            return np.abs(args[0])
        if name == "sqrt":
            with np.errstate(invalid="ignore"):
                return np.sqrt(args[0])
        if name == "min":
            return np.minimum(args[0], args[1])
        if name == "max":
            return np.maximum(args[0], args[1])
        if name == "mag":
            return args[0]
        if name == "ifgt":
            return np.where(args[0] > args[1], 1.0, 0.0)
        if name == "ifet":
            return np.where(args[0] >= args[1], 1.0, 0.0)
        if name == "ifeq":
            return np.where(args[0] == args[1], 1.0, 0.0)
        raise ValueError("unknown function " + repr(name))


# public API

def evaluate_expression(expr: str, variables: dict, n: int,
                         ff=None) -> np.ndarray:
    """Evaluate *expr* over arrays in *variables* (each (n,) or (n,3))."""
    toks = tokenize(expr)
    return _Eval(toks, variables, n, ff=ff).evaluate()


def register_variable(ff, name: str, expr: str,
                     variables: Optional[dict] = None) -> VarInfo:
    """Register a derived variable on a FieldFile (P1.1).

    The name must be a valid identifier and must not collide with an
    existing variable.  The expression is evaluated over the file's own
    variables (vector bases resolve to their X/Y/Z components).  Returns
    the new VarInfo and stores it on the file.
    """
    if not name or not name.isidentifier():
        raise ValueError("invalid variable name: " + repr(name))
    if name in ff.variables:
        raise ValueError("variable already exists: " + repr(name))
    if variables is None:
        variables = _resolved_vars(ff)
    n = _array_len(ff, variables)
    arr = evaluate_expression(expr, variables, n, ff=ff)
    arr = np.asarray(arr, dtype=np.float64)
    if arr.ndim == 1:
        kind = FIELD_KIND_SCALAR
    elif arr.ndim == 2 and arr.shape[1] == 3:
        kind = FIELD_KIND_VECTOR
    else:
        raise ValueError("expression must yield a scalar or a (n,3) vector")
    location = _source_location(ff, variables, expr)
    vi = VarInfo(name=name, kind=kind, location=location, array=arr)
    ff.variables[name] = vi
    return vi


def _resolved_vars(ff) -> dict:
    """All file variables as arrays; vector bases gain a (n,3) tuple."""
    out: dict = {}
    bases: dict = {}
    for name, vi in ff.variables.items():
        if vi.array is None or vi.array.size == 0:
            continue
        a = np.asarray(vi.array, dtype=np.float64)
        if name.endswith(("X", "Y", "Z")) and vi.kind == FIELD_KIND_VECTOR:
            bases.setdefault(name[:-1], {})[name[-1]] = a
        else:
            out[name] = a
    for base, comps in bases.items():
        if len(comps) == 3:
            out[base] = np.column_stack([comps[c] for c in "XYZ" if c in comps])
    return out


def _array_len(ff, variables: dict) -> int:
    for a in variables.values():
        if a is not None and getattr(a, "size", 0):
            return int(a.shape[0])
    if ff.kind == "fld" and ff.n_vertices:
        return ff.n_vertices
    return max(1, ff.n_cells)


def _source_location(ff, variables: dict, expr: str) -> str:
    """Inherit the location ('cell' | 'node') from the first used var."""
    for name, vi in ff.variables.items():
        if vi.array is not None and name in expr:
            return vi.location
    if ff.kind == "fld":
        return "node"
    return "cell"

def _axis_difference(ff, name: str, axis: str):
    """Central first difference of a node field along *axis* (B1).

    Projects nodes onto the plane perpendicular to *axis* and uses a
    cKDTree there to find, per node, the nearest same-row neighbour on
    each side along *axis* (structured-node-field friendly), then
    computes (v[+] - v[-]) / (x[+] - x[-]).
    """
    if ff.vertices is None or ff.kind == "fph":
        raise ValueError(axis + " requires a node-centred (FLD/CGNS) field")
    a = ff.variable_array(name)
    if a is None or np.asarray(a).ndim != 1:
        raise ValueError("unknown scalar variable " + repr(name))
    a = np.asarray(a, dtype=np.float64)
    verts = np.asarray(ff.vertices, dtype=np.float64)
    try:
        from scipy.spatial import cKDTree
    except ImportError:
        raise ValueError("scipy required for delx/dely/delz")
    ax = {"X": 0, "Y": 1, "Z": 2}[axis]
    other = [c for c in range(3) if c != ax]
    tree2 = cKDTree(verts[:, other])
    k = min(64, len(verts))
    _d2, nbr = tree2.query(verts[:, other], k=k)
    if len(verts) == 1:
        nbr = nbr.reshape(1, -1)
    out = np.zeros(len(a), dtype=np.float64)
    for i in range(len(a)):
        idx = np.asarray(nbr[i]).astype(np.int64)
        idx = idx[idx != i]
        if idx.size == 0:
            continue
        da = verts[idx, ax] - verts[i, ax]
        pos = idx[da > 0]
        neg = idx[da < 0]
        if pos.size == 0 or neg.size == 0:
            continue
        p = pos[np.argmin(verts[pos, ax] - verts[i, ax])]
        m = neg[np.argmax(verts[neg, ax] - verts[i, ax])]
        h = verts[p, ax] - verts[m, ax]
        if abs(h) > 1e-12:
            out[i] = (a[p] - a[m]) / h
    return out