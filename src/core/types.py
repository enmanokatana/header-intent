from __future__ import annotations

import ctypes

from ..spec.vocab import Role, Intent
from ..spec.schema import ParamSpec, FunctionSpec, ctype_by_name

CTYPE_TO_PY = {
    ctypes.c_int: int, ctypes.c_uint: int, ctypes.c_long: int, ctypes.c_ulong: int,
    ctypes.c_longlong: int, ctypes.c_ulonglong: int, ctypes.c_short: int,
    ctypes.c_ushort: int, ctypes.c_byte: int, ctypes.c_ubyte: int,
    ctypes.c_float: float, ctypes.c_double: float, ctypes.c_longdouble: float,
    ctypes.c_bool: bool, ctypes.c_char_p: str, ctypes.c_void_p: int,
    ctypes.c_size_t: int, ctypes.c_ssize_t: int,
    ctypes.c_wchar: str, ctypes.c_wchar_p: str,
}


def py_type_of(ctype_name: str) -> type:
    return CTYPE_TO_PY.get(ctype_by_name(ctype_name), int)


def py_restype(fn: FunctionSpec) -> type:
    if fn.restype is None:
        return type(None)
    return py_type_of(fn.restype)


def arg_ctype(p: ParamSpec):
    """The ctypes type to BIND for a parameter."""
    if p.role is Role.HANDLE:
        return ctypes.c_void_p
    base = ctype_by_name(p.ctype)
    if p.role is Role.ARRAY or p.by_ref:
        return ctypes.POINTER(base)
    return base


def to_c(value, ctype):
    if ctype is ctypes.c_char_p and isinstance(value, str):
        return value.encode()
    if ctype is ctypes.c_bool:
        return bool(value)
    if ctype in (ctypes.c_float, ctypes.c_double, ctypes.c_longdouble):
        return float(value)
    return value


def from_c(value, ctype):
    if ctype is ctypes.c_char_p and isinstance(value, (bytes, bytearray)):
        return value.decode(errors="replace")
    if isinstance(value, (bytes, bytearray)):
        return value.decode(errors="replace")
    return value