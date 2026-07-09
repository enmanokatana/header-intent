"""
Build callable tools from a capability spec + a loaded ctypes library.

Pattern handlers keyed on (role, intent). The server used to classify inline;
now it just reads the spec and routes. Returns ToolDescriptors that a thin
FastMCP wrapper registers -- but they're plain callables, so they're testable
without the mcp package.

Phase 1 handles: scalar in, string in, scalar out, scalar inout. (handle/array
come in later phases.)
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
    """The ctypes type to bind for this param (POINTER whenever it's by_ref)."""
    base = ctype_by_name(p.ctype)
    return ctypes.POINTER(base) if p.by_ref else base


def _check_safe(fn: FunctionSpec) -> None:
    for p in fn.params:
        if p.role is Role.HANDLE:            # handled by the lifecycle builder
            continue
        if p.role is Role.OPAQUE or (
            not p.intent.verified and p.intent.confidence < CONFIDENCE_THRESHOLD
        ):
            raise SpecViolation(
                f"{fn.name}: param {p.name!r} is unhandled or low-confidence "
                f"(role={p.role.value}, conf={p.intent.confidence}, verified={p.intent.verified}); "
                f"refuse to auto-generate (fail-safe)."
            )


def build_handle_tool(lib, fn: FunctionSpec, handles) -> ToolDescriptor:
    """Generate a create/use/destroy tool from lifecycle facts. Opaque handle
    pointers are bound as c_void_p; the real pointer lives in `handles`, the
    client sees an integer id."""
    cfn = getattr(lib, fn.name)
    argtypes = []
    for p in fn.params:
        argtypes.append(ctypes.c_void_p if p.role is Role.HANDLE else _arg_ctype(p))
    cfn.argtypes = argtypes
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)
    if fn.lifecycle == "creates":
        cfn.restype = ctypes.c_void_p        # returned handle is an opaque address

    non_handle = [p for p in fn.params if p.role is not Role.HANDLE
                  and p.intent.value is not Intent.OUT]
    schema = [(p.name, CTYPE_TO_PY.get(ctype_by_name(p.ctype), int)) for p in non_handle]
    if fn.lifecycle in ("uses", "destroys"):
        schema = [("handle", int)] + schema

    def invoke(**kwargs):
        call_args = []
        for p in fn.params:
            if p.role is Role.HANDLE:
                call_args.append(handles.get(kwargs["handle"]))
            else:
                base = ctype_by_name(p.ctype)
                call_args.append(_to_c(kwargs[p.name], base))
        ret = cfn(*call_args)
        if fn.lifecycle == "creates":
            if not ret:
                return {"handle": None}
            return {"handle": handles.put(ret)}
        if fn.lifecycle == "destroys":
            handles.pop(kwargs["handle"])
            return {"freed": kwargs["handle"], "live_handles": len(handles)}
        rtype = None if fn.restype is None else ctype_by_name(fn.restype)
        return _from_c(ret, rtype)

    doc = f"{fn.name}({', '.join(n for n, _ in schema)}) [handle:{fn.lifecycle} {fn.handle_type}]"
    return ToolDescriptor(fn.name, doc, schema, fn.lifecycle in ("creates", "destroys"), invoke)


def build_tool(lib, fn: FunctionSpec, handles=None) -> ToolDescriptor:
    if fn.lifecycle in ("creates", "uses", "destroys"):
        if handles is None:
            raise SpecViolation(f"{fn.name}: lifecycle tool needs a handle table")
        return build_handle_tool(lib, fn, handles)

    if any(p.role is Role.ARRAY for p in fn.params):
        return build_array_tool(lib, fn)

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
            if p.by_ref:
                if p.intent.value is Intent.OUT:                 # allocate, return
                    cell = base()
                    outs[p.name] = cell
                elif p.intent.value is Intent.INOUT:             # seed, return
                    cell = base(_to_c(kwargs[p.name], base))
                    outs[p.name] = cell
                else:                                            # IN by reference: seed, don't return
                    cell = base(_to_c(kwargs[p.name], base))
                call_args.append(ctypes.byref(cell))
            else:
                call_args.append(_to_c(kwargs[p.name], base))    # by value
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


def build_array_tool(lib, fn: FunctionSpec) -> ToolDescriptor:
    """Function with an input array + companion length. The array param takes a
    JSON list; the length param is hidden and filled from len(list). Other params
    pass through as scalars/strings. (Input arrays only; out-arrays are later.)"""
    # names of length params (hidden) and array->length map
    length_names = {p.dimension for p in fn.params if p.role is Role.ARRAY}
    arrays = {p.name: p for p in fn.params if p.role is Role.ARRAY}

    for p in fn.params:                     # fail-safe: unresolved pointer stays refused
        if p.role is Role.OPAQUE:
            raise SpecViolation(f"{fn.name}: opaque param {p.name!r} alongside array; refusing.")

    argtypes = []
    for p in fn.params:
        if p.role is Role.ARRAY:
            argtypes.append(ctypes.POINTER(ctype_by_name(p.ctype)))
        elif p.by_ref:
            argtypes.append(ctypes.POINTER(ctype_by_name(p.ctype)))
        else:
            argtypes.append(ctype_by_name(p.ctype))
    cfn = getattr(lib, fn.name)
    cfn.argtypes = argtypes
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)

    visible = [p for p in fn.params
               if p.name not in length_names and p.intent.value is not Intent.OUT]
    schema = []
    for p in visible:
        if p.role is Role.ARRAY:
            schema.append((p.name, list))
        else:
            schema.append((p.name, CTYPE_TO_PY.get(ctype_by_name(p.ctype), int)))

    def invoke(**kwargs):
        # build C arrays first so lengths are known
        built = {}
        for name, p in arrays.items():
            elem = ctype_by_name(p.ctype)
            items = kwargs[name]
            built[name] = (elem * len(items))(*items)
        call_args = []
        for p in fn.params:
            if p.role is Role.ARRAY:
                call_args.append(built[p.name])
            elif p.role is Role.LENGTH_OF:
                call_args.append(len(kwargs[p.dimension]))     # auto length
            elif p.by_ref:
                base = ctype_by_name(p.ctype)
                call_args.append(ctypes.byref(base(_to_c(kwargs[p.name], base))))
            else:
                call_args.append(_to_c(kwargs[p.name], ctype_by_name(p.ctype)))
        ret = cfn(*call_args)
        rtype = None if fn.restype is None else ctype_by_name(fn.restype)
        return _from_c(ret, rtype)

    doc = f"{fn.name}({', '.join(n for n, _ in schema)}) [array; length auto-filled]"
    return ToolDescriptor(fn.name, doc, schema, False, invoke)


def build_tools(lib, spec: LibrarySpec, handles=None) -> list[ToolDescriptor]:
    if handles is None:
        from .handles import HandleTable
        handles = HandleTable()
    return [build_tool(lib, fn, handles) for fn in spec.functions.values()]