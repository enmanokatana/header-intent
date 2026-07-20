"""
Pin down why cJSON_ParseWithOpts -> origin='unknown'.

It is structurally identical to cJSON_ParseWithLength (which now resolves), EXCEPT
it has TWO return statements:

    if (NULL == value) { return NULL; }        <- return #1
    ...
    return cJSON_ParseWithLengthOpts(...);     <- return #2  (the one that matters)

This prints every RETURN_STMT the walker finds, its tokens, and the origin computed
for it -- so we can see whether return #2 is being seen at all.

Run from ~/header-intent:
    python3 diag_returns.py
"""
from clang import cindex

from src.layers.libclang_engine import (LibclangEngine, _unwrap, _callee_name_of,
                                        _binop_is_assign)
from src.layers.l2_ownership import _is_alloc_name

SRC = "/tmp/cjson/cJSON.c"
ARGS = ["-I", "/tmp/cjson"]
TARGETS = ["cJSON_ParseWithOpts", "cJSON_ParseWithLength", "cJSON_Parse"]

tu = cindex.Index.create().parse(SRC, args=ARGS)


def txt(node, limit=70):
    t = " ".join(x.spelling for x in node.get_tokens())
    return (t[:limit] + "...") if len(t) > limit else t


for c in tu.cursor.walk_preorder():
    if c.kind != cindex.CursorKind.FUNCTION_DECL or not c.is_definition():
        continue
    if c.spelling not in TARGETS:
        continue

    print("=" * 78)
    print(f"FUNCTION: {c.spelling}")
    params = {a.spelling for a in c.get_arguments()}
    print(f"  params: {params}")

    returns = []
    for n in c.walk_preorder():
        if n.kind == cindex.CursorKind.RETURN_STMT:
            kids = list(n.get_children())
            returns.append(kids[0] if kids else None)

    print(f"  RETURN_STMTs found: {len(returns)}")
    for i, expr in enumerate(returns, 1):
        if expr is None:
            print(f"    [{i}] <bare return;>")
            continue
        u = _unwrap(expr)
        kind = u.kind if u is not None else None
        callee = ""
        if u is not None and u.kind == cindex.CursorKind.CALL_EXPR:
            callee = _callee_name_of(u)
        print(f"    [{i}] tokens : {txt(expr)}")
        print(f"        raw kind : {expr.kind}")
        print(f"        unwrapped: {kind}")
        if callee:
            print(f"        callee   : {callee!r}  is_alloc={_is_alloc_name(callee)}")
    print()
