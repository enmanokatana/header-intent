
from clang import cindex

from src.layers.libclang_engine import builtin_include_args

SOURCE = "/tmp/sqlite3/sqlite3.c"
ARGS = builtin_include_args() + ["-I", "/tmp/sqlite3"]

tu = cindex.Index.create().parse(SOURCE, args=ARGS)


def txt(node, limit=100):
    t = " ".join(x.spelling for x in node.get_tokens())
    return (t[:limit] + "...") if len(t) > limit else t


for c in tu.cursor.walk_preorder():
    if c.kind == cindex.CursorKind.FUNCTION_DECL and c.is_definition() and c.spelling == "openDatabase":
        print(f"=== openDatabase: full parameter list ===")
        for a in c.get_arguments():
            print(f"  {a.spelling!r}  type={a.type.spelling}")
        print()
        print(f"=== every VAR_DECL and assignment in openDatabase, source order ===")
        for n in c.walk_preorder():
            if n.kind == cindex.CursorKind.VAR_DECL:
                print(f"  VAR_DECL   : {txt(n)}")
            elif n.kind == cindex.CursorKind.BINARY_OPERATOR:
                kids = list(n.get_children())
                if len(kids) == 2:
                    # only show assignment-shaped ones (has an '=' token right after lhs)
                    toks = [t.spelling for t in n.get_tokens()]
                    if "=" in toks:
                        print(f"  ASSIGNMENT : {txt(n)}")
        break
else:
    print("openDatabase definition NOT FOUND in this translation unit "
         "(check it isn't named differently, e.g. static inline, or guarded by a macro)")
