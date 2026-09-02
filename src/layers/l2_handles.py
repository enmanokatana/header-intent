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


_FREE_NAMES = {"free"}          # kept for back-compat; _is_dealloc_name is the real test


@dataclass
class HandleRecord:
    """Engine-neutral extraction for one function."""
    name: str
    return_pointee: str | None = None            # struct/typedef name if returns T*
    struct_ptr_params: dict = field(default_factory=dict)  # param -> type name
    freed: set = field(default_factory=set)      # params passed to free()
    param_order: list = field(default_factory=list)  # ALL param names, SOURCE order.
    # Needed because a header prototype and its .c definition can legally use
    # DIFFERENT parameter names (or the header may omit them entirely --
    # sqlite3.h declares many functions as `int sqlite3_close(sqlite3*);` with
    # no name at all, so L0 auto-names that param "a0"). Facts computed here
    # come from the SOURCE file's real names ("db"); apply_handle_facts must
    # fall back to matching by POSITION when the name itself doesn't match.
    forwards: dict = field(default_factory=dict)
    # {param_name: [(callee_name, callee_arg_index), ...]} -- every DIRECT
    # argument-position appearance of this param in a call within the body.
    # Needed because sqlite3_close forwards through TWO hops before the real
    # free (sqlite3_close -> sqlite3Close -> sqlite3LeaveMutexAndCloseZombie ->
    # sqlite3_free(db)), and the middle hop's body passes `db` directly to SIX
    # different helper calls, only one of which is the real closer -- a
    # single-hop or single-target forwarding rule (as used for out-param-handle
    # confirmation) is both too shallow and too strict for this idiom.


@dataclass
class HandleFacts:
    function: str
    role: str | None = None                       # creates | uses | destroys
    handle_type: str | None = None
    handle_param: str | None = None               # the one freed/used (destroys/uses)
    handle_params: list = field(default_factory=list)   # ALL handle-typed params
    param_order: list = field(default_factory=list)     # SOURCE-side param order (see HandleRecord)


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
            if node.args and node.args.exprs:
                # ONLY the LAST argument is the thing being freed -- see the
                # matching fix in libclang_engine.py's handle_records for why
                # (sqlite3DbFree(db, p): db is context, p is what's freed).
                last = node.args.exprs[-1]
                if isinstance(last, c_ast.ID):
                    self.freed_ids.add(last.name)
        self.generic_visit(node)


class _ForwardCollector(c_ast.NodeVisitor):
    """Every DIRECT argument-position appearance of any name in `names`, across
    every call in the function body -- used to resolve lifecycle classification
    through wrapper functions (see HandleRecord.forwards)."""
    def __init__(self, names: set[str]):
        self.names = names
        self.forwards: dict[str, list] = {n: [] for n in names}

    @staticmethod
    def _callee_name(nm) -> str:
        if isinstance(nm, c_ast.ID):
            return nm.name
        if isinstance(nm, c_ast.StructRef):
            return nm.field.name
        return ""

    def visit_FuncCall(self, node):
        callee = self._callee_name(node.name)
        if callee and node.args:
            for i, a in enumerate(node.args.exprs):
                if isinstance(a, c_ast.ID) and a.name in self.names:
                    self.forwards[a.name].append((callee, i))
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
        fc = _ForwardCollector(set(struct_params) - freed)
        fc.visit(fd.body)
        recs[name] = HandleRecord(name, ret, struct_params, freed, param_order, fc.forwards)
    return recs


# --------------------------------------------------------------------------
# engine-agnostic classification
# --------------------------------------------------------------------------
def classify_records(records: dict[str, HandleRecord]) -> tuple[dict[str, HandleFacts], set[str]]:
    returned = {r.return_pointee for r in records.values() if r.return_pointee}
    facts: dict[str, HandleFacts] = {}
    for name, r in records.items():
        f = HandleFacts(function=name)
        f.param_order = r.param_order
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

    # Fixed-point forward-resolution: a function whose body never directly frees
    # its handle param may still genuinely destroy it through one or more layers
    # of wrapper calls (sqlite3_close -> sqlite3Close -> sqlite3LeaveMutexAnd
    # CloseZombie -> sqlite3_free(db), a TWO-hop chain). Missing this is not
    # cosmetic: sqlite3_close would bind as "uses", our HandleTable would never
    # pop the handle after a REAL, successful C-level close, and reusing that
    # handle afterward would hand an already-freed pointer straight into C --
    # a genuine use-after-free, the opposite failure mode from the double-free
    # protection this whole ownership system exists to provide.
    #
    # The rule: if ANY callee that directly receives this param as an argument
    # (there may be several -- sqlite3Close passes `db` to six different
    # helpers, only one of which is the real closer) itself resolves, via this
    # same fixed point, to "destroys" at the matching parameter position,
    # promote this function to "destroys" too. This is grounded in an actual
    # verified chain reaching a real free() call, not a naming guess, so a
    # false positive would require an unrelated helper to ALSO transitively
    # free its own first argument for a completely different reason --
    # implausible for purpose-built helper functions, and even if it happened
    # the failure mode is benign (a handle gets invalidated a little early,
    # not a crash or corruption).
    for _ in range(10):
        changed = False
        for name, r in records.items():
            f = facts.get(name)
            if f is None or f.role == "destroys":
                continue
            for pname, targets in r.forwards.items():
                if pname not in r.struct_ptr_params:
                    continue
                for callee, arg_idx in targets:
                    callee_rec = records.get(callee)
                    if callee_rec is None or arg_idx >= len(callee_rec.param_order):
                        continue
                    callee_param = callee_rec.param_order[arg_idx]
                    callee_facts = facts.get(callee)
                    if (callee_facts and callee_facts.role == "destroys"
                            and callee_facts.handle_param == callee_param):
                        f.role = "destroys"
                        f.handle_type = r.struct_ptr_params[pname]
                        f.handle_param = pname
                        changed = True
                        break
                if f.role == "destroys":
                    break
        if not changed:
            break

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
    handle_type, and mark the handle param's role=HANDLE.

    NAME MISMATCH: sqlite3.h declares many functions WITHOUT parameter names
    (`int sqlite3_close(sqlite3*);`), so L0's header-based extraction auto-names
    that param "a0". This layer's facts come from the .c file's DEFINITION,
    which has the real name ("db"). A pure name match then silently fails for
    every such function -- the param stays OPAQUE and the whole function gets
    refused, even though the lifecycle was correctly determined. C guarantees
    declaration and definition share the same parameter COUNT and ORDER, so
    when the name isn't found, fall back to matching by position within
    `f.param_order` (the source's own ordering) against `fn.params` (the
    header's ordering) -- sound regardless of why the names differ.
    """
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

        # resolve each marked SOURCE name to a spec-side name: direct match first,
        # positional fallback second.
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