
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
        # struct*/void*/func* -> opaque address (handle analysis resolves later)
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

    for c in tu.cursor.walk_preorder():
        if c.kind != cindex.CursorKind.FUNCTION_DECL:
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