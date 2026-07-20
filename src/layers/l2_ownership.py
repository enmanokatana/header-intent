"""
L2 ownership inference (Phase 3 slice 1) -- creates vs BORROWED.

The gap cJSON forced. Handle analysis says "returns a T* => creates", but that
is unsound: cJSON_GetObjectItem returns a pointer INTO the tree you passed in.
It is owned by the parent; freeing it double-frees. Same for cJSON_AddNullToObject,
which allocates a node and then hands it to the parent object.

Ownership vocabulary is Shroud's (`owner: caller` | `owner: library`).

Rules (intraprocedural taint + escape, then a fixed point across the file):

  1. return traces to an ALLOCATION            -> OWNED    (owner=caller)
       cJSON_CreateObject: node = hooks->allocate(...); return node;
  2. return traces to a PARAMETER, or to a
     member/traversal rooted at a parameter    -> BORROWED (owner=library)
       get_object_item: current = object->child; ... return current;
  3. return is ALLOCATED but ESCAPES into a
     handle-typed parameter (passed to a call
     that also receives that parameter)        -> BORROWED (parent took ownership)
       cJSON_AddNullToObject: add_item_to_object(object, name, null); return null;
  4. return is a CALL to another function      -> propagate that function's verdict
       cJSON_Parse -> cJSON_ParseWithOpts -> cJSON_New_Item -> alloc  => OWNED
  5. anything else                             -> UNKNOWN  -> treated as BORROWED
                                                  (fail-safe: refuse to free)

Fail-safe direction matters: guessing BORROWED when it is really OWNED leaks
memory; guessing OWNED when it is really BORROWED double-frees. We always err
toward BORROWED.

KNOWN LIMITATION: cJSON_DetachItemViaPointer returns a *parameter* but the detach
semantically TRANSFERS ownership to the caller. Rule 2 marks it BORROWED, so it
leaks rather than crashes -- the safe error. Naming heuristics (L3) or an explicit
override can upgrade it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from pycparser import c_ast, c_parser

OWNED = "caller"
BORROWED = "library"
UNKNOWN = "unknown"

_ALLOC_RE = re.compile(r"(^|_)(malloc|calloc|realloc|strdup|alloc|allocate|new)($|_)", re.I)


def _is_alloc_name(name: str) -> bool:
    return bool(name) and bool(_ALLOC_RE.search(name))


@dataclass
class OwnRecord:
    """Engine-neutral extraction for one function that returns a pointer."""
    name: str
    returns_pointer: bool = False
    origin: str = UNKNOWN          # "alloc" | "param" | "call:<fn>" | "unknown"
    escaped: bool = False          # returned value stored into a handle-typed param
    handle_params: list = field(default_factory=list)


@dataclass
class OwnFact:
    function: str
    owner: str                     # OWNED | BORROWED
    reason: str
    confidence: float


# --------------------------------------------------------------------------
# pycparser extraction
# --------------------------------------------------------------------------
def _returns_struct_ptr(fd) -> bool:
    t = fd.decl.type.type            # fd.decl.type is the FuncDecl; .type is the return type
    if not isinstance(t, c_ast.PtrDecl):
        return False
    inner = t.type
    if isinstance(inner, c_ast.TypeDecl):
        ty = inner.type
        if isinstance(ty, c_ast.Struct):
            return True
        if isinstance(ty, c_ast.IdentifierType):
            return " ".join(ty.names) not in ("char", "void", "int", "float", "double",
                                              "unsigned char", "const char")
    return False


def _struct_ptr_params(fd) -> list[str]:
    out = []
    args = fd.decl.type.args
    if args:
        for pd in args.params:
            if isinstance(pd, c_ast.Decl) and isinstance(pd.type, c_ast.PtrDecl):
                inner = pd.type.type
                if isinstance(inner, c_ast.TypeDecl):
                    ty = inner.type
                    if isinstance(ty, c_ast.Struct):
                        out.append(pd.name)
                    elif isinstance(ty, c_ast.IdentifierType) and \
                            " ".join(ty.names) not in ("char", "void", "const char"):
                        out.append(pd.name)
    return out


def _root_id(node) -> str | None:
    """Root identifier of an expression: p, p->x, p->x->y, (T*)p ..."""
    n = node
    while n is not None:
        if isinstance(n, c_ast.ID):
            return n.name
        if isinstance(n, c_ast.StructRef):
            n = n.name
        elif isinstance(n, c_ast.Cast):
            n = n.expr
        elif isinstance(n, c_ast.UnaryOp):
            n = n.expr
        elif isinstance(n, c_ast.ArrayRef):
            n = n.name
        else:
            return None
    return None


def _is_member_expr(node) -> bool:
    n = node
    while isinstance(n, c_ast.Cast):
        n = n.expr
    return isinstance(n, c_ast.StructRef)


def _callee_name(nm) -> str:
    if isinstance(nm, c_ast.ID):
        return nm.name
    if isinstance(nm, c_ast.StructRef):
        return nm.field.name          # hooks->allocate(...)
    return ""


class _OwnCollector(c_ast.NodeVisitor):
    def __init__(self, params: list[str], handle_params: list[str]):
        self.params = set(params)
        self.handle_params = set(handle_params)
        self.origin: dict[str, str] = {}          # local var -> origin tag
        self.returns: list = []                   # returned expressions
        self.calls: list = []                     # (callee, [arg root ids])

    def _origin_of_expr(self, expr) -> str:
        if expr is None:
            return UNKNOWN
        e = expr
        while isinstance(e, c_ast.Cast):
            e = e.expr
        if isinstance(e, c_ast.FuncCall):
            cn = _callee_name(e.name)
            return "alloc" if _is_alloc_name(cn) else f"call:{cn}"
        if _is_member_expr(e):                    # p->child / cur->next
            root = _root_id(e)
            if root in self.params:
                return "param"                    # object->child : into the caller's tree
            # traversal STAYS inside a borrowed structure: cur = cur->next keeps the
            # borrow (without this, a loop clobbers the taint and we lose the fact).
            if self.origin.get(root) == "param":
                return "param"
            return UNKNOWN
        if isinstance(e, c_ast.ID):
            if e.name in self.params:
                return "param"
            return self.origin.get(e.name, UNKNOWN)
        return UNKNOWN

    def visit_Decl(self, node):
        if node.init is not None and node.name:
            self.origin[node.name] = self._origin_of_expr(node.init)
        self.generic_visit(node)

    def visit_Assignment(self, node):
        if node.op == "=" and isinstance(node.lvalue, c_ast.ID):
            self.origin[node.lvalue.name] = self._origin_of_expr(node.rvalue)
        self.generic_visit(node)

    def visit_Return(self, node):
        if node.expr is not None:
            self.returns.append(node.expr)
        self.generic_visit(node)

    def visit_FuncCall(self, node):
        roots = []
        if node.args:
            for a in node.args.exprs:
                r = _root_id(a)
                if r:
                    roots.append(r)
        self.calls.append((_callee_name(node.name), roots))
        self.generic_visit(node)


def _records_from_pycparser(source: str) -> dict[str, OwnRecord]:
    ast = c_parser.CParser().parse(source)
    recs: dict[str, OwnRecord] = {}
    for fd in ast.ext:
        if not isinstance(fd, c_ast.FuncDef):
            continue
        name = fd.decl.name
        rec = OwnRecord(name)
        if not _returns_struct_ptr(fd):
            recs[name] = rec
            continue
        rec.returns_pointer = True

        args = fd.decl.type.args
        params = [p.name for p in args.params
                  if isinstance(p, c_ast.Decl) and p.name] if args else []
        rec.handle_params = _struct_ptr_params(fd)

        col = _OwnCollector(params, rec.handle_params)
        col.visit(fd.body)

        # origin of the returned expression (prefer a non-NULL return)
        origin, ret_ids = UNKNOWN, []
        for expr in col.returns:
            o = col._origin_of_expr(expr)
            rid = _root_id(expr)
            if rid:
                ret_ids.append(rid)
            if o != UNKNOWN and not (isinstance(expr, c_ast.Constant)):
                origin = o
                if o != "alloc":
                    break
        rec.origin = origin

        # ESCAPE only applies to a pointer WE allocated here. If the return is a
        # call to another function, that callee's verdict governs (applying escape
        # there wrongly borrowed cJSON_Duplicate).
        if rec.origin == "alloc":
          for callee, roots in col.calls:
              if _is_alloc_name(callee):
                  continue
              if any(r in ret_ids for r in roots) and \
                 any(r in rec.handle_params for r in roots):
                  rec.escaped = True
                  break

        recs[name] = rec
    return recs


# --------------------------------------------------------------------------
# engine-agnostic fixed-point classification
# --------------------------------------------------------------------------
def classify_ownership(records: dict[str, OwnRecord]) -> dict[str, OwnFact]:
    verdict: dict[str, str] = {}

    def base(rec: OwnRecord) -> str | None:
        if not rec.returns_pointer:
            return None
        if rec.escaped:
            return BORROWED                    # rule 3: parent took ownership
        if rec.origin == "param":
            return BORROWED                    # rule 2
        if rec.origin == "alloc":
            return OWNED                       # rule 1
        return None                            # rule 4/5: needs propagation

    for n, r in records.items():
        b = base(r)
        if b:
            verdict[n] = b

    # fixed point over call propagation (rule 4)
    for _ in range(10):
        changed = False
        for n, r in records.items():
            if n in verdict or not r.returns_pointer:
                continue
            if r.origin.startswith("call:"):
                callee = r.origin.split(":", 1)[1]
                if callee in verdict:
                    verdict[n] = verdict[callee]
                    changed = True
        if not changed:
            break

    facts = {}
    for n, r in records.items():
        if not r.returns_pointer:
            continue
        if n in verdict:
            own = verdict[n]
            if r.escaped:
                reason, conf = "allocated then stored into a parameter (parent owns it)", 0.85
            elif r.origin == "param":
                reason, conf = "returns a pointer derived from an input parameter", 0.9
            elif r.origin == "alloc":
                reason, conf = "returns a freshly allocated pointer", 0.9
            else:
                reason, conf = f"propagated from {r.origin}", 0.8
        else:
            own, reason, conf = BORROWED, "ownership unresolved; fail-safe = do not free", 0.3
        facts[n] = OwnFact(n, own, reason, conf)
    return facts


def analyze_ownership(source: str | None = None, *, engine=None, path=None,
                      clang_args=None) -> dict[str, OwnFact]:
    if engine is not None:
        records = engine.ownership_records(path, clang_args)
    else:
        records = _records_from_pycparser(source)
    return classify_ownership(records)


def apply_ownership_facts(spec, facts: dict[str, OwnFact]) -> list[str]:
    """Set FunctionSpec.owner. A `creates` whose return is BORROWED is demoted to
    a borrowed-reference producer: the client may read it but never free it."""
    notes = []
    for fname, f in facts.items():
        fn = spec.functions.get(fname)
        if fn is None:
            continue
        fn.owner = f.owner
        if fn.lifecycle == "creates" and f.owner == BORROWED:
            fn.lifecycle = "borrows"          # NOT a fresh handle the caller may free
            notes.append(f"{fname}: creates -> BORROWS ({f.reason})")
        elif fn.lifecycle == "creates":
            notes.append(f"{fname}: creates (owner=caller)")
    return notes