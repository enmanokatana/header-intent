from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pycparser import c_ast, c_parser, parse_file

from ..spec.vocab import Intent
from ..spec.schema import Evidenced


@dataclass
class FunctionAccesses:
    name: str
    pointer_params: list[str]
    events: list[tuple[str, str]]        
    escaped: set[str] = field(default_factory=set)   # params passed whole to a call


class SourceEngine(Protocol):
    def function_accesses(self, source: str) -> dict[str, FunctionAccesses]:
        """Map function name -> its pointer-param access trace."""
        ...


class _AccessCollector(c_ast.NodeVisitor):
    def __init__(self, params: set[str]):
        self.params = params
        self.events: list[tuple[str, str]] = []
        self.escaped: set[str] = set()

    def _target(self, node) -> str | None:
        if isinstance(node, c_ast.UnaryOp) and node.op == "*" \
                and isinstance(node.expr, c_ast.ID) and node.expr.name in self.params:
            return node.expr.name
        if isinstance(node, c_ast.ArrayRef) and isinstance(node.name, c_ast.ID) \
                and node.name.name in self.params:
            return node.name.name
        if isinstance(node, c_ast.StructRef) and isinstance(node.name, c_ast.ID) \
                and node.name.name in self.params:
            return node.name.name
        return None

    def visit_Assignment(self, node):
        self.visit(node.rvalue)                      
        tgt = self._target(node.lvalue)
        if tgt is not None:
            if node.op != "=":                        
                self.events.append((tgt, "read"))
            self.events.append((tgt, "write"))
            if isinstance(node.lvalue, c_ast.ArrayRef):
                self.visit(node.lvalue.subscript)     #
        else:
            self.visit(node.lvalue)

    def visit_UnaryOp(self, node):
        if node.op == "*" and isinstance(node.expr, c_ast.ID) and node.expr.name in self.params:
            self.events.append((node.expr.name, "read"))
            return
        self.generic_visit(node)

    def visit_ArrayRef(self, node):
        if isinstance(node.name, c_ast.ID) and node.name.name in self.params:
            self.events.append((node.name.name, "read"))
            self.visit(node.subscript)
            return
        self.generic_visit(node)

    def visit_StructRef(self, node):
        if isinstance(node.name, c_ast.ID) and node.name.name in self.params:
            self.events.append((node.name.name, "read"))
            return
        self.generic_visit(node)

    def visit_FuncCall(self, node):
        if node.args:
            for expr in node.args.exprs:
                if isinstance(expr, c_ast.ID) and expr.name in self.params:
                    self.escaped.add(expr.name)
        self.generic_visit(node)


def _pointer_params(fd: c_ast.FuncDef) -> list[str]:
    out = []
    args = fd.decl.type.args
    if args:
        for pd in args.params:
            if isinstance(pd, c_ast.Decl) and isinstance(pd.type, c_ast.PtrDecl) and pd.name:
                out.append(pd.name)
    return out


class PycparserEngine:
    def function_accesses(self, source: str) -> dict[str, FunctionAccesses]:
        ast = c_parser.CParser().parse(source)
        out = {}
        for node in ast.ext:
            if isinstance(node, c_ast.FuncDef):
                params = _pointer_params(node)
                if not params:
                    continue
                col = _AccessCollector(set(params))
                col.visit(node.body)
                out[node.decl.name] = FunctionAccesses(
                    node.decl.name, params, col.events, col.escaped)
        return out

    def function_accesses_file(self, path, cpp_args=None) -> dict[str, FunctionAccesses]:
        """Parse a real .c via the preprocessor (needs cpp + fake libc headers)."""
        ast = parse_file(path, use_cpp=True, cpp_args=cpp_args or [])
        text = ""  
        out = {}
        for node in ast.ext:
            if isinstance(node, c_ast.FuncDef):
                params = _pointer_params(node)
                if not params:
                    continue
                col = _AccessCollector(set(params))
                col.visit(node.body)
                out[node.decl.name] = FunctionAccesses(
                    node.decl.name, params, col.events, col.escaped)
        return out


def _intent_of(seq: list[str]) -> Intent | None:
    if not seq:
        return None
    if seq[0] == "write":
        return Intent.OUT
    if "write" in seq:
        return Intent.INOUT
    return Intent.IN


def l2_intents(source: str, engine: SourceEngine | None = None) -> dict[str, dict[str, Evidenced]]:
    """Return {func: {param: Evidenced[Intent]}} derived from source by def-use.
    Escaped params get lower confidence (intraprocedural view is incomplete)."""
    engine = engine or PycparserEngine()
    result: dict[str, dict[str, Evidenced]] = {}
    for fname, fa in engine.function_accesses(source).items():
        facts = {}
        for p in fa.pointer_params:
            seq = [kind for (n, kind) in fa.events if n == p]
            intent = _intent_of(seq)
            if intent is None:
                continue                             
            if p in fa.escaped:
                facts[p] = Evidenced(intent, ["def_use", "escape_unresolved"], 0.5, verified=False)
            else:
                facts[p] = Evidenced(intent, ["def_use"], 0.95, verified=False)
        if facts:
            result[fname] = facts
    return result


def l2_param_order(source: str, engine: SourceEngine | None = None) -> dict[str, list[str]]:
    engine = engine or PycparserEngine()
    return {fname: fa.pointer_params for fname, fa in engine.function_accesses(source).items()}