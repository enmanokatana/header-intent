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
except Exception:
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
    kind_map = _build_kind_map()

    canon = t.get_canonical()
    kind = canon.kind
    k = cindex.TypeKind

    if kind in kind_map:
        return kind_map[kind]

    if kind == k.POINTER:
        pointee_q = canon.get_pointee()
        pointee = pointee_q.get_canonical()
        if pointee.kind in (k.CHAR_S, k.CHAR_U, k.SCHAR, k.UCHAR):
            if is_param and not pointee_q.is_const_qualified():
                return ctypes.c_void_p
            return ctypes.c_char_p
        if pointee.kind in kind_map and kind_map[pointee.kind] is not None:
            return ctypes.POINTER(kind_map[pointee.kind])
        return ctypes.c_void_p

    if kind == k.ENUM:
        return ctypes.c_int

    if kind == k.CONSTANTARRAY:
        elem = canon.get_array_element_type().get_canonical()
        if elem.kind in (k.CHAR_S, k.CHAR_U):
            return ctypes.c_char_p
        if elem.kind in kind_map and kind_map[elem.kind] is not None:
            return ctypes.POINTER(kind_map[elem.kind])
        return ctypes.c_void_p

    raise UnmappableType(f"{t.spelling} (canonical kind {kind})")


def _out_handle_candidate(arg_type) -> str | None:
    """T** where T is a struct/typedef-to-struct -- CANDIDATE for the
    sqlite3_open(path, &db) idiom (a NEW handle written through an out-param).
    This is a candidate only: L2 must confirm the function actually WRITES an
    allocated value through it before we trust it (see layers/l2_out_handles.py).
    Until confirmed it stays OPAQUE -> refused, the same fail-safe as any other
    unresolved double pointer.
    """
    canon = arg_type.get_canonical()
    if canon.kind != cindex.TypeKind.POINTER:
        return None
    inner = canon.get_pointee().get_canonical()
    if inner.kind != cindex.TypeKind.POINTER:
        return None
    struct_t = inner.get_pointee()
    struct_canon = struct_t.get_canonical()
    if struct_canon.kind != cindex.TypeKind.RECORD:
        return None
    decl = struct_t.get_declaration()
    name = (decl.spelling or struct_canon.spelling or "").replace("struct ", "").strip()
    return name or None


def _pointer_is_out(arg_type) -> bool:
    """const-based pre-classification: non-const scalar pointer -> candidate out."""
    canon = arg_type.get_canonical()
    if canon.kind != cindex.TypeKind.POINTER:
        return False
    pointee = canon.get_pointee()
    k = cindex.TypeKind
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

    args = builtin_include_args() + list(clang_args or [])
    idx = cindex.Index.create()
    tu = idx.parse(header_path, args=args)
    check_diagnostics(tu, header_path, strict=strict)

    signatures: dict = {}
    skipped: list[str] = []

    _SYS_ROOTS = ("/usr/include", "/usr/lib", "/usr/local/include",
                  "/usr/lib/llvm", "/usr/lib/gcc")
    _target_real = os.path.realpath(os.path.abspath(header_path))
    _target_dir = os.path.dirname(_target_real)
    _stem = os.path.splitext(os.path.basename(_target_real))[0]
    _umbrella_dir = os.path.join(_target_dir, _stem)

    def _in_library(cursor) -> bool:
        loc = cursor.location
        f = loc.file
        if f is None:
            return False
        path = os.path.realpath(os.path.abspath(f.name))
        if (path == _target_real
                or path.startswith(_umbrella_dir + os.sep)
                or (path.startswith(_target_dir + os.sep)
                    and _target_dir not in ("/usr/include", "/usr/local/include"))):
            return True
        try:
            if loc.is_in_system_header:
                return False
        except AttributeError:
            pass
        if any(path.startswith(os.path.realpath(r)) for r in _SYS_ROOTS):
            return False
        return path.startswith(_target_dir + os.sep)

    for c in tu.cursor.walk_preorder():
        if c.kind != cindex.CursorKind.FUNCTION_DECL:
            continue
        if not _in_library(c):
            continue
        name = c.spelling
        if name in signatures:
            continue
        try:
            argnames, argtypes, pointers, out_handle_candidates = [], [], {}, {}
            for i, a in enumerate(c.get_arguments()):
                an = a.spelling or f"a{i}"
                at = _map_type(a.type, is_param=True)
                argnames.append(an)
                argtypes.append(at)
                if _pointer_is_out(a.type):
                    pointers[an] = "out"
                oh = _out_handle_candidate(a.type)
                if oh:
                    out_handle_candidates[an] = oh
            restype = _map_type(c.result_type, is_param=False)
            signatures[name] = {
                "argnames": argnames,
                "argtypes": argtypes,
                "restype": restype,
                "pointers": pointers,
                "out_handle_candidates": out_handle_candidates,
            }
        except UnmappableType as e:
            skipped.append(f"{name}: unmappable type {e}")
        except Exception as e:
            skipped.append(f"{name}: {type(e).__name__}: {e}")

    return signatures, skipped