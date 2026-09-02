"""
Show, for a real library header, which FUNCTION_DECLs the header-scoping filter
KEEPS vs REJECTS, and from which file. This tells us conclusively whether the
library's own functions are being extracted.

Run from the Ferrule repo root:
    python3 eval/diag_extract.py /tmp/ferrule-eval/zlib/zlib.h
    python3 eval/diag_extract.py /tmp/ferrule-eval/libgit2/include/git2.h -I /tmp/ferrule-eval/libgit2/include
"""
import os, sys
sys.path.insert(0, os.path.abspath("."))
from clang import cindex
from src.layers.libclang_engine import builtin_include_args

header = sys.argv[1]
extra = []
i = 2
while i < len(sys.argv):
    if sys.argv[i] == "-I":
        extra += ["-I", sys.argv[i + 1]]; i += 2
    else:
        i += 1

args = builtin_include_args() + extra
tu = cindex.Index.create().parse(header, args=args)

# replicate the NEW _in_library filter exactly
_SYS_ROOTS = ("/usr/include", "/usr/lib", "/usr/local/include",
              "/usr/lib/llvm", "/usr/lib/gcc")
_target_real = os.path.realpath(os.path.abspath(header))
_target_dir = os.path.dirname(_target_real)

def in_library(cursor):
    loc = cursor.location; f = loc.file
    if f is None: return False
    try:
        if loc.is_in_system_header: return False
    except AttributeError:
        pass
    path = os.path.realpath(os.path.abspath(f.name))
    if any(path.startswith(os.path.realpath(r)) for r in _SYS_ROOTS): return False
    return path == _target_real or path.startswith(_target_dir + os.sep)

kept = rejected = 0
kept_names = []
for c in tu.cursor.walk_preorder():
    if c.kind != cindex.CursorKind.FUNCTION_DECL: continue
    if in_library(c):
        kept += 1
        if len(kept_names) < 40: kept_names.append(c.spelling)
    else:
        rejected += 1

print(f"target: {_target_real}")
print(f"KEPT (library):   {kept}")
print(f"REJECTED (system): {rejected}")
print()
print("first kept function names:")
for n in kept_names:
    print("  ", n)
if kept == 0:
    print("\n!! ZERO kept -- the library's own decls are being rejected. Paste this output.")