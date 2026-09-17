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


# ---------------------------------------------------------------------------
# Fixed-point cap error
# ---------------------------------------------------------------------------

class FixedPointNotReached(RuntimeError):
    """The lifecycle fixed point did not converge within the iteration cap.

    Returning a partial result here would be the same failure mode as analyzing a
    truncated parse: every layer above would compute a confident, internally
    consistent, WRONG answer. Fail loudly instead.
    """


MAX_FIXPOINT_ITERS = 10

# Observed iteration count from the last classify_records call, for the paper's
# reporting (Table VIII / fix F23).
LAST_FIXPOINT_ITERS = 0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HandleRecord:
    """Engine-neutral extraction for one function."""
    name: str
    return_pointee: str | None = None
    struct_ptr_params: dict = field(default_factory=dict)
    freed: set = field(default_factory=set)
    param_order: list = field(default_factory=list)
    forwards: dict = field(default_factory=dict)
    freed_conditional: set = field(default_factory=set)   # params freed only inside a branch


@dataclass
class HandleFacts:
    function: str
    role: str | None = None
    handle_type: str | None = None
    handle_param: str | None = None
    handle_params: list = field(default_factory=list)
    param_order: list = field(default_factory=list)
    evidence: str = "direct"        # direct | forwarded | conditional | forwarded+conditional
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

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
    """Collect freed parameter names, and record whether each free was reached
    unconditionally or only inside a branch.

    WHY: a free on an error path (`if (!ok) { png_destroy(p); return; }`) has the
    same AST shape as unconditional destruction, and classifying a repeatable
    read function as `destroys` because of its cleanup path is a latent
    use-after-free -- the handle table releases a handle the caller will use
    again. Without path sensitivity the analysis cannot tell these apart, so it
    must ABSTAIN rather than assert (see policy.check_exposable rule 0).
    """
    def __init__(self):
        self.freed_ids: set[str] = set()
        self.freed_conditional: set[str] = set()
        self._depth = 0                      # nesting inside If/Switch/loops

    @staticmethod
    def _callee_name(nm) -> str:
        if isinstance(nm, c_ast.ID):
            return nm.name
        if isinstance(nm, c_ast.StructRef):
            return nm.field.name
        return ""

    def _guarded(self, node):
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_If = _guarded
    visit_Switch = _guarded
    visit_While = _guarded
    visit_DoWhile = _guarded
    visit_For = _guarded
    visit_TernaryOp = _guarded

    def visit_FuncCall(self, node):
        if _is_dealloc_name(self._callee_name(node.name)):
            if node.args and node.args.exprs:
                last = node.args.exprs[-1]
                if isinstance(last, c_ast.ID):
                    self.freed_ids.add(last.name)
                    if self._depth > 0:
                        self.freed_conditional.add(last.name)
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


# ---------------------------------------------------------------------------
# Extraction (pycparser)
# ---------------------------------------------------------------------------

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
        freed_cond = {p for p in freed if p in ff.freed_conditional}
        fc = _ForwardCollector(set(struct_params) - freed)
        fc.visit(fd.body)
        recs[name] = HandleRecord(name, ret, struct_params, freed, param_order,
                                  fc.forwards, freed_cond)
    return recs


# ---------------------------------------------------------------------------
# Classification (engine-agnostic)
# ---------------------------------------------------------------------------

