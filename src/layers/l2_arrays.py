"""
L2 array<->length pairing (Phase 2 slice 3).

Recovers the array-parameter idiom (PLDI'09): in f(const int *arr, int n), the
`n` is arr's length -- a fact NOT in the types. Two evidence signals:

  * loop-bound (strong): an index variable that subscripts the pointer is bounded
    by an int parameter in a for-condition (i < n). Confidence 0.9.
  * adjacency (weak): an int parameter immediately following the pointer.
    Confidence 0.6 -- a fallback when no loop bound is found.

Populates ParamSpec.role=ARRAY (with dimension=<length_param>) and the length
param role=LENGTH_OF. Only const/scalar element arrays are handled here; the
element type comes from the pointee.

pycparser engine below; a libclang path can be added behind the same shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pycparser import c_ast, c_parser


_INT_NAMES = ("int", "long", "short", "size_t", "unsigned", "uint32_t", "int32_t",
              "uint64_t", "int64_t", "ptrdiff_t")


@dataclass
class ArrayFact:
    function: str
    array_param: str
    length_param: str
    element: str                 # pointee type name (e.g. "int", "double")
    source: str                  # "loop_bound" | "adjacency"
    confidence: float


def _is_int_typedecl(node) -> bool:
    return isinstance(node, c_ast.TypeDecl) and isinstance(node.type, c_ast.IdentifierType) \
        and any(k in node.type.names for k in _INT_NAMES)


def _pointee_name(ptrdecl) -> str | None:
    inner = ptrdecl.type
    if isinstance(inner, c_ast.TypeDecl) and isinstance(inner.type, c_ast.IdentifierType):
        return " ".join(n for n in inner.type.names if n != "const")
    return None


class _Subscripts(c_ast.NodeVisitor):
    def __init__(self, ptrs):
        self.ptrs = set(ptrs)
        self.idx_vars: set[str] = set()

    def visit_ArrayRef(self, node):
        if isinstance(node.name, c_ast.ID) and node.name.name in self.ptrs:
            if isinstance(node.subscript, c_ast.ID):
                self.idx_vars.add(node.subscript.name)
        self.generic_visit(node)


class _LoopBounds(c_ast.NodeVisitor):
    def __init__(self):
        self.bounds: list[tuple[str, str]] = []      # (index_var, bound_var)

    def visit_For(self, node):
        cond = node.cond
        if isinstance(cond, c_ast.BinaryOp) and cond.op in ("<", "<="):
            if isinstance(cond.left, c_ast.ID) and isinstance(cond.right, c_ast.ID):
                self.bounds.append((cond.left.name, cond.right.name))
        self.generic_visit(node)


def analyze_arrays(source: str) -> dict[str, list[ArrayFact]]:
    ast = c_parser.CParser().parse(source)
    out: dict[str, list[ArrayFact]] = {}
    for fd in ast.ext:
        if not isinstance(fd, c_ast.FuncDef):
            continue
        args = fd.decl.type.args
        if not args:
            continue

        ptrs, ints, order, elem = [], [], [], {}
        for pd in args.params:
            if not isinstance(pd, c_ast.Decl):
                continue
            if isinstance(pd.type, c_ast.PtrDecl):
                nm = _pointee_name(pd.type)
                # only scalar-element arrays here (char* is a string; struct* is a handle)
                if nm and nm in ("int", "long", "short", "double", "float",
                                 "unsigned", "unsigned int", "size_t"):
                    ptrs.append(pd.name)
                    elem[pd.name] = nm
                    order.append(("ptr", pd.name))
                else:
                    order.append(("other", pd.name))
            elif _is_int_typedecl(pd.type):
                ints.append(pd.name)
                order.append(("int", pd.name))
            else:
                order.append(("other", pd.name))

        if not ptrs or not ints:
            continue

        subs = _Subscripts(ptrs); subs.visit(fd.body)
        lb = _LoopBounds(); lb.visit(fd.body)

        facts = []
        for aptr in ptrs:
            length, source, conf = None, None, 0.0
            # strong: loop bound whose index subscripts this pointer
            for idx, bound in lb.bounds:
                if idx in subs.idx_vars and bound in ints:
                    length, source, conf = bound, "loop_bound", 0.9
                    break
            # weak: an int immediately after this pointer in the signature
            if length is None:
                for i, (kind, name) in enumerate(order):
                    if kind == "ptr" and name == aptr and i + 1 < len(order) \
                            and order[i + 1][0] == "int":
                        length, source, conf = order[i + 1][1], "adjacency", 0.6
                        break
            if length is not None:
                facts.append(ArrayFact(fd.decl.name, aptr, length, elem[aptr], source, conf))
        if facts:
            out[fd.decl.name] = facts
    return out


def apply_array_facts(spec, arrays: dict[str, list[ArrayFact]]) -> list[str]:
    """Set array params role=ARRAY (dimension=length_param) and length params
    role=LENGTH_OF. Facts are unverified until a probe confirms them."""
    from ..spec.vocab import Role, Intent
    from ..spec.schema import Evidenced

    notes = []
    for fname, facts in arrays.items():
        fn = spec.functions.get(fname)
        if fn is None:
            continue
        for f in facts:
            for p in fn.params:
                if p.name == f.array_param:
                    p.role = Role.ARRAY
                    p.dimension = f.length_param
                    p.intent = Evidenced(Intent.IN, [f.source], f.confidence, verified=False)
                elif p.name == f.length_param:
                    p.role = Role.LENGTH_OF
                    p.dimension = f.array_param
            notes.append(f"{fname}: {f.array_param}[{f.length_param}] ({f.source})")
    return notes
