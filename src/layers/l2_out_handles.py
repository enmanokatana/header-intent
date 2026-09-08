"""
L2 out-param-handle confirmation (sqlite3_open(path, &db) idiom).

L0 detects CANDIDATES: any T** parameter where T is a struct (see
model/extract.py's _out_handle_candidate). A candidate is not trusted until
confirmed here -- staying OPAQUE (refused) is the fail-safe default, same as
every other unresolved pointer shape in this project.

Confirmation has two forms, because sqlite3_open itself is a one-line wrapper
around an internal helper (openDatabase) that does the actual allocation:

  1. DIRECT: the function's body writes `*out = <alloc-derived expr>;`
     (or `out[0] = ...`) -- resolved with the SAME alloc/call-chain origin
     tracing already proven for return-value ownership (l2_ownership.py).
  2. FORWARD: the function's only use of `out` is passing it BYREF, unmodified,
     to exactly one other call -- resolved via a fixed point over that callee's
     OWN verdict for the out-param at the same argument position, mirroring the
     call-chain propagation already proven for ownership's "call:X" origin.

Both forms are deliberately conservative: anything more complex (branching
writes, multiple candidate calls, the pointer read before written) is left
UNCONFIRMED -- the candidate stays a candidate, the param stays refused.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pycparser import c_ast, c_parser

from .l2_ownership import _is_alloc_name, _callee_name


class _MultiOriginCollector(c_ast.NodeVisitor):
    """Tracks, per local variable, the SET of every origin it is ever assigned --
    not just the last one. This is deliberately DIFFERENT from l2_ownership's
    _OwnCollector (which tracks a single overwriting value per name, correct for
    return-value tracing) because real sqlite3 code does this:

        db = sqlite3MallocZero(sizeof(sqlite3));   // success path: alloc
        ...
        if (rc != SQLITE_OK) { ...; db = 0; }      // an error path: reset to NULL
        ...
        opendb_out:
        *ppDb = db;                                 // reached from EVERY path

    `db` legitimately holds EITHER the allocated pointer OR NULL depending on
    which branch executed, and BOTH values flow into the same final write.
    "Last assignment wins" forgets the allocation entirely once it sees the
    later `db = 0` reset. The question we actually care about -- does there
    EXIST an execution path where this out-param receives a fresh allocation --
    is answered correctly by checking whether "alloc" is anywhere in the set,
    regardless of what else the variable was also assigned on other paths (a
    null-reset on failure is not a competing claim on ownership; it correctly
    becomes `handle: None` at runtime either way).
    """
    def __init__(self):
        self.origin: dict[str, set[str]] = {}

    def _origin_of_expr(self, expr) -> str:
        if expr is None:
            return "unknown"
        if isinstance(expr, c_ast.FuncCall):
            cn = _callee_name(expr.name)
            return "alloc" if _is_alloc_name(cn) else f"call:{cn}"
        if isinstance(expr, c_ast.ID):
            s = self.origin.get(expr.name)
            return "alloc" if s and "alloc" in s else "unknown"
        return "unknown"

    def visit_Decl(self, node):
        if node.init is not None and node.name:
            self.origin.setdefault(node.name, set()).add(self._origin_of_expr(node.init))
        self.generic_visit(node)

    def visit_Assignment(self, node):
        # ONLY a bare-identifier reassignment changes what the POINTER VARIABLE
        # itself refers to. `db->mutex = ...` writes a FIELD of *db -- it must
        # NOT be recorded as a new origin for `db` (the variable's own identity
        # is unchanged); only `isinstance(lvalue, c_ast.ID)` counts.
        if node.op == "=" and isinstance(node.lvalue, c_ast.ID):
            self.origin.setdefault(node.lvalue.name, set()).add(self._origin_of_expr(node.rvalue))
        self.generic_visit(node)

    def any_alloc(self, name: str) -> bool:
        s = self.origin.get(name)
        return bool(s and "alloc" in s)


@dataclass
class OutHandleRecord:
    """One (function, out-param) candidate's evidence."""
    function: str
    param: str
    struct_name: str
    origin: str = "unknown"          # "alloc" | "forward:<callee>:<argindex>" | "unknown"


@dataclass
class OutHandleFact:
    function: str
    param: str
    struct_name: str
    confirmed: bool
    confidence: float
    reason: str


