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


def _has_stddef(d: str) -> bool:
    return os.path.isfile(os.path.join(d, "stddef.h"))


def builtin_include_args() -> list:
    """clang's OWN builtin headers (stddef.h, stdarg.h, ...).

    Without these libclang emits a FATAL "'stddef.h' file not found" and then
    ERROR-RECOVERS BY TRUNCATING FUNCTION BODIES -- silently. That is exactly what
    corrupted cJSON: `size_t buffer_length;` inside cJSON_ParseWithOpts made clang
    drop the rest of the body, so `return cJSON_ParseWithLengthOpts(...)` never
    appeared in the AST and ownership came out 'unknown'.

    Search order (all validated by actually containing stddef.h):
      1. clang's resource dir, if the clang binary is installed
      2. common LLVM install paths
      3. GCC's builtin include dir -- works fine for clang, and gcc is almost
         always present even when the clang *compiler* is not (only the libclang
         bindings are needed otherwise)
      4. headers bundled with the `libclang` pip wheel
    """
    cands = []

    for exe in ("clang", "clang-19", "clang-18", "clang-17", "clang-16", "clang-15"):
        try:
            out = subprocess.run([exe, "-print-resource-dir"], capture_output=True,
                                 text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                cands.append(os.path.join(out.stdout.strip(), "include"))
        except Exception:
            continue

    for pat in ("/usr/lib/llvm-*/lib/clang/*/include",
                "/usr/lib/clang/*/include",
                "/usr/local/lib/clang/*/include",
                "/usr/lib/gcc/*/*/include",          # gcc ships stddef.h too
                "/usr/lib/gcc/*/*/include-fixed"):
        cands.extend(sorted(glob.glob(pat)))

    try:
        import clang as _c
        cands.append(os.path.join(os.path.dirname(_c.__file__), "native", "include"))
    except Exception:
        pass

    for d in cands:
        if os.path.isdir(d) and _has_stddef(d):
            return ["-I" + d]
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
            f"(Clang's builtin headers were not found. Install them with "
            f"`sudo apt install clang`, or pass the dir explicitly, e.g. "
            f"-I /usr/lib/gcc/x86_64-linux-gnu/13/include)"
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
            param_order = []
            for a in c.get_arguments():
                param_order.append(a.spelling)
                tn = _struct_pointee_name(a.type)
                if tn:
                    struct_params[a.spelling] = tn
            freed = set()
            for d in c.walk_preorder():
                if d.kind != cindex.CursorKind.CALL_EXPR:
                    continue
                if not _callee_is_dealloc(d):
                    continue
                args = list(d.get_arguments())
                if args:
                    # ONLY the LAST argument is the thing being freed. cJSON's
                    # deallocators are single-arg (free(ptr), hooks->deallocate(item)),
                    # where last==only, so this is unchanged there. sqlite3's actual
                    # convention is sqlite3DbFree(sqlite3 *db, void *p): db is the
                    # ALLOCATOR CONTEXT (arg 0), p is what's freed (last arg). Checking
                    # every argument wrongly flagged `db` as destroyed on every function
                    # that calls sqlite3DbFree internally (sqlite3_exec, sqlite3_blob_open,
                    # sqlite3_declare_vtab, ...) even though db itself is never freed.
                    nm = _direct_ref(args[-1], struct_params)
                    if nm:
                        freed.add(nm)

            # Every DIRECT argument-position appearance of a not-yet-freed
            # struct-typed param, across every call in the body -- resolves
            # lifecycle classification through wrapper functions. sqlite3_close
            # forwards through TWO hops before the real free (sqlite3_close ->
            # sqlite3Close -> sqlite3LeaveMutexAndCloseZombie -> sqlite3_free(db)),
            # and the middle hop passes `db` directly to SIX different helper
            # calls, only one of which is the real closer -- see
            # l2_handles.classify_records for the fixed-point resolution this
            # feeds into.
            candidate_names = set(struct_params) - freed
            forwards = {n: [] for n in candidate_names}
            if candidate_names:
                for n in c.walk_preorder():
                    if n.kind != cindex.CursorKind.CALL_EXPR:
                        continue
                    callee = _callee_name_of(n)
                    if not callee:
                        continue
                    for i, a in enumerate(n.get_arguments()):
                        nm2 = _decl_ref_name(a, candidate_names)
                        if nm2:
                            forwards[nm2].append((callee, i))

            recs[name] = HandleRecord(name, ret, struct_params, freed, param_order, forwards)
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


def _merge_multi(eng, method_name, paths, clang_args, extra_kwargs=None):
    """Run one engine analysis method across several source files and union the
    per-function results, skipping any file that fails to parse (a real
    multi-file library always has some files that need generated headers or
    platform flags we don't have). Returns (merged_dict, skipped_notes).

    This is the core of multi-file support: each analysis is keyed by function
    name and a function is defined in exactly one .c, so a union across files
    reconstructs the whole-library view. The one analysis this does NOT fully
    resolve is cross-FILE ownership call chains (a function returning the result
    of a callee in another file) -- that needs the merged-graph fixed point of
    stage 2; here such a chain conservatively stays unresolved (fail-safe).

    All engine analysis methods share the signature (path, [candidates,]
    clang_args=...), so clang_args is passed as a keyword uniformly and any
    method-specific argument (out_handle_records' `candidates`) rides in
    extra_kwargs.
    """
    extra_kwargs = extra_kwargs or {}
    merged: dict = {}
    skipped: list = []
    method = getattr(eng, method_name)
    for p in paths:
        try:
            part = method(p, clang_args=clang_args, **extra_kwargs)
        except ParseTruncated as e:
            skipped.append(f"{os.path.basename(p)}: parse failed, skipped ({e})")
            continue
        except Exception as e:                       # never let one file abort all
            skipped.append(f"{os.path.basename(p)}: {type(e).__name__}, skipped")
            continue
        # union; a function defined in multiple files (rare: weak symbols,
        # platform variants) keeps the first file's verdict, which is stable
        # across runs because `paths` is caller-ordered.
        for k, v in part.items():
            merged.setdefault(k, v)
    return merged, skipped


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
        from, whether it escaped into a handle-typed parameter, and (for the
        ownership-TRANSFER rule) whether it mutates a DIFFERENT parameter's
        structure while returning one parameter unchanged."""
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
            mutated_param_roots: set = set()
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
                if k == cindex.CursorKind.MEMBER_REF_EXPR:            # DERIVED (p->child)
                    if _root_param(n, params):
                        return "param_member"
                    base = next((x.spelling for x in n.walk_preorder()
                                 if x.kind == cindex.CursorKind.DECL_REF_EXPR), None)
                    bo = origin.get(base, "")
                    if bo == "param_member" or bo.startswith("param_direct"):
                        return "param_member"       # cur = cur->next : stays in the borrow
                    return "unknown"
                if k == cindex.CursorKind.DECL_REF_EXPR:
                    if n.spelling in params:
                        return f"param_direct:{n.spelling}"   # the parameter ITSELF
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
                        elif lhs is not None and lhs.kind == cindex.CursorKind.MEMBER_REF_EXPR:
                            # a WRITE through a member (p->field = ...) -- unlink evidence.
                            root = _root_param(lhs, params)
                            if root:
                                mutated_param_roots.add(root)
                            else:
                                base = next((x.spelling for x in lhs.walk_preorder()
                                            if x.kind == cindex.CursorKind.DECL_REF_EXPR), None)
                                bo = origin.get(base, "")
                                if bo.startswith("param_direct:"):
                                    mutated_param_roots.add(bo.split(":", 1)[1])
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

            if "param_member" in origins:
                rec.origin = "param_member"                # derived-from-param wins (fail-safe)
            elif "alloc" in origins:
                rec.origin = "alloc"
            else:
                direct = [o for o in origins if o.startswith("param_direct:")]
                if direct:
                    rec.origin = direct[0]
                    pname = direct[0].split(":", 1)[1]
                    rec.mutates_other_param = pname in mutated_param_roots
                else:
                    call_origins = [o for o in origins if o.startswith("call:")]
                    rec.origin = call_origins[0] if call_origins else "unknown"

            # ESCAPE applies whenever the return is freshly PRODUCED here -- either
            # a direct alloc, or a call to a wrapper that allocates (cJSON_AddNullToObject
            # calls cJSON_CreateNull(), it does not malloc directly; gating this on
            # origin=="alloc" literally missed every Add*ToObject function -- a REAL
            # regression: silently reclassified caller-owned instead of BORROWED, a
            # live double-free risk).
            #
            # The PRODUCER call itself is excluded from the scan, or its own
            # arguments falsely look like an escape target -- this is what caused the
            # ORIGINAL cJSON_Duplicate bug: `return dup_rec(item, hooks, recurse);`
            # walks `item` into ret_ids (inside the return expression's subtree), and
            # dup_rec's own args re-match against handle_params, making the producer
            # look like a consumer of its own output.
            producer = rec.origin.split(":", 1)[1] if rec.origin.startswith("call:") else None
            if rec.origin == "alloc" or rec.origin.startswith("call:"):
                for callee, roots in calls:
                    if _is_alloc_name(callee) or callee == producer:
                        continue
                    if any(r in ret_ids for r in roots) and \
                       any(r in rec.handle_params for r in roots):
                        rec.escaped = True
                        break

            recs[c.spelling] = rec
        return recs


# mix ownership extraction into the engine
LibclangEngine.ownership_records = _OwnershipMixin.ownership_records


def _returns_char_ptr_clang(t) -> bool:
    if t.kind != cindex.TypeKind.POINTER:
        return False
    pointee = t.get_pointee().get_canonical()
    return pointee.kind in (cindex.TypeKind.CHAR_S, cindex.TypeKind.CHAR_U,
                            cindex.TypeKind.SCHAR, cindex.TypeKind.UCHAR)


class _StringOwnershipMixin:
    def string_ownership_records(self, path, clang_args=None) -> dict:
        """Same origin-tracing as ownership_records, retargeted at char* returns,
        with the SAME simpler rule set as the pycparser path: no escape rule, no
        transfer rule -- a wrong deallocator call here is heap corruption, not a
        leak, so only unambiguous evidence is trusted."""
        tu = self._parse(path, clang_args)
        recs: dict = {}
        for c in self._defined_functions(tu, path):
            if not _returns_char_ptr_clang(c.result_type):
                continue
            params = {a.spelling for a in c.get_arguments()}
            origin: dict = {}
            returns = []

            def origin_of(expr):
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
                    return "param_member" if _root_param(n, params) else "unknown"
                if k == cindex.CursorKind.DECL_REF_EXPR:
                    if n.spelling in params:
                        return "param_member"     # any param-derived string: don't free
                    return origin.get(n.spelling, "unknown")
                if k == cindex.CursorKind.STRING_LITERAL:
                    return "static"
                return "unknown"

            for n in c.walk_preorder():
                if n.kind == cindex.CursorKind.VAR_DECL:
                    kids = [k for k in n.get_children()
                            if k.kind != cindex.CursorKind.TYPE_REF]
                    if kids:
                        origin[n.spelling] = origin_of(kids[-1])
                elif n.kind == cindex.CursorKind.BINARY_OPERATOR and _binop_is_assign(n):
                    kids = list(n.get_children())
                    if len(kids) == 2:
                        lhs = _unwrap(kids[0])
                        if lhs is not None and lhs.kind == cindex.CursorKind.DECL_REF_EXPR:
                            origin[lhs.spelling] = origin_of(kids[1])
                elif n.kind == cindex.CursorKind.RETURN_STMT:
                    kids = list(n.get_children())
                    if kids:
                        returns.append(kids[0])

            origins = [origin_of(e) for e in returns]
            if not origins:
                recs[c.spelling] = ("not_owned", "no return path found (fail-safe)")
            elif "param_member" in origins or "unknown" in origins or "static" in origins:
                recs[c.spelling] = ("not_owned", "borrowed/static, or a return path we "
                                                 "are not confident about (fail-safe)")
            elif all(o == "alloc" for o in origins):
                recs[c.spelling] = ("alloc", "returns a freshly allocated string")
            elif all(o == "alloc" or o.startswith("call:") for o in origins):
                recs[c.spelling] = ("call", origins)
            else:
                recs[c.spelling] = ("not_owned", "ownership unresolved; fail-safe = do not free")
        return recs


LibclangEngine.string_ownership_records = _StringOwnershipMixin.string_ownership_records


class _OutHandleMixin:
    def out_handle_records(self, path, candidates: dict, clang_args=None) -> dict:
        """libclang mirror of l2_out_handles._records_from_pycparser. Same two
        confirmation forms (direct alloc-write, one-level forward), same
        auto-discovery of INTERNAL (non-header) T**-to-struct candidates so a
        forwarding wrapper (sqlite3_open -> static openDatabase) still resolves.

        UNVERIFIED against real libclang in this sandbox (no libclang available
        here) -- mirrors the pycparser implementation's proven logic structurally,
        but the AST-shape assumptions (cursor kinds, child ordering) carry the
        same risk every libclang-side addition in this project has needed at
        least one round of live correction for. Test against real sqlite3 before
        trusting it; if a candidate that should confirm doesn't, the likely cause
        is the same class of AST-shape mismatch fixed repeatedly in
        ownership_records (see FERRULE docs) -- a targeted diag script beats
        guessing at the shape again.
        """
        from .l2_ownership import OwnRecord
        from .l2_out_handles import OutHandleRecord, _SCALAR_NAMES

        tu = self._parse(path, clang_args)
        funcs = list(self._defined_functions(tu, path))

        # discover ALL functions' double-pointer-to-struct params (source-wide,
        # not just header-declared ones) so internal helpers resolve too.
        all_candidates: dict = {}
        all_params: dict = {}
        for c in funcs:
            params = [a.spelling for a in c.get_arguments()]
            all_params[c.spelling] = params
            found = {}
            for a in c.get_arguments():
                canon = a.type.get_canonical()
                if canon.kind != cindex.TypeKind.POINTER:
                    continue
                inner = canon.get_pointee().get_canonical()
                if inner.kind != cindex.TypeKind.POINTER:
                    continue
                struct_t = inner.get_pointee()
                sc = struct_t.get_canonical()
                if sc.kind == cindex.TypeKind.RECORD:
                    decl = struct_t.get_declaration()
                    name = (decl.spelling or sc.spelling or "").replace("struct ", "").strip()
                    if name:
                        found[a.spelling] = name
            merged = dict(found)
            merged.update(candidates.get(c.spelling, {}))    # header hint wins
            if merged:
                all_candidates[c.spelling] = merged

        recs: dict = {}
        for c in funcs:
            fname = c.spelling
            cands = all_candidates.get(fname, {})
            if not cands:
                continue

            # local-variable origin tracing -- ACCUMULATES a SET of every
            # origin a variable is ever assigned, rather than overwriting.
            # Real sqlite3 does this in openDatabase:
            #     db = sqlite3MallocZero(...);   // success path
            #     ...
            #     if (rc != SQLITE_OK) { db = 0; }  // an error path
            #     opendb_out: *ppDb = db;         // reached from EVERY path
            # "last assignment wins" forgets the allocation once it sees
            # the later reset. The real question -- does an execution path
            # EXIST where this out-param receives a fresh allocation -- is
            # answered by checking whether "alloc" is in the set at all.
            #
            # PERFORMANCE: walk the function body ONCE for ALL of its
            # candidate params, not once per param -- a full walk_preorder()
            # over a large function (sqlite3's VDBE/parser functions run to
            # thousands of nodes) is the expensive part; re-walking it once
            # per T** parameter when a function has several was pure waste.
            origin: dict = {}
            direct_rhs_by_param: dict = {}
            forward_target_by_param: dict = {}
            cand_names = set(cands)

            def origin_of(expr):
                n = _unwrap(expr)
                if n is None:
                    return "unknown"
                k = n.kind
                if k == cindex.CursorKind.CALL_EXPR:
                    cn = _callee_name_of(n)
                    return "alloc" if _is_alloc_name(cn) else (f"call:{cn}" if cn else "unknown")
                if k == cindex.CursorKind.DECL_REF_EXPR:
                    s = origin.get(n.spelling)
                    return "alloc" if s and "alloc" in s else "unknown"
                return "unknown"

            for n in c.walk_preorder():
                if n.kind == cindex.CursorKind.VAR_DECL:
                    kids = [k for k in n.get_children() if k.kind != cindex.CursorKind.TYPE_REF]
                    if kids:
                        origin.setdefault(n.spelling, set()).add(origin_of(kids[-1]))
                elif n.kind == cindex.CursorKind.BINARY_OPERATOR and _binop_is_assign(n):
                    kids = list(n.get_children())
                    if len(kids) == 2:
                        lhs = _unwrap(kids[0])
                        if lhs is not None and lhs.kind == cindex.CursorKind.DECL_REF_EXPR:
                            origin.setdefault(lhs.spelling, set()).add(origin_of(kids[1]))
                        elif lhs is not None and lhs.kind == cindex.CursorKind.UNARY_OPERATOR \
                                and _is_deref(lhs):
                            # *pname = expr -- the dereference operand must be
                            # unwrapped too (libclang wraps it in UNEXPOSED_EXPR);
                            # _decl_ref_name already exists and handles it.
                            #
                            # LAST write wins, not first. openDatabase does
                            # `*ppDb = 0;` as a defensive reset near the top,
                            # THEN the real `*ppDb = db;` at a cleanup label
                            # near the bottom. A first-wins guard here locks in
                            # the defensive reset and the real write is never
                            # recorded -- this was a real regression introduced
                            # by the single-walk-per-function restructuring
                            # (the original per-parameter walk overwrote
                            # unconditionally on every match, which is correct;
                            # this rewrite accidentally added a "only if not
                            # already seen" guard while consolidating the walk).
                            sub = list(lhs.get_children())
                            if sub:
                                nm = _decl_ref_name(sub[0], cand_names)
                                if nm:
                                    direct_rhs_by_param[nm] = kids[1]
                elif n.kind == cindex.CursorKind.CALL_EXPR:
                    callee = _callee_name_of(n)
                    for i, a in enumerate(n.get_arguments()):
                        nm = _decl_ref_name(a, cand_names)
                        if nm and nm not in direct_rhs_by_param and nm not in forward_target_by_param:
                            forward_target_by_param[nm] = (callee, i)

            for pname, struct_name in cands.items():
                rec = OutHandleRecord(fname, pname, struct_name)
                direct_rhs = direct_rhs_by_param.get(pname)
                if direct_rhs is not None:
                    o = origin_of(direct_rhs)
                    if o == "alloc" or o.startswith("call:"):
                        rec.origin = o
                elif pname in forward_target_by_param:
                    callee, idx = forward_target_by_param[pname]
                    callee_params = all_params.get(callee, [])
                    if idx < len(callee_params):
                        rec.origin = f"forward:{callee}:{callee_params[idx]}"
                recs[(fname, pname)] = rec
        return recs


LibclangEngine.out_handle_records = _OutHandleMixin.out_handle_records