"""Pin down why handle_types is empty: does L2 see png_create_read_struct's
return type at all, and does it survive the multi-file merge?"""
import sys, os
repo = os.path.expanduser("~/header-intent")
libs = os.path.expanduser("~/ferrule-libs")
sys.path.insert(0, repo)

from src.layers.libclang_engine import LibclangEngine
from src.layers.l2_handles import classify_records, analyze_handles_multi

args = [f"-I{libs}/libpng", f"-I{libs}/zlib"]
eng = LibclangEngine(args)

TARGETS = ("png_create_read_struct", "png_create_write_struct",
           "png_create_info_struct", "png_destroy_read_struct")

print("=== A. single file: pngread.c ===")
recs = eng.handle_records(f"{libs}/libpng/pngread.c", args)
print(f"records: {len(recs)}")
for t in TARGETS:
    r = recs.get(t)
    if r:
        print(f"  {t}: return_pointee={r.return_pointee!r} "
              f"struct_params={r.struct_ptr_params} freed={r.freed}")
    else:
        print(f"  {t}: NOT IN RECORDS")
returned = {r.return_pointee for r in recs.values() if r.return_pointee}
print(f"  handle types from this file: {sorted(returned)[:8]}")

print("\n=== B. same file, straight through classify_records ===")
facts, types = classify_records(recs)
print(f"  handle_types={sorted(types)[:8]}")
print(f"  kept facts={len(facts)}")
for t in TARGETS:
    if t in facts:
        f = facts[t]
        print(f"  {t}: role={f.role} type={f.handle_type} evidence={f.evidence}")

print("\n=== C. multi-file merge (the path the pipeline uses) ===")
paths = [f"{libs}/libpng/pngread.c", f"{libs}/libpng/pngwrite.c", f"{libs}/libpng/png.c"]
facts_m, types_m, skipped = analyze_handles_multi(paths, engine=eng, clang_args=args)
print(f"  handle_types={sorted(types_m)[:8]}")
print(f"  kept facts={len(facts_m)}")
print(f"  skipped={skipped}")

print("\n=== D. does any record anywhere have a return_pointee? ===")
from src.layers.libclang_engine import _merge_multi
merged, sk = _merge_multi(eng, "handle_records", paths, args)
print(f"  merged records: {len(merged)}")
with_ret = {k: v.return_pointee for k, v in merged.items() if v.return_pointee}
print(f"  records with a return_pointee: {len(with_ret)}")
for k, v in list(with_ret.items())[:10]:
    print(f"    {k} -> {v}")
if not with_ret:
    print("  >>> ZERO. L2 never resolves a struct-pointer return type.")
    print("  >>> handle_types is empty for that reason, not because of merging.")
