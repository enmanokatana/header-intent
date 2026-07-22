
from __future__ import annotations

from dataclasses import dataclass, field

from pycparser import c_ast, c_parser


import re as _re

from .l2_ownership import _tokenize_ident

_DEALLOC_WORDS = {"free", "dealloc", "deallocate", "destroy", "delete", "release", "dispose"}


def _is_dealloc_name(name: str) -> bool:
    """Whole-word match over BOTH snake_case and camelCase tokens (see
    l2_ownership._tokenize_ident) -- sqlite3's internal deallocator is
    `sqlite3DbFree` (camelCase, no underscore), the same naming-convention gap
    that _is_alloc_name needed fixing for."""
    if not name:
        return False
    return any(w in _DEALLOC_WORDS for w in _tokenize_ident(name))


_FREE_NAMES = {"free"}         


@dataclass
class HandleRecord:
    """Engine-neutral extraction for one function."""
    name: str
    return_pointee: str | None = None            # struct/typedef name if returns T*
    struct_ptr_params: dict = field(default_factory=dict)  # param -> type name
    freed: set = field(default_factory=set)      # params passed to free()
    param_order: list = field(default_factory=list)  # ALL param names, SOURCE order.
    # Needed because a header prototype and its .c definition can legally use
    # DIFFERENT parameter names (or the header may omit them entirely 
    # sqlite3.h declares many functions as `int sqlite3_close(sqlite3*);` with
    # no name at all, so L0 auto-names that param "a0"). Facts computed here
    # come from the SOURCE file's real names ("db"); apply_handle_facts must
    # fall back to matching by POSITION when the name itself doesn't match.


@dataclass
class HandleFacts:
    function: str
    role: str | None = None                       # creates | uses | destroys
    handle_type: str | None = None
    handle_param: str | None = None               # the one freed/used (destroys/uses)
    handle_params: list = field(default_factory=list)   # ALL handle-typed params
    param_order: list = field(default_factory=list)     # SOURCE-side param order (see HandleRecord)



def _pointee_typename(node) -> str | None:
    if isinstance(node, c_ast.PtrDecl):
        inner = node.type
        if isinstance(inner, c_ast.TypeDecl):
            t = inner.type
            if isinstance(t, c_ast.IdentifierType):
                name = " ".join(t.names)
                return name if name not in ("char", "void", "int", "float", "double") else None
            if isinstance(t, c_ast.Struct):
                return t.name
    return None


class _FreeFinder(c_ast.NodeVisitor):
    def __init__(self):
        self.freed_ids: set[str] = set()

    @staticmethod
    def _callee_name(nm) -> str:
        if isinstance(nm, c_ast.ID):
            return nm.name                      
        if isinstance(nm, c_ast.StructRef):
            return nm.field.name               
        return ""

    def visit_FuncCall(self, node):
        if _is_dealloc_name(self._callee_name(node.name)):
            if node.args:
                for e in node.args.exprs:
                    if isinstance(e, c_ast.ID):
                        self.freed_ids.add(e.name)
        self.generic_visit(node)


def _records_from_pycparser(source: str) -> dict[str, HandleRecord]:
    ast = c_parser.CParser().parse(source)
    recs: dict[str, HandleRecord] = {}
    for fd in ast.ext:
        if not isinstance(fd, c_ast.FuncDef):
            continue
        name = fd.decl.name
        funcdecl = fd.decl.type
        ret = _pointee_typename(funcdecl.type)
        struct_params: dict[str, str] = {}
        param_order = []
        if funcdecl.args:
            for pd in funcdecl.args.params:
                if isinstance(pd, c_ast.Decl):
                    param_order.append(pd.name)
                    tn = _pointee_typename(pd.type)
                    if tn:
                        struct_params[pd.name] = tn
        ff = _FreeFinder()
        ff.visit(fd.body)
        freed = {p for p in struct_params if p in ff.freed_ids}
        recs[name] = HandleRecord(name, ret, struct_params, freed, param_order)
    return recs



def classify_records(records: dict[str, HandleRecord]) -> tuple[dict[str, HandleFacts], set[str]]:
    returned = {r.return_pointee for r in records.values() if r.return_pointee}
    facts: dict[str, HandleFacts] = {}
    for name, r in records.items():
        f = HandleFacts(function=name)
        f.param_order = r.param_order
        f.handle_params = [p for p, tn in r.struct_ptr_params.items() if tn in returned]
        if r.return_pointee:
            f.role, f.handle_type = "creates", r.return_pointee
        else:
            destroyed = next((p for p in r.struct_ptr_params if p in r.freed), None)
            if destroyed is not None:
                f.role, f.handle_type, f.handle_param = "destroys", r.struct_ptr_params[destroyed], destroyed
            elif r.struct_ptr_params:
                p, tn = next(iter(r.struct_ptr_params.items()))
                f.role, f.handle_type, f.handle_param = "uses", tn, p
        facts[name] = f
    handle_types = returned
    kept = {fn: f for fn, f in facts.items() if f.role and f.handle_type in handle_types}
    return kept, handle_types


def analyze_handles(source: str | None = None, *, engine=None, path=None,
                    clang_args=None) -> tuple[dict[str, HandleFacts], set[str]]:
    if engine is not None:
        records = engine.handle_records(path, clang_args)
    else:
        records = _records_from_pycparser(source)
    return classify_records(records)


def apply_handle_facts(spec, facts: dict[str, HandleFacts]) -> list[str]:
    from ..spec.vocab import Role, Intent
    from ..spec.schema import Evidenced

    notes = []
    for fname, f in facts.items():
        fn = spec.functions.get(fname)
        if fn is None:
            continue
        fn.lifecycle = f.role
        fn.handle_type = f.handle_type
        notes.append(f"{fname}: {f.role} {f.handle_type}")
        marks = set(f.handle_params) | ({f.handle_param} if f.handle_param else set())

        resolved = set()
        spec_names = [p.name for p in fn.params]
        for m in marks:
            if any(p.name == m for p in fn.params):
                resolved.add(m)
                continue
            if f.param_order and m in f.param_order:
                idx = f.param_order.index(m)
                if idx < len(spec_names):
                    resolved.add(spec_names[idx])
                    notes.append(f"  (matched {fname}'s {m!r} to header param "
                                f"{spec_names[idx]!r} by position: names differ "
                                f"between declaration and definition)")

        for p in fn.params:
            if p.name in resolved:
                p.role = Role.HANDLE
                p.handle_type = f.handle_type
                p.intent = Evidenced(Intent.IN, ["handle_analysis"], 0.9, verified=False)
    return notes