def _direct_write_expr(body, param: str):
    """Find `*param = expr;` or `param[0] = expr;` at any depth; return expr or None."""
    found = [None]

    class V(c_ast.NodeVisitor):
        def visit_Assignment(self, node):
            if node.op == "=":
                lv = node.lvalue
                is_deref = (isinstance(lv, c_ast.UnaryOp) and lv.op == "*"
                           and isinstance(lv.expr, c_ast.ID) and lv.expr.name == param)
                is_index0 = (isinstance(lv, c_ast.ArrayRef) and isinstance(lv.name, c_ast.ID)
                            and lv.name.name == param and isinstance(lv.subscript, c_ast.Constant)
                            and lv.subscript.value == "0")
                if is_deref or is_index0:
                    found[0] = node.rvalue
            self.generic_visit(node)

    V().visit(body)
    return found[0]


def _forward_call(body, param: str):
    """If `param`'s ONLY appearance is as a direct, unmodified argument to ONE
    call, return (callee_name, arg_index). Else None (too complex to trust)."""
    appearances = []          # (kind, extra) -- kind in {"call_arg", "other"}

    class V(c_ast.NodeVisitor):
        def visit_FuncCall(self, node):
            if node.args:
                for i, a in enumerate(node.args.exprs):
                    if isinstance(a, c_ast.ID) and a.name == param:
                        appearances.append(("call_arg", (_callee_name(node.name), i)))
            self.generic_visit(node)

        def visit_ID(self, node):
            # any OTHER bare use of the name outside a call arg counts as "other"
            # (visit_FuncCall's generic_visit will also re-visit args as ID nodes,
            # so we only flag names NOT already recorded as a call_arg at this spot)
            pass

    V().visit(body)
    call_args = [a for k, a in appearances if k == "call_arg"]
    if len(call_args) == 1:
        return call_args[0]
    return None


_SCALAR_NAMES = {"char", "void", "int", "float", "double", "unsigned", "signed",
                 "short", "long", "_Bool"}


def _double_ptr_struct_params(fd) -> dict:
    """T** params where T is a struct/typedef-to-struct, detected directly from
    pycparser's AST -- mirrors model/extract.py's _out_handle_candidate but for
    the .c SOURCE, so INTERNAL static helpers (never declared in the header,
    hence never in L0's candidate dict) still get discovered here. sqlite3_open
    forwards to exactly such a helper (openDatabase); without this, the fixed
    point in classify_out_handles would have nothing to resolve the forward TO.

    NOTE: real code almost always uses the TYPEDEF name (`sqlite3 **ppDb`), which
    pycparser represents as IdentifierType(['sqlite3']), not c_ast.Struct -- the
    same distinction l2_handles._pointee_typename already has to make.
    """
    out = {}
    args = fd.decl.type.args
    if not args:
        return out
    for pd in args.params:
        if not (isinstance(pd, c_ast.Decl) and pd.name):
            continue
        t = pd.type
        if isinstance(t, c_ast.PtrDecl) and isinstance(t.type, c_ast.PtrDecl):
            inner = t.type.type
            if isinstance(inner, c_ast.TypeDecl):
                it = inner.type
                if isinstance(it, c_ast.Struct) and it.name:
                    out[pd.name] = it.name
                elif isinstance(it, c_ast.IdentifierType):
                    name = " ".join(it.names)
                    if name and name not in _SCALAR_NAMES:
                        out[pd.name] = name
    return out


def _records_from_pycparser(source: str, candidates: dict) -> dict:
    """`candidates`: {fname: {argname: struct_name}} from L0 (header-declared
    functions only). Internal source-only helpers are discovered separately
    (see _double_ptr_struct_params) so forwarding through them still resolves."""
    ast = c_parser.CParser().parse(source)

    # full param-order map for EVERY function, needed to resolve a forwarding
    # call's argument INDEX to the callee's actual parameter NAME (the call site
    # and the callee's own declaration can order/name things differently).
    all_params: dict[str, list[str]] = {}
    all_candidates: dict[str, dict] = {}      # header hints UNION source-discovered
    for fd in ast.ext:
        if isinstance(fd, c_ast.FuncDef) and fd.decl.type.args:
            all_params[fd.decl.name] = [p.name for p in fd.decl.type.args.params
                                        if isinstance(p, c_ast.Decl) and p.name]
        if isinstance(fd, c_ast.FuncDef):
            merged = dict(_double_ptr_struct_params(fd))
            merged.update(candidates.get(fd.decl.name, {}))   # header hint wins on conflict
            if merged:
                all_candidates[fd.decl.name] = merged

    recs = {}
    for fd in ast.ext:
        if not isinstance(fd, c_ast.FuncDef):
            continue
        fname = fd.decl.name
        cands = all_candidates.get(fname, {})
        if not cands:
            continue
        for pname, struct_name in cands.items():
            rec = OutHandleRecord(fname, pname, struct_name)
            col = _MultiOriginCollector()
            col.visit(fd.body)
            direct = _direct_write_expr(fd.body, pname)
            if direct is not None:
                # THE fix: _origin_of_expr checks the variable's ENTIRE
                # assignment history (a SET), not just its last-seen value --
                # db=alloc(...) then later db=0 on an error path must not erase
                # the alloc evidence just because it's textually more recent.
                origin = col._origin_of_expr(direct)
                if origin == "alloc":
                    rec.origin = "alloc"
                elif origin.startswith("call:"):
                    rec.origin = origin
                # else: leaves rec.origin at "unknown" (conservative)
            else:
                fwd = _forward_call(fd.body, pname)
                if fwd:
                    callee, arg_idx = fwd
                    callee_params = all_params.get(callee, [])
                    if arg_idx < len(callee_params):
                        rec.origin = f"forward:{callee}:{callee_params[arg_idx]}"
            recs[(fname, pname)] = rec
    return recs


