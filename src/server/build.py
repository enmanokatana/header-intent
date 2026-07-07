"""
here we'll be building callable tools from a capability spec + a loaded ctypes library.


Pattern handlers keyed on (role, intent). The server used to classify inline;
now it just reads the spec and routes. Returns ToolDescriptors that a thin
FastMCP wrapper registers but they're plain callables, so they're testable
without the mcp package.

handles now : scalar in, string in, scalar out, scalar inout. (handle/array we'll do it later)
"""
from __future__ import annotations

import ctypes
import math
from dataclasses import dataclass, field
from typing import Any, Callable

from ..spec.vocab import Intent, Role
from ..spec.schema import LibrarySpec, FunctionSpec, ParamSpec, ctype_by_name

CTYPE_TO_PY = {
    ctypes.c_int: int, ctypes.c_uint: int, ctypes.c_short: int,
    ctypes.c_long: int, ctypes.c_ulong: int, ctypes.c_longlong: int,
    ctypes.c_float: float, ctypes.c_double: float,
    ctypes.c_bool: bool, ctypes.c_char_p: str, ctypes.c_char: str,
}

# Confidence below which an unverified fact is treated as unsafe (fail-safe).
CONFIDENCE_THRESHOLD = 0.5


def _to_c(value, ctype):
    if ctype is ctypes.c_char_p and isinstance(value, str):
        return value.encode("utf-8")
    if ctype is ctypes.c_char and isinstance(value, str):
        return value.encode("utf-8")[:1] or b"\x00"
    return value

def _from_c(value, ctype):
    if ctype in (ctypes.c_char_p, ctypes.c_char) and isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if ctype is ctypes.c_bool:
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@dataclass
class ToolDescriptor:
    name: str
    doc: str
    params: list[tuple[str, type]]     # visible (name, python_type) for the schema
    returns_dict: bool                 # True if it returns {result, out...}
    invoke: Callable[..., Any]


class SpecViolation(Exception):
    pass


def _arg_ctype(p: ParamSpec):
    """The ctypes type to bind for this param (POINTER for out/inout)."""
    base = ctype_by_name(p.ctype)
    if p.intent.value in (Intent.OUT, Intent.INOUT):
        return ctypes.POINTER(base)
    return base


def _check_safe(fn: FunctionSpec) -> None:
    for p in fn.params:
        if p.role is Role.OPAQUE or (
            not p.intent.verified and p.intent.confidence < CONFIDENCE_THRESHOLD
        ):
            raise SpecViolation(
                f"{fn.name}: param {p.name!r} is unhandled or low-confidence "
                f"(role={p.role.value}, conf={p.intent.confidence}, verified={p.intent.verified}); "
                f"refuse to auto-generate (fail-safe)."
            )


def build_tool(lib, fn: FunctionSpec) -> ToolDescriptor:
    _check_safe(fn)

    argtypes = [_arg_ctype(p) for p in fn.params]
    cfn = getattr(lib, fn.name)
    cfn.argtypes = argtypes
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)

    has_out = any(p.intent.value in (Intent.OUT, Intent.INOUT) for p in fn.params)
    visible = [p for p in fn.params if p.intent.value is not Intent.OUT]  # inout stays visible

    def py_for(p: ParamSpec):
        base = ctype_by_name(p.ctype)
        return CTYPE_TO_PY.get(base, int)

    param_schema = [(p.name, py_for(p)) for p in visible]

    def invoke(**kwargs):
        call_args, outs = [], {}
        for p in fn.params:
            base = ctype_by_name(p.ctype)
            if p.intent.value is Intent.OUT:
                cell = base()
                outs[p.name] = cell
                call_args.append(ctypes.byref(cell))
            elif p.intent.value is Intent.INOUT:
                cell = base(_to_c(kwargs[p.name], base))
                outs[p.name] = cell
                call_args.append(ctypes.byref(cell))
            else:
                call_args.append(_to_c(kwargs[p.name], base))
        ret = cfn(*call_args)
        rtype = None if fn.restype is None else ctype_by_name(fn.restype)
        if not has_out:
            return _from_c(ret, rtype)
        result = {}
        if rtype is not None:
            result["result"] = _from_c(ret, rtype)
        for n, cell in outs.items():
            result[n] = _from_c(cell.value, type(cell))
        return result

    doc = f"{fn.name}({', '.join(n for n, _ in param_schema)}) [spec-driven]"
    return ToolDescriptor(fn.name, doc, param_schema, has_out, invoke)


def build_tools(lib, spec: LibrarySpec) -> list[ToolDescriptor]:
    return [build_tool(lib, fn) for fn in spec.functions.values()]