def classify_records(records: dict[str, HandleRecord],
                     *, max_iters: int = MAX_FIXPOINT_ITERS
                     ) -> tuple[dict[str, HandleFacts], set[str]]:
    global LAST_FIXPOINT_ITERS

    returned = {r.return_pointee for r in records.values() if r.return_pointee}
    facts: dict[str, HandleFacts] = {}
    for name, r in records.items():
        f = HandleFacts(function=name)
        f.param_order = r.param_order
        f.handle_params = [p for p, tn in r.struct_ptr_params.items() if tn in returned]
        if r.return_pointee:
            f.role, f.handle_type = "creates", r.return_pointee
            f.confidence, f.evidence = 1.0, "direct"
        else:
            destroyed = next((p for p in r.struct_ptr_params if p in r.freed), None)
            if destroyed is not None:
                conditional = destroyed in r.freed_conditional
                # A conditional free in a function whose own name says "destroy"
                # is still a destructor (png_destroy_read_struct guards on NULL);
                # a conditional free in a function whose name says nothing is an
                # error path until proven otherwise.
                if conditional and not _is_dealloc_name(name):
                    f.role = "uncertain_destroys"
                    f.evidence, f.confidence = "conditional", 0.4
                else:
                    f.role = "destroys"
                    f.confidence = 1.0 if not conditional else 0.8
                    f.evidence = "direct" if not conditional else "conditional"
                f.handle_type = r.struct_ptr_params[destroyed]
                f.handle_param = destroyed
            elif r.struct_ptr_params:
                p, tn = next(iter(r.struct_ptr_params.items()))
                f.role, f.handle_type, f.handle_param = "uses", tn, p
                f.confidence, f.evidence = 1.0, "direct"
        facts[name] = f

    # Fixed-point forwarding resolution.
    iters = 0
    for iters in range(1, max_iters + 1):
        changed = False
        for name, r in records.items():
            f = facts.get(name)
            # A function already classified as a direct destructor cannot be
            # upgraded further. But an uncertain_destroys CAN be upgraded by a
            # stronger forwarding path, and a `uses` can be promoted to
            # destroys/uncertain_destroys.
            if f is None or (f.role == "destroys" and f.evidence == "direct"):
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
                    if (callee_facts
                            and callee_facts.role in ("destroys", "uncertain_destroys")
                            and callee_facts.handle_param == callee_param
                            and callee_facts.handle_type == r.struct_ptr_params[pname]):
                        # Forwarding is evidence, not proof: we know the callee
                        # frees this type, not that this caller always reaches
                        # that call. The question is WHETHER THE FREE IS
                        # CONDITIONAL, not how many hops away it is — a chain
                        # of unconditional destructors is still unconditional
                        # regardless of depth. Check `evidence` (was any link
                        # in the chain conditional?) not `confidence` (how many
                        # hops?), because confidence < 0.8 is true for every
                        # forwarded fact, which would demote a two-hop
                        # unconditional chain like sqlite3_close → sqlite3Close
                        # → ...CloseZombie → free(db).
                        if (callee_facts.role == "uncertain_destroys"
                                or "conditional" in callee_facts.evidence):
                            new_role = "uncertain_destroys"
                            new_evidence = "forwarded+conditional"
                            new_conf = 0.4
                        else:
                            new_role = "destroys"
                            new_evidence = "forwarded"
                            new_conf = 0.6
                        # Only upgrade (uses -> destroys, uncertain -> certain),
                        # never downgrade.
                        if (f.role == "uses"
                                or (f.role == "uncertain_destroys"
                                    and new_role == "destroys")):
                            f.role = new_role
                            f.evidence = new_evidence
                            f.confidence = new_conf
                            f.handle_type = r.struct_ptr_params[pname]
                            f.handle_param = pname
                            changed = True
                            break
                if f.role in ("destroys", "uncertain_destroys") and f.evidence != "direct":
                    break
        if not changed:
            break
    else:
        # Loop was NOT broken -> fixed point did not converge.
        raise FixedPointNotReached(
            f"lifecycle forwarding did not converge in {max_iters} iterations "
            f"({len(records)} functions); results would be partial."
        )
    LAST_FIXPOINT_ITERS = iters

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


def analyze_handles_multi(paths, *, engine, clang_args=None):
    """Multi-file handle analysis. Merges the RAW HandleRecords across all files
    FIRST, then classifies once, so that lifecycle forwarding (a destructor
    reached only through a wrapper in another file) and the set of handed-out
    handle types both resolve across the whole library rather than per file.
    Returns (facts, handle_types, skipped_notes)."""
    from .libclang_engine import _merge_multi
    records, skipped = _merge_multi(engine, "handle_records", paths, clang_args)
    facts, types = classify_records(records)
    return facts, types, skipped