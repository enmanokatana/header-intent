import sys
import time

print("[1/5] starting...", flush=True)

from clang import cindex

print("[2/5] clang.cindex imported OK", flush=True)

from src.layers.libclang_engine import builtin_include_args, LibclangEngine

print("[3/5] ferrule imports OK", flush=True)

SOURCE = "/tmp/sqlite3/sqlite3.c"
ARGS = builtin_include_args() + ["-I", "/tmp/sqlite3"]
print("[4/5] parsing " + SOURCE + " (slow part -- full amalgamation)...", flush=True)

t0 = time.time()
try:
    tu = cindex.Index.create().parse(SOURCE, args=ARGS)
except Exception as e:
    print("PARSE FAILED after %.1fs: %s: %s" % (time.time() - t0, type(e).__name__, e), flush=True)
    sys.exit(1)
print("[5/5] parse finished in %.1fs" % (time.time() - t0), flush=True)

fatal = [d for d in tu.diagnostics if d.severity >= 4]
print("fatal diagnostics: %d" % len(fatal), flush=True)
for d in fatal[:5]:
    print("  " + str(d), flush=True)

print("", flush=True)
print("=== sqlite3_open / sqlite3_open_v2 / openDatabase: found? ===", flush=True)
targets = {"sqlite3_open", "sqlite3_open_v2", "openDatabase"}
found = set()
count = 0
for c in tu.cursor.walk_preorder():
    count += 1
    if c.kind == cindex.CursorKind.FUNCTION_DECL and c.spelling in targets and c.is_definition():
        found.add(c.spelling)
        print("  found definition: " + c.spelling, flush=True)
print("(walked %d cursors total; found: %s)" % (count, found), flush=True)

print("", flush=True)
print("=== running the actual out-handle analysis (candidates = sqlite3_open only) ===", flush=True)
t0 = time.time()
try:
    eng = LibclangEngine(ARGS)
    from src.layers.l2_out_handles import analyze_out_handles
    candidates = {"sqlite3_open": {"ppDb": "sqlite3"}}
    facts = analyze_out_handles(candidates=candidates, engine=eng, path=SOURCE, clang_args=ARGS)
    print("analysis finished in %.1fs" % (time.time() - t0), flush=True)
    for k, f in facts.items():
        if k[0] in ("sqlite3_open", "openDatabase"):
            print("  %r  confirmed=%s  %s" % (k, f.confirmed, f.reason), flush=True)
    if not facts:
        print("  (facts dict is EMPTY -- no candidates were found at all)", flush=True)
except Exception as e:
    print("ANALYSIS FAILED after %.1fs: %s: %s" % (time.time() - t0, type(e).__name__, e), flush=True)
    import traceback
    traceback.print_exc()

print("", flush=True)
print("DONE", flush=True)