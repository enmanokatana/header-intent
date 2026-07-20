"""
L2 handle-lifecycle analysis (Phase 2 slice 2).

Recovers create/use/destroy from source (PLDI'09 "resource manager" idiom;
APISan-style alloc/free pairing):

  * creates  -- a function whose RETURN type is a pointer to a struct/typedef T
  * destroys -- a function taking T* whose body calls free() on that param
  * uses     -- a function taking T* that is neither of the above

A type T is a HANDLE only if some function returns it as a pointer (the library
hands it out for the caller to hold).

Extraction is engine-specific (pycparser here; a libclang engine avoids the
cpp/fake-header preprocessing -- see libclang_engine.py). Classification is
engine-agnostic and shared.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pycparser import c_ast, c_parser


import re as _re

# A deallocator may be free(), a custom name (cJSON_free), or a FUNCTION POINTER
# reached through a hooks struct: global_hooks.deallocate(item)  <- cJSON does this.
# Matching only "free" missed cJSON_Delete entirely (it derived as `uses`, leaving
# a dangling handle after delete). Match the dealloc FAMILY by name instead.
_DEALLOC_RE = _re.compile(r"(^|_)(free|dealloc|deallocate|destroy|delete|release|dispose)($|_)", _re.I)


def _is_dealloc_name(name: str) -> bool:
    return bool(name) and bool(_DEALLOC_RE.search(name))


_FREE_NAMES = {"free"}          # kept for back-compat; _is_dealloc_name is the real test


@dataclass
class HandleRecord:
    """Engine-neutral extraction for one function."""
    name: str
    return_pointee: str | None = None            # struct/typedef name if returns T*
    struct_ptr_params: dict = field(default_factory=dict)  # param -> type name
    freed: set = field(default_factory=set)      # params passed to free()


@dataclass
class HandleFacts:
    function: str
    role: str | None = None                       # creates | uses | destroys
    handle_type: str | None = None
    handle_param: str | None = None               # the one freed/used (destroys/uses)
    handle_params: list = field(default_factory=list)   # ALL handle-typed params


# --------------------------------------------------------------------------
# pycparser extraction
# --------------------------------------------------------------------------
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
            return nm.name                       # free(p)
        if isinstance(nm, c_ast.StructRef):
            return nm.field.name                 # hooks.deallocate(p) / hooks->free(p)
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
        if funcdecl.args:
            for pd in funcdecl.args.params:
                if isinstance(pd, c_ast.Decl):
                    tn = _pointee_typename(pd.type)
                    if tn:
                        struct_params[pd.name] = tn
        ff = _FreeFinder()
        ff.visit(fd.body)
        freed = {p for p in struct_params if p in ff.freed_ids}
        recs[name] = HandleRecord(name, ret, struct_params, freed)
    return recs


# --------------------------------------------------------------------------
# engine-agnostic classification
# --------------------------------------------------------------------------
def classify_records(records: dict[str, HandleRecord]) -> tuple[dict[str, HandleFacts], set[str]]:
    returned = {r.return_pointee for r in records.values() if r.return_pointee}
    facts: dict[str, HandleFacts] = {}
    for name, r in records.items():
        f = HandleFacts(function=name)
        # every param that is a pointer to a handed-out type is a handle input
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
    """Derive handle lifecycle facts.
    - default: pycparser on preprocessed `source` text.
    - engine given (e.g. LibclangEngine): extract from `path` directly (no cpp)."""
    if engine is not None:
        records = engine.handle_records(path, clang_args)
    else:
        records = _records_from_pycparser(source)
    return classify_records(records)


def apply_handle_facts(spec, facts: dict[str, HandleFacts]) -> list[str]:
    """Upgrade the spec with handle lifecycle: set FunctionSpec.lifecycle /
    handle_type, and mark the handle param's role=HANDLE."""
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
        # mark EVERY handle-typed param (not just the freed one): a `creates` that
        # also TAKES a handle (cJSON_GetObjectItem(object, key)) must bind that
        # input as a handle id, not a raw int.
        marks = set(f.handle_params) | ({f.handle_param} if f.handle_param else set())
        for p in fn.params:
            if p.name in marks:
                p.role = Role.HANDLE
                p.handle_type = f.handle_type
                p.intent = Evidenced(Intent.IN, ["handle_analysis"], 0.9, verified=False)
    return notes