from clang import cindex

from src.layers.libclang_engine import builtin_include_args
from src.models.extract import _out_handle_candidate

HEADER = "/tmp/sqlite3/sqlite3.h"
ARGS = builtin_include_args() + ["-I", "/tmp/sqlite3"]

TARGETS = ["sqlite3_open", "sqlite3_open_v2", "sqlite3_prepare_v2"]

idx = cindex.Index.create()
tu = idx.parse(HEADER, args=ARGS)

fatal = [d for d in tu.diagnostics if d.severity >= 4]
print("=== FATAL diagnostics ===")
print(fatal if fatal else "  (none)")
print()

for c in tu.cursor.walk_preorder():
    if c.kind != cindex.CursorKind.FUNCTION_DECL or c.spelling not in TARGETS:
        continue
    print("=" * 78)
    print(f"FUNCTION: {c.spelling}")
    for a in c.get_arguments():
        print(f"  param: {a.spelling!r}")
        t = a.type
        print(f"    raw type spelling      : {t.spelling}")
        canon = t.get_canonical()
        print(f"    canonical kind         : {canon.kind}")
        print(f"    canonical spelling     : {canon.spelling}")
        if canon.kind == cindex.TypeKind.POINTER:
            inner = canon.get_pointee()
            print(f"    pointee spelling       : {inner.spelling}")
            print(f"    pointee kind (raw)     : {inner.kind}")
            inner_canon = inner.get_canonical()
            print(f"    pointee canonical kind : {inner_canon.kind}")
            print(f"    pointee canonical spell: {inner_canon.spelling}")
            if inner_canon.kind == cindex.TypeKind.POINTER:
                struct_t = inner_canon.get_pointee()
                print(f"    struct_t spelling      : {struct_t.spelling}")
                print(f"    struct_t kind (raw)    : {struct_t.kind}")
                struct_canon = struct_t.get_canonical()
                print(f"    struct_t canonical kind: {struct_canon.kind}")
                decl = struct_t.get_declaration()
                print(f"    struct_t decl.spelling : {decl.spelling!r}")
        result = _out_handle_candidate(a.type)
        print(f"    _out_handle_candidate()  -> {result!r}")
    print()
