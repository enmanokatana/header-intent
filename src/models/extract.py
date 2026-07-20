"""
L0 -- Ferrule's own libclang signature extractor. Self-contained: no cToMcp.

Turns a C header into the signatures dict the rest of Ferrule consumes:
    { fname: {"argnames": [...], "argtypes": [ctypes...],
              "restype": ctype|None, "pointers": {argname: "out"}} }

Design principles that fix the problems real libraries surface:
  * CANONICAL typedef resolution -- every type is resolved via get_canonical()
    first, so `typedef int cJSON_bool` maps to c_int automatically (no per-type
    patches; also handles sqlite's sqlite3_int64 etc.).
  * SKIP, don't crash -- a function with a type we can't map is dropped with a
    note, never aborting the whole header.
  * const-based pointer pre-classification -- same signal L1 uses, produced here
    so L1's `pointers` dict is populated.

Pointer intent beyond const-ness is NOT decided here (that's L1/L2); struct
pointers degrade to c_void_p (opaque handles, resolved later by handle analysis).
"""
from __future__ import annotations

import ctypes

try:
    from clang import cindex
    _HAVE = True
except Exception:                      # pragma: no cover
    cindex = None
    _HAVE = False


class UnmappableType(Exception):
    pass


def _build_kind_map():
    k = cindex.TypeKind
    return {
        k.VOID: None,
        k.BOOL: ctypes.c_bool,
        k.CHAR_U: ctypes.c_char, k.UCHAR: ctypes.c_ubyte,
        k.CHAR_S: ctypes.c_char, k.SCHAR: ctypes.c_byte,
        k.USHORT: ctypes.c_ushort, k.SHORT: ctypes.c_short,
        k.UINT: ctypes.c_uint, k.INT: ctypes.c_int,
        k.ULONG: ctypes.c_ulong, k.LONG: ctypes.c_long,
        k.ULONGLONG: ctypes.c_ulonglong, k.LONGLONG: ctypes.c_longlong,
        k.FLOAT: ctypes.c_float, k.DOUBLE: ctypes.c_double,
        k.LONGDOUBLE: ctypes.c_longdouble,
    }


def _map_type(t, is_param: bool = True):
    """ctypes type for a clang Type. Resolves typedefs canonically. Raises
    UnmappableType for anything we can't safely bind.

    SAFETY (learned from cJSON): a NON-CONST `char *` PARAMETER is a writable
    output buffer (cJSON_PrintPreallocated, cJSON_Minify), not an input string.
    Binding it as c_char_p would hand C an immutable Python bytes object to
    write into -> heap corruption. So it maps to c_void_p, which L1 classifies
    OPAQUE and the fail-safe guard refuses until out-buffer support exists.
    Only `const char *` params are true input strings.
    """
    kind_map = _build_kind_map()            # built per call: no shared global state

    canon = t.get_canonical()
    kind = canon.kind
    k = cindex.TypeKind

    if kind in kind_map:
        return kind_map[kind]

    if kind == k.POINTER:
        pointee_q = canon.get_pointee()             # keeps const qualification
        pointee = pointee_q.get_canonical()
        if pointee.kind in (k.CHAR_S, k.CHAR_U, k.SCHAR, k.UCHAR):
            if is_param and not pointee_q.is_const_qualified():
                return ctypes.c_void_p              # writable buffer -> OPAQUE -> refused
            return ctypes.c_char_p                  # const char* (or a return) -> string
        if pointee.kind in kind_map and kind_map[pointee.kind] is not None:
            return ctypes.POINTER(kind_map[pointee.kind])
        # struct*/void*/func* -> opaque address (handle analysis resolves later)
        return ctypes.c_void_p

    if kind == k.ENUM:
        return ctypes.c_int                 # C enums are int-compatible

    if kind == k.CONSTANTARRAY:             # arrays decay to pointers at call sites
        elem = canon.get_array_element_type().get_canonical()
        if elem.kind in (k.CHAR_S, k.CHAR_U):
            return ctypes.c_char_p
        if elem.kind in kind_map and kind_map[elem.kind] is not None:
            return ctypes.POINTER(kind_map[elem.kind])
        return ctypes.c_void_p

    raise UnmappableType(f"{t.spelling} (canonical kind {kind})")


def _pointer_is_out(arg_type) -> bool:
    """const-based pre-classification: non-const scalar pointer -> candidate out."""
    canon = arg_type.get_canonical()
    if canon.kind != cindex.TypeKind.POINTER:
        return False
    pointee = canon.get_pointee()
    k = cindex.TypeKind
    # char* and struct*/void* are not scalar-out
    pc = pointee.get_canonical().kind
    if pc in (k.CHAR_S, k.CHAR_U, k.SCHAR, k.UCHAR, k.RECORD, k.VOID, k.POINTER,
              k.FUNCTIONPROTO, k.FUNCTIONNOPROTO):
        return False
    return not pointee.is_const_qualified()


def extract_signatures(header_path: str, clang_args=None, strict: bool = True):
    """Parse a header -> (signatures, skipped notes). Self-contained libclang."""
    if not _HAVE:
        raise ImportError("libclang bindings not available; `pip install libclang`")

    import os
    if not os.path.exists(header_path):
        raise FileNotFoundError(f"header not found: {header_path}")

    from ..layers.libclang_engine import builtin_include_args, check_diagnostics

    args = builtin_include_args() + list(clang_args or [])   # stddef.h etc.
    idx = cindex.Index.create()
    tu = idx.parse(header_path, args=args)
    check_diagnostics(tu, header_path, strict=strict)         # never trust a truncated AST

    signatures: dict = {}
    skipped: list[str] = []

    for c in tu.cursor.walk_preorder():
        if c.kind != cindex.CursorKind.FUNCTION_DECL:
            continue
        # declarations are enough for signatures; take each function once
        name = c.spelling
        if name in signatures:
            continue
        try:
            argnames, argtypes, pointers = [], [], {}
            for i, a in enumerate(c.get_arguments()):
                an = a.spelling or f"a{i}"
                at = _map_type(a.type, is_param=True)
                argnames.append(an)
                argtypes.append(at)
                if _pointer_is_out(a.type):
                    pointers[an] = "out"
            restype = _map_type(c.result_type, is_param=False)
            signatures[name] = {
                "argnames": argnames,
                "argtypes": argtypes,
                "restype": restype,
                "pointers": pointers,
            }
        except UnmappableType as e:
            skipped.append(f"{name}: unmappable type {e}")
        except Exception as e:                # never let one function abort the header
            skipped.append(f"{name}: {type(e).__name__}: {e}")

    return signatures, skipped