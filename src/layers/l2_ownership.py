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

def _tokenize_ident(name: str) -> list[str]:
    """Split a C identifier into words, handling BOTH naming conventions this
    project has had to support: snake_case (cJSON: hooks->allocate,
    sqlite3_malloc) and camelCase (sqlite3's actual INTERNAL convention:
    sqlite3MallocZero, sqlite3DbMallocRaw -- no underscores at all). Whole-word
    matching avoids substring false positives a boundary regex risks (e.g.
    "deallocate" must not look like it contains "allocate" as a real word).
    """
    words = []
    for chunk in name.split("_"):
        words.extend(re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", chunk))
    return [w.lower() for w in words if w]


_ALLOC_WORDS = {"malloc", "calloc", "realloc", "strdup", "alloc", "allocate", "new"}


def _is_alloc_name(name: str) -> bool:
    if not name:
        return False
    return any(w in _ALLOC_WORDS for w in _tokenize_ident(name))

_TRANSFER_NAME_RE = re.compile(r"(detach|remove|take|extract|unlink|pop)", re.I)





@dataclass
class OwnRecord:
    """Engine-neutral extraction for one function that returns a pointer."""
    name: str
    returns_pointer: bool = False
    origin: str = UNKNOWN
    escaped: bool = False
    handle_params: list = field(default_factory=list)
    mutates_other_param: bool = False


@dataclass
class OwnFact:
    function: str
    owner: str
    reason: str
    confidence: float


def _returns_struct_ptr(fd) -> bool:
    t = fd.decl.type.type
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
        return nm.field.name
    return ""


class _OwnCollector(c_ast.NodeVisitor):
    def __init__(self, params: list[str], handle_params: list[str]):
        self.params = set(params)
        self.handle_params = set(handle_params)
        self.origin: dict[str, str] = {}
        self.returns: list = []
        self.calls: list = []
        self.mutated_param_roots: set[str] = set()

    def _origin_of_expr(self, expr) -> str:
        if expr is None:
            return UNKNOWN
        e = expr
        while isinstance(e, c_ast.Cast):
            e = e.expr
        if isinstance(e, c_ast.FuncCall):
            cn = _callee_name(e.name)
            return "alloc" if _is_alloc_name(cn) else f"call:{cn}"
        if _is_member_expr(e):
            root = _root_id(e)
            if root in self.params:
                return "param_member"
            if self.origin.get(root) in ("param_member", "param_direct"):
                return "param_member"
            return UNKNOWN
        if isinstance(e, c_ast.ID):
            if e.name in self.params:
                return f"param_direct:{e.name}"
            return self.origin.get(e.name, UNKNOWN)
        return UNKNOWN

    def visit_Decl(self, node):
        if node.init is not None and node.name:
            self.origin[node.name] = self._origin_of_expr(node.init)
        self.generic_visit(node)

    def visit_Assignment(self, node):
        if node.op == "=" and isinstance(node.lvalue, c_ast.ID):
            self.origin[node.lvalue.name] = self._origin_of_expr(node.rvalue)
        elif _is_member_expr(node.lvalue):
            root = _root_id(node.lvalue)
            if root in self.params:
                self.mutated_param_roots.add(root)
            elif self.origin.get(root, "").startswith("param_direct:"):
                self.mutated_param_roots.add(self.origin[root].split(":", 1)[1])
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

        origins, ret_ids = [], []
        for expr in col.returns:
            if isinstance(expr, c_ast.Constant):
                continue
            origins.append(col._origin_of_expr(expr))
            rid = _root_id(expr)
            if rid:
                ret_ids.append(rid)

        if "param_member" in origins:
            rec.origin = "param_member"
        elif "alloc" in origins:
            rec.origin = "alloc"
        else:
            direct = [o for o in origins if o.startswith("param_direct:")]
            if direct:
                rec.origin = direct[0]
                pname = direct[0].split(":", 1)[1]
                rec.mutates_other_param = pname in col.mutated_param_roots
            else:
                calls = [o for o in origins if o.startswith("call:")]
                rec.origin = calls[0] if calls else UNKNOWN

        producer = rec.origin.split(":", 1)[1] if rec.origin.startswith("call:") else None
        if rec.origin == "alloc" or rec.origin.startswith("call:"):
          for callee, roots in col.calls:
              if _is_alloc_name(callee) or callee == producer:
                  continue
              if any(r in ret_ids for r in roots) and \
                 any(r in rec.handle_params for r in roots):
                  rec.escaped = True
                  break

        recs[name] = rec
    return recs


def classify_ownership(records: dict[str, OwnRecord]) -> dict[str, OwnFact]:
    verdict: dict[str, str] = {}

    def base(rec: OwnRecord) -> str | None:
        if not rec.returns_pointer:
            return None
        if rec.escaped:
            return BORROWED
        if rec.origin == "param_member":
            return BORROWED
        if rec.origin.startswith("param_direct:"):
            fname = rec.name
            if rec.mutates_other_param and _TRANSFER_NAME_RE.search(fname):
                return OWNED
            return None
        if rec.origin == "alloc":
            return OWNED
        return None

    for n, r in records.items():
        b = base(r)
        if b:
            verdict[n] = b

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
            elif r.origin == "param_member":
                reason, conf = "returns a pointer derived from an input parameter", 0.9
            elif r.origin.startswith("param_direct:") and own == OWNED:
                reason, conf = ("returns a parameter unchanged but unlinks it from "
                                "another structure (ownership transfer)"), 0.75
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
            fn.lifecycle = "borrows"
            notes.append(f"{fname}: creates -> BORROWS ({f.reason})")
        elif fn.lifecycle == "creates":
            notes.append(f"{fname}: creates (owner=caller)")
    return notes


@dataclass
class StringOwnFact:
    function: str
    owns: bool
    reason: str
    confidence: float


def _returns_char_ptr(fd) -> bool:
    t = fd.decl.type.type
    if not isinstance(t, c_ast.PtrDecl):
        return False
    inner = t.type
    if isinstance(inner, c_ast.TypeDecl) and isinstance(inner.type, c_ast.IdentifierType):
        return "char" in inner.type.names
    return False


def _string_records_from_pycparser(source: str) -> dict:
    ast = c_parser.CParser().parse(source)
    recs = {}
    for fd in ast.ext:
        if not isinstance(fd, c_ast.FuncDef):
            continue
        name = fd.decl.name
        if not _returns_char_ptr(fd):
            continue
        args = fd.decl.type.args
        params = [p.name for p in args.params
                  if isinstance(p, c_ast.Decl) and p.name] if args else []
        col = _OwnCollector(params, [])
        col.visit(fd.body)

        origins = []
        for expr in col.returns:
            if isinstance(expr, c_ast.Constant):
                origins.append("static")
                continue
            origins.append(col._origin_of_expr(expr))

        if "param_member" in origins or "unknown" in origins or "static" in origins:
            recs[name] = ("not_owned", "borrowed/static, or a return path we are not "
                                       "confident about (fail-safe: never free a "
                                       "pointer we might not own)")
        elif origins and all(o == "alloc" or o.startswith("call:") for o in origins):
            if all(o == "alloc" for o in origins):
                recs[name] = ("alloc", "returns a freshly allocated string")
            else:
                recs[name] = ("call", origins)
        else:
            recs[name] = ("not_owned", "ownership unresolved; fail-safe = do not free")
    return recs


def classify_string_ownership(records: dict) -> dict:
    verdict = {}
    for n, v in records.items():
        if v[0] == "alloc":
            verdict[n] = (True, v[1], 0.85)
        elif v[0] == "not_owned":
            verdict[n] = (False, v[1], 0.9 if "fail-safe" not in v[1] else 0.3)

    for _ in range(10):
        changed = False
        for n, v in records.items():
            if n in verdict or v[0] != "call":
                continue
            callees = [o.split(":", 1)[1] for o in v[1] if o.startswith("call:")]
            if callees and all(c in verdict for c in callees):
                owns = all(verdict[c][0] for c in callees)
                verdict[n] = (owns, f"propagated from {callees}", 0.75)
                changed = True
        if not changed:
            break

    facts = {}
    for n in records:
        if n in verdict:
            owns, reason, conf = verdict[n]
        else:
            owns, reason, conf = False, "ownership unresolved; fail-safe = do not free", 0.3
        facts[n] = StringOwnFact(n, owns, reason, conf)
    return facts


def analyze_string_ownership(source: str | None = None, *, engine=None, path=None,
                             clang_args=None) -> dict:
    if engine is not None:
        records = engine.string_ownership_records(path, clang_args)
    else:
        records = _string_records_from_pycparser(source)
    return classify_string_ownership(records)


def apply_string_ownership_facts(spec, facts: dict) -> list[str]:
    """Set FunctionSpec.string_owner for functions returning char*."""
    notes = []
    for fname, f in facts.items():
        fn = spec.functions.get(fname)
        if fn is None or fn.restype != "c_char_p":
            continue
        fn.string_owner = "caller" if f.owns else "library"
        if f.owns:
            notes.append(f"{fname}: returns an OWNED string (will be auto-freed after copy) -- {f.reason}")
    return notes


def analyze_ownership_multi(paths, *, engine, clang_args=None):
    """Multi-file ownership analysis.

    Merges the RAW ownership records across all files FIRST, then runs
    classify_ownership once over the union. Because classify_ownership's
    call-propagation fixed point operates over whatever record set it is given,
    a call chain that crosses files DOES resolve here: a caller in a.c whose
    return origin is `call:g` finds g's record even when g is defined in b.c.
    The residual limit is deeper cross-file EVIDENCE (e.g. a per-file record that
    was itself classified `unknown` because the callee's allocator was invisible
    within that file) -- those stay fail-safe. Returns (facts, skipped_notes).
    """
    from .libclang_engine import _merge_multi
    records, skipped = _merge_multi(engine, "ownership_records", paths, clang_args)
    return classify_ownership(records), skipped


def analyze_string_ownership_multi(paths, *, engine, clang_args=None):
    """Multi-file string-ownership analysis: union per-file records, then
    classify once. A returned string's ownership is decided within its own
    function body, so a plain union across files is complete (no cross-file
    chain, unlike pointer ownership). MUST classify the merged raw records (the
    single-file path calls classify_string_ownership); returning the raw
    (verdict, reason) tuples unclassified is what caused apply_* to choke on a
    'tuple has no attribute owns'. Returns (facts, skipped_notes)."""
    from .libclang_engine import _merge_multi
    records, skipped = _merge_multi(engine, "string_ownership_records", paths, clang_args)
    return classify_string_ownership(records), skipped