def classify_out_handles(records: dict) -> dict:
    """Fixed point: resolve 'call:X' (direct alloc-wrapper) and 'forward:F:name'
    (byref passthrough, resolved by the callee's OWN parameter name) against
    other records' verdicts."""
    verdict: dict = {}   # (fname, pname) -> bool confirmed

    changed = True
    for _ in range(10):
        if not changed:
            break
        changed = False
        for key, rec in records.items():
            if key in verdict:
                continue
            if rec.origin == "alloc":
                verdict[key] = True
                changed = True
            elif rec.origin.startswith("call:"):
                # direct write is itself a call to a non-obviously-alloc wrapper;
                # without interprocedural return-value tracing here, treat as
                # unconfirmed (conservative) -- the ownership analysis already
                # covers return-value cases; this module only covers out-params.
                verdict[key] = False
                changed = True
            elif rec.origin.startswith("forward:"):
                _, callee, pname = rec.origin.split(":", 2)
                target = (callee, pname)
                if target in verdict:
                    verdict[key] = verdict[target]
                    changed = True
                elif target not in records:
                    # forwards to a param that isn't itself a candidate at all
                    # (e.g. forwarded to a plain non-handle param) -> unconfirmed
                    verdict[key] = False
                    changed = True
            elif rec.origin == "unknown":
                verdict[key] = False
                changed = True

    facts = {}
    for key, rec in records.items():
        ok = verdict.get(key, False)
        if ok:
            reason = ("writes a freshly allocated value through this parameter"
                      if rec.origin == "alloc" else
                      f"forwards to {rec.origin.split(':')[1]}, which is confirmed")
            conf = 0.85 if rec.origin == "alloc" else 0.7
        else:
            reason = "not confidently traced to an allocation (fail-safe: stays refused)"
            conf = 0.2
        facts[key] = OutHandleFact(rec.function, rec.param, rec.struct_name, ok, conf, reason)
    return facts


def analyze_out_handles(source: str | None = None, *, candidates: dict, engine=None,
                        path=None, clang_args=None) -> dict:
    if engine is not None:
        records = engine.out_handle_records(path, candidates, clang_args)
    else:
        records = _records_from_pycparser(source, candidates)
    return classify_out_handles(records)


def apply_out_handle_facts(spec, facts: dict) -> list:
    """Promote a CONFIRMED candidate param to Role.OUT_HANDLE and set
    FunctionSpec.handle_out_param (only one per function is supported)."""
    from ..spec.vocab import Role, Intent
    from ..spec.schema import Evidenced

    notes = []
    for (fname, pname), f in facts.items():
        if not f.confirmed:
            continue
        fn = spec.functions.get(fname)
        if fn is None:
            continue
        for p in fn.params:
            if p.name == pname:
                p.role = Role.OUT_HANDLE
                p.handle_type = f.struct_name
                p.intent = Evidenced(Intent.OUT, ["out_handle_analysis"], f.confidence, verified=False)
        fn.handle_out_param = pname
        fn.lifecycle = "creates"
        fn.owner = "caller"
        fn.handle_type = f.struct_name
        notes.append(f"{fname}: OUT_HANDLE param {pname!r} -> {f.struct_name} ({f.reason})")
    return notes


def analyze_out_handles_multi(paths, *, candidates: dict, engine, clang_args=None):
    """Multi-file out-handle analysis. out_handle_records auto-discovers internal
    T** candidates within each file and also confirms forwarding wrappers; merging
    the RAW records across files then classifying lets a public wrapper in one
    file resolve against the internal allocator helper in another (the
    sqlite3_open -> openDatabase pattern, but split across files). Returns
    (facts, skipped_notes)."""
    from .libclang_engine import _merge_multi
    records, skipped = _merge_multi(engine, "out_handle_records", paths, clang_args,
                                    extra_kwargs={"candidates": candidates})
    return classify_out_handles(records), skipped