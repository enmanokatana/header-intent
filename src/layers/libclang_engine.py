"""
reads real .c/.h directly (resolves #include and
system headers), so NO cpp/fake-header preprocessing is needed.

Provides the same outputs as the pycparser engine:
  * handle_records(path)      -> {fn: HandleRecord}   (robust: types + free() calls)
  * function_accesses(path)   -> {fn: FunctionAccesses} (def-use for in/out/inout)

Only functions DEFINED in the given file are analyzed (not included-header
declarations).
"""
from __future__ import annotations

import os

try:
    from clang import cindex
    _HAVE = True
except Exception:                     
    cindex = None
    _HAVE = False

from .l2_handles import HandleRecord
from .l2_static import FunctionAccesses


def _require():
    if not _HAVE:
        raise ImportError("libclang bindings not available; `pip install libclang`")


def _struct_pointee_name(t):
    """If t is a pointer to a struct/typedef-to-struct, return the type name."""
    if t.kind != cindex.TypeKind.POINTER:
        return None
    pointee = t.get_pointee()
    canon = pointee.get_canonical()
    if canon.kind == cindex.TypeKind.RECORD:
        decl = pointee.get_declaration()
        name = (decl.spelling or canon.spelling or "")
        name = name.replace("struct ", "").replace("const ", "").strip()
        return name or None
    return None


_ARITH = None
def _is_scalar_pointer(t) -> bool:
    """True if t is a pointer to an arithmetic scalar (int/double/...), not char."""
    global _ARITH
    if _ARITH is None:
        _ARITH = {cindex.TypeKind.INT, cindex.TypeKind.UINT, cindex.TypeKind.LONG,
                  cindex.TypeKind.ULONG, cindex.TypeKind.LONGLONG, cindex.TypeKind.ULONGLONG,
                  cindex.TypeKind.SHORT, cindex.TypeKind.USHORT,
                  cindex.TypeKind.FLOAT, cindex.TypeKind.DOUBLE, cindex.TypeKind.BOOL}
    if t.kind != cindex.TypeKind.POINTER:
        return False
    return t.get_pointee().get_canonical().kind in _ARITH


def _decl_ref_name(node, params):
    """Unwrap casts/parens to a DECL_REF_EXPR; return its name if in params."""
    n = node
    while n is not None:
        if n.kind == cindex.CursorKind.DECL_REF_EXPR:
            return n.spelling if n.spelling in params else None
        kids = list(n.get_children())
        n = kids[0] if len(kids) == 1 else None
    return None


def _root_lvalue_param(lhs, params):
    """If lhs is *p / p[i] / p->f with p a param, return p's name."""
    if lhs.kind == cindex.CursorKind.UNARY_OPERATOR and _is_deref(lhs):
        kids = list(lhs.get_children())
        return _decl_ref_name(kids[0], params) if kids else None
    if lhs.kind == cindex.CursorKind.ARRAY_SUBSCRIPT_EXPR:
        kids = list(lhs.get_children())
        return _decl_ref_name(kids[0], params) if kids else None
    if lhs.kind == cindex.CursorKind.MEMBER_REF_EXPR:
        kids = list(lhs.get_children())
        return _decl_ref_name(kids[0], params) if kids else None
    return None


def _is_deref(unary):
    toks = [t.spelling for t in unary.get_tokens()]
    return bool(toks) and toks[0] == "*"


def _binop_is_assign(node) -> bool:
    kids = list(node.get_children())
    if len(kids) < 2:
        return False
    lhs_tok = list(kids[0].get_tokens())
    all_tok = list(node.get_tokens())
    if len(lhs_tok) < len(all_tok):
        return all_tok[len(lhs_tok)].spelling == "="
    return False


def _collect_events(node, params, events):
    k = node.kind
    if k == cindex.CursorKind.BINARY_OPERATOR and _binop_is_assign(node):
        kids = list(node.get_children())
        _collect_events(kids[1], params, events)               # RHS reads first
        tgt = _root_lvalue_param(kids[0], params)
        if tgt:
            events.append((tgt, "write"))
        else:
            _collect_events(kids[0], params, events)
        return
    if k == cindex.CursorKind.COMPOUND_ASSIGNMENT_OPERATOR:
        kids = list(node.get_children())
        _collect_events(kids[1], params, events)
        tgt = _root_lvalue_param(kids[0], params)
        if tgt:
            events.append((tgt, "read"))
            events.append((tgt, "write"))
        else:
            _collect_events(kids[0], params, events)
        return
    if k == cindex.CursorKind.UNARY_OPERATOR and _is_deref(node):
        kids = list(node.get_children())
        nm = _decl_ref_name(kids[0], params) if kids else None
        if nm:
            events.append((nm, "read"))
            return
    if k == cindex.CursorKind.ARRAY_SUBSCRIPT_EXPR:
        kids = list(node.get_children())
        nm = _decl_ref_name(kids[0], params) if kids else None
        if nm:
            events.append((nm, "read"))
            for extra in kids[1:]:
                _collect_events(extra, params, events)
            return
    if k == cindex.CursorKind.MEMBER_REF_EXPR:
        kids = list(node.get_children())
        nm = _decl_ref_name(kids[0], params) if kids else None
        if nm:
            events.append((nm, "read"))
            return
    for ch in node.get_children():
        _collect_events(ch, params, events)


class LibclangEngine:
    def __init__(self, clang_args=None):
        self.args = list(clang_args or [])

    def _parse(self, path, clang_args=None):
        _require()
        idx = cindex.Index.create()
        return idx.parse(path, args=list(clang_args or self.args))

    def _defined_functions(self, tu, path):
        target = os.path.abspath(path)
        for c in tu.cursor.walk_preorder():
            if c.kind == cindex.CursorKind.FUNCTION_DECL and c.is_definition():
                f = c.location.file
                if f and os.path.abspath(f.name) == target:
                    yield c

    def handle_records(self, path, clang_args=None) -> dict[str, HandleRecord]:
        tu = self._parse(path, clang_args)
        recs: dict[str, HandleRecord] = {}
        for c in self._defined_functions(tu, path):
            name = c.spelling
            ret = _struct_pointee_name(c.result_type)
            struct_params = {}
            for a in c.get_arguments():
                tn = _struct_pointee_name(a.type)
                if tn:
                    struct_params[a.spelling] = tn
            freed = set()
            for d in c.walk_preorder():
                if d.kind == cindex.CursorKind.CALL_EXPR and d.spelling in _FREE:
                    for arg in d.get_arguments():
                        for r in arg.walk_preorder():
                            if r.kind == cindex.CursorKind.DECL_REF_EXPR and r.spelling in struct_params:
                                freed.add(r.spelling)
            recs[name] = HandleRecord(name, ret, struct_params, freed)
        return recs

    def function_accesses(self, path, clang_args=None) -> dict[str, FunctionAccesses]:
        tu = self._parse(path, clang_args)
        out: dict[str, FunctionAccesses] = {}
        for c in self._defined_functions(tu, path):
            params = [a.spelling for a in c.get_arguments() if _is_scalar_pointer(a.type)]
            if not params:
                continue
            events: list[tuple[str, str]] = []
            for ch in c.get_children():
                if ch.kind == cindex.CursorKind.COMPOUND_STMT:
                    _collect_events(ch, set(params), events)
            out[c.spelling] = FunctionAccesses(c.spelling, params, events, set())
        return out


_FREE = {"free"}


def handle_records_files(paths, clang_args=None) -> dict[str, HandleRecord]:
    """Merge handle records across several source files (e.g. lib + shim)."""
    eng = LibclangEngine(clang_args)
    merged: dict[str, HandleRecord] = {}
    for p in paths:
        merged.update(eng.handle_records(p, clang_args))
    return merged
