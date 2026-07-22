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
    sqlite3MallocZero, sqlite3DbMallocRaw no underscores at all). Whole-word
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

# TRANSFER heuristic: a function whose NAME suggests unlinking (not just reading)
# combined with STRUCTURAL evidence (it mutates a DIFFERENT parameter's structure)
# distinguishes cJSON_DetachItemViaPointer (returns `item` unchanged, but sets
# `parent->child = ...` a real unlink) from cJSON_GetObjectItem (returns
# `object->child`, pure read, no mutation anywhere). Name alone is not trusted;
# structural corroboration is required, per the project's fail-safe philosophy.
_TRANSFER_NAME_RE = re.compile(r"(detach|remove|take|extract|unlink|pop)", re.I)





@dataclass
class OwnRecord:
    """Engine-neutral extraction for one function that returns a pointer."""
    name: str
    returns_pointer: bool = False
    origin: str = UNKNOWN          # "alloc" | "param_member" | "param_direct:<n>" | "call:<fn>" | "unknown"
    escaped: bool = False          # returned value stored into a handle-typed param
    handle_params: list = field(default_factory=list)
    mutates_other_param: bool = False   # writes through a DIFFERENT param (unlink evidence)


@dataclass
class OwnFact:
    function: str
    owner: str                     # OWNED | BORROWED
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
        self.origin: dict[str, str] = {}          # local var -> origin tag
        self.returns: list = []                   # returned expressions
        self.calls: list = []                     # (callee, [arg root ids])
        self.mutated_param_roots: set[str] = set()  # params whose members were WRITTEN

    def _origin_of_expr(self, expr) -> str:
        if expr is None:
            return UNKNOWN
        e = expr
        while isinstance(e, c_ast.Cast):
            e = e.expr
        if isinstance(e, c_ast.FuncCall):
            cn = _callee_name(e.name)
            return "alloc" if _is_alloc_name(cn) else f"call:{cn}"
        if _is_member_expr(e):                    # p->child / cur->next  DERIVED
            root = _root_id(e)
            if root in self.params:
                return "param_member"             # object->child : into the caller's tree
            # traversal STAYS inside a borrowed structure: cur = cur->next keeps the
            # borrow (without this, a loop clobbers the taint and we lose the fact).
            if self.origin.get(root) in ("param_member", "param_direct"):
                return "param_member"
            return UNKNOWN
        if isinstance(e, c_ast.ID):
            if e.name in self.params:
                return f"param_direct:{e.name}"   # the parameter ITSELF, unchanged
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
            # a WRITE through a member access (p->field = ...) is evidence that
            # whichever parameter `p` traces back to was MUTATED the signal
            # that distinguishes an unlink (cJSON_DetachItemViaPointer sets
            # `parent->child = ...`) from a pure read.
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

        # Collect EVERY return's origin, then pick by priority (order-independent 
        # an early `return NULL;` guard must not hide the real return path).
        origins, ret_ids = [], []
        for expr in col.returns:
            if isinstance(expr, c_ast.Constant):
                continue
            origins.append(col._origin_of_expr(expr))
            rid = _root_id(expr)
            if rid:
                ret_ids.append(rid)

        if "param_member" in origins:
            rec.origin = "param_member"                # derived-from-param wins (fail-safe)
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

        # ESCAPE applies whenever the return is freshly PRODUCED here either a
        # direct alloc, or a call to a wrapper that allocates (cJSON_AddNullToObject
        # calls cJSON_CreateNull(), it does not malloc directly; gating this on
        # origin=="alloc" literally missed every Add*ToObject function, which is a
        # REAL regression: they were silently reclassified caller-owned instead of
        # BORROWED, a live double-free risk).
        #
        # The PRODUCER call itself must be excluded from the scan, or its own
        # arguments falsely look like an escape targe this is what caused the
        # ORIGINAL cJSON_Duplicate bug: `return dup_rec(item, hooks, recurse);`
        # walks `item` into ret_ids (it's inside the return expression's subtree),
        # and dup_rec's own args re-match against handle_params, making the
        # producer look like a consumer of its own output.  
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


# STRING ownership: does an OWNED (caller-must-free) char* come back, or a
# BORROWED/static one? Reuses the SAME origin-tracing machinery as pointer
# ownership above (it is type-agnostic), with a DELIBERATELY SIMPLER rule set:
# no escape rule, no transfer rule. A wrong verdict here means calling free()
# on a pointer we do not actually own heap corruption, not just a leak so
# only the highest-confidence signal (a return that traces cleanly to an
# allocation, with NO other complicating origin among the returns) is trusted.
# Everything else defaults to "do not free" (a small, bounded, safe leak),
# matching cJSON_Print's malloc'd buffer that this was built to address.
@dataclass
class StringOwnFact:
    function: str
    owns: bool              # True = caller (we) must free the returned buffer
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
        col = _OwnCollector(params, [])       # no handle_params: no escape rule for strings
        col.visit(fd.body)

        origins = []
        for expr in col.returns:
            if isinstance(expr, c_ast.Constant):     # a string literal return -> static, never free
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