"""
Libclang-backed L2 engine -- reads real .c/.h directly (resolves #include and
system headers), so NO cpp/fake-header preprocessing is needed.

Provides the same outputs as the pycparser engine:
  * handle_records(path)      -> {fn: HandleRecord}   (robust: types + free() calls)
  * function_accesses(path)   -> {fn: FunctionAccesses} (def-use for in/out/inout)

Only functions DEFINED in the given file are analyzed (not included-header
declarations). Requires the `libclang` python bindings.
"""
from __future__ import annotations

import os

try:
    from clang import cindex
    _HAVE = True
except Exception:                      # pragma: no cover
    cindex = None
    _HAVE = False

from .l2_handles import HandleRecord, _is_dealloc_name
from .l2_ownership import OwnRecord, _is_alloc_name
from .l2_static import FunctionAccesses


import glob
import subprocess


def builtin_include_args() -> list:
    """clang's OWN builtin headers (stddef.h, stdarg.h, ...).

    Without these libclang emits a FATAL "'stddef.h' file not found" and then
    ERROR-RECOVERS BY TRUNCATING FUNCTION BODIES -- silently. That is exactly what
    corrupted cJSON: `size_t buffer_length;` inside cJSON_ParseWithOpts made clang
    drop the rest of the body, so the `return cJSON_ParseWithLengthOpts(...)`
    statement never appeared in the AST and ownership came out 'unknown'.
    """
    # 1. ask clang directly
    for exe in ("clang", "clang-19", "clang-18", "clang-17", "clang-16", "clang-15"):
        try:
            out = subprocess.run([exe, "-print-resource-dir"], capture_output=True,
                                 text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                inc = os.path.join(out.stdout.strip(), "include")
                if os.path.isdir(inc):
                    return ["-I" + inc]
        except Exception:
            continue
    # 2. glob the usual locations
    for pat in ("/usr/lib/llvm-*/lib/clang/*/include",
                "/usr/lib/clang/*/include",
                "/usr/local/lib/clang/*/include"):
        hits = sorted(glob.glob(pat))
        if hits:
            return ["-I" + hits[-1]]
    # 3. headers bundled with the `libclang` pip wheel, if present
    try:
        import clang as _c
        cand = os.path.join(os.path.dirname(_c.__file__), "native", "include")
        if os.path.isdir(cand):
            return ["-I" + cand]
    except Exception:
        pass
    return []


class ParseTruncated(RuntimeError):
    """A fatal clang diagnostic means bodies may be missing -- never analyze that."""


def check_diagnostics(tu, path, strict=True):
    """Return fatal diagnostics; raise if strict. NEVER analyze a truncated AST."""
    fatal = [d for d in tu.diagnostics if d.severity >= 4]      # 4 == FATAL
    if fatal and strict:
        detail = "; ".join(f"{d.location}: {d.spelling}" for d in fatal[:3])
        raise ParseTruncated(
            f"libclang hit a FATAL error parsing {path} -- function bodies are "
            f"TRUNCATED and any analysis would be wrong: {detail}. "
            f"(Usually clang's builtin headers are missing; pass the include dir.)"
        )
    return fatal


def _require():
    if not _HAVE:
        raise ImportError("libclang bindings not available; `pip install libclang`")


# --- type helpers -----------------------------------------------------------
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


# --- AST helpers ------------------------------------------------------------
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


# --- the engine -------------------------------------------------------------
class LibclangEngine:
    def __init__(self, clang_args=None, strict=True):
        self.args = list(clang_args or [])
        self.strict = strict          # refuse to analyze a truncated AST

    def _parse(self, path, clang_args=None):
        _require()
        args = list(clang_args or self.args)
        args = builtin_include_args() + args      # stddef.h etc. -- or bodies truncate
        idx = cindex.Index.create()
        tu = idx.parse(path, args=args)
        check_diagnostics(tu, path, strict=self.strict)
        return tu

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
                if d.kind != cindex.CursorKind.CALL_EXPR:
                    continue
                if not _callee_is_dealloc(d):
                    continue
                for arg in d.get_arguments():
                    # ONLY a direct reference frees the param. cJSON_free(object->valuestring)
                    # must NOT mark `object` as freed -- that produced spurious `destroys`
                    # for SetValuestring / DeleteItemFromArray / ReplaceItemViaPointer.
                    nm = _direct_ref(arg, struct_params)
                    if nm:
                        freed.add(nm)
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


def _callee_is_dealloc(call) -> bool:
    """A deallocator may be free(), a custom name, or a function POINTER through a
    hooks struct: global_hooks.deallocate(item) -- which is what cJSON does."""
    if _is_dealloc_name(call.spelling):
        return True
    for ch in call.get_children():
        if ch.kind == cindex.CursorKind.MEMBER_REF_EXPR and _is_dealloc_name(ch.spelling):
            return True
        if ch.kind == cindex.CursorKind.DECL_REF_EXPR and _is_dealloc_name(ch.spelling):
            return True
    return False


def _callee_name_of(call) -> str:
    """Callee name of a CALL_EXPR -- token-based, so it does not depend on how
    libclang happens to wrap the callee (implicit casts / UNEXPOSED_EXPR nesting,
    which defeated every AST-shape heuristic: some calls resolved, others came back
    empty or picked up the first ARGUMENT).

    The callee is simply the identifier immediately before the first '(':
        cJSON_ParseWithLengthOpts(value, len, ...)  -> "cJSON_ParseWithLengthOpts"
        hooks->allocate(sizeof(cJSON))              -> "allocate"
    """
    try:
        ref = call.referenced
        if ref is not None and ref.spelling:
            return ref.spelling
    except Exception:
        pass
    if call.spelling:
        return call.spelling
    try:
        toks = [t.spelling for t in call.get_tokens()]
        for i, t in enumerate(toks):
            if t == "(" and i > 0:
                return toks[i - 1]
        if toks:
            return toks[0]
    except Exception:
        pass
    return ""


def _unwrap(n):
    """Strip transparent wrappers (implicit casts, parens) to the real expression.

    NOTE: a CSTYLE_CAST_EXPR's children are [TYPE_REF, expr] -- TWO nodes. Requiring
    exactly one child made `(cJSON*)hooks->allocate(...)` fail to unwrap, so the
    allocation was invisible and cJSON_New_Item came out `unknown`.
    """
    global _TRANSPARENT
    if _TRANSPARENT is None:
        ck = cindex.CursorKind
        _TRANSPARENT = {ck.UNEXPOSED_EXPR, ck.PAREN_EXPR, ck.CSTYLE_CAST_EXPR}
    while n is not None and n.kind in _TRANSPARENT:
        kids = [k for k in n.get_children()
                if k.kind != cindex.CursorKind.TYPE_REF]     # drop the cast's type
        if len(kids) != 1:
            return n
        n = kids[0]
    return n


_TRANSPARENT = None

def _direct_ref(node, names):
    """Name of a DIRECT reference to one of `names`, unwrapping only casts/parens.
    Returns None for member access (p->f), calls, or anything derived."""
    global _TRANSPARENT
    if _TRANSPARENT is None:
        ck = cindex.CursorKind
        _TRANSPARENT = {ck.UNEXPOSED_EXPR, ck.PAREN_EXPR, ck.CSTYLE_CAST_EXPR}
    n = node
    while n is not None:
        if n.kind == cindex.CursorKind.DECL_REF_EXPR:
            return n.spelling if n.spelling in names else None
        if n.kind in _TRANSPARENT:
            kids = list(n.get_children())
            n = kids[0] if len(kids) == 1 else None
            continue
        return None                       # member ref, call, binary op, ... -> not direct
    return None


def _root_param(node, params):
    """Root identifier of an expr (unwrapping member/cast/paren), if it's a param."""
    for n in node.walk_preorder():
        if n.kind == cindex.CursorKind.DECL_REF_EXPR and n.spelling in params:
            return n.spelling
    return None


class _OwnershipMixin:
    def ownership_records(self, path, clang_args=None) -> dict:
        """Extract ownership evidence per function: where the returned pointer came
        from, and whether it escaped into a handle-typed parameter."""
        tu = self._parse(path, clang_args)
        recs: dict[str, OwnRecord] = {}
        for c in self._defined_functions(tu, path):
            rec = OwnRecord(c.spelling)
            if _struct_pointee_name(c.result_type) is None:
                recs[c.spelling] = rec
                continue
            rec.returns_pointer = True
            params = {a.spelling for a in c.get_arguments()}
            rec.handle_params = [a.spelling for a in c.get_arguments()
                                 if _struct_pointee_name(a.type)]

            origin: dict[str, str] = {}
            returns, calls = [], []

            def origin_of(expr):
                """Classify the TOP-LEVEL expression. Scanning the whole subtree let a
                call inside an ARGUMENT hijack the origin (cJSON_Duplicate came out as
                `call:item`)."""
                n = _unwrap(expr)
                if n is None:
                    return "unknown"
                k = n.kind
                if k == cindex.CursorKind.CALL_EXPR:
                    cn = _callee_name_of(n)
                    if _is_alloc_name(cn):
                        return "alloc"
                    return f"call:{cn}" if cn else "unknown"
                if k == cindex.CursorKind.MEMBER_REF_EXPR:
                    if _root_param(n, params):
                        return "param"           # object->child
                    base = next((x.spelling for x in n.walk_preorder()
                                 if x.kind == cindex.CursorKind.DECL_REF_EXPR), None)
                    if base and origin.get(base) == "param":
                        return "param"           # cur = cur->next : stays in the borrow
                    return "unknown"
                if k == cindex.CursorKind.DECL_REF_EXPR:
                    if n.spelling in params:
                        return "param"
                    return origin.get(n.spelling, "unknown")
                return "unknown"

            for n in c.walk_preorder():
                if n.kind == cindex.CursorKind.VAR_DECL:
                    kids = [k for k in n.get_children()
                            if k.kind != cindex.CursorKind.TYPE_REF]
                    if kids:                       # last child is the initializer
                        origin[n.spelling] = origin_of(kids[-1])
                elif n.kind == cindex.CursorKind.BINARY_OPERATOR and _binop_is_assign(n):
                    kids = list(n.get_children())
                    if len(kids) == 2:
                        lhs = _unwrap(kids[0])       # may be wrapped
                        if lhs is not None and lhs.kind == cindex.CursorKind.DECL_REF_EXPR:
                            origin[lhs.spelling] = origin_of(kids[1])
                elif n.kind == cindex.CursorKind.RETURN_STMT:
                    kids = list(n.get_children())
                    if kids:
                        returns.append(kids[0])
                elif n.kind == cindex.CursorKind.CALL_EXPR:
                    roots = []
                    for a in n.get_arguments():
                        nm = _direct_ref(a, params | set(origin))   # direct args only
                        if nm:
                            roots.append(nm)
                    calls.append((_callee_name_of(n), roots))

            # Collect EVERY return's origin, then pick by priority. The old
            # "first non-unknown wins, then break" was order-dependent: an early
            # `return NULL;` (cJSON_ParseWithOpts) could leave the real
            # `return cJSON_ParseWithLengthOpts(...)` unexamined.
            ret_ids, origins = [], []
            for expr in returns:
                origins.append(origin_of(expr))
                for r in expr.walk_preorder():
                    if r.kind == cindex.CursorKind.DECL_REF_EXPR:
                        ret_ids.append(r.spelling)

            if "param" in origins:
                rec.origin = "param"                       # borrowed wins (fail-safe)
            elif "alloc" in origins:
                rec.origin = "alloc"
            else:
                call_origins = [o for o in origins if o.startswith("call:")]
                rec.origin = call_origins[0] if call_origins else "unknown"

            # ESCAPE only makes sense for a pointer WE allocated here. If the return
            # is just a call to another function, that callee's verdict governs --
            # applying escape there wrongly borrowed cJSON_Duplicate and mislabelled
            # cJSON_GetObjectItem's reason.
            if rec.origin == "alloc":
                for callee, roots in calls:
                    if _is_alloc_name(callee):
                        continue
                    if any(r in ret_ids for r in roots) and \
                       any(r in rec.handle_params for r in roots):
                        rec.escaped = True
                        break

            recs[c.spelling] = rec
        return recs


# mix ownership extraction into the engine
LibclangEngine.ownership_records = _OwnershipMixin.ownership_records