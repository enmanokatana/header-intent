from __future__ import annotations

from dataclasses import dataclass, field

from pycparser import c_ast, c_parser

from .l2_ownership import _is_alloc_name, _callee_name


class _MultiOriginCollector(c_ast.NodeVisitor):
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
    origin: str = "unknown"         


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
    appearances = []          # (kind, extra)  kind in {"call_arg", "other"}

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
    ast = c_parser.CParser().parse(source)


    all_params: dict[str, list[str]] = {}
    all_candidates: dict[str, dict] = {}    
    for fd in ast.ext:
        if isinstance(fd, c_ast.FuncDef) and fd.decl.type.args:
            all_params[fd.decl.name] = [p.name for p in fd.decl.type.args.params
                                        if isinstance(p, c_ast.Decl) and p.name]
        if isinstance(fd, c_ast.FuncDef):
            merged = dict(_double_ptr_struct_params(fd))
            merged.update(candidates.get(fd.decl.name, {}))  
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
                origin = col._origin_of_expr(direct)
                if origin == "alloc":
                    rec.origin = "alloc"
                elif origin.startswith("call:"):
                    rec.origin = origin
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
    verdict: dict = {}  

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
                verdict[key] = False
                changed = True
            elif rec.origin.startswith("forward:"):
                _, callee, pname = rec.origin.split(":", 2)
                target = (callee, pname)
                if target in verdict:
                    verdict[key] = verdict[target]
                    changed = True
                elif target not in records:
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