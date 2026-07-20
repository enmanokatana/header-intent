"""
Diagnose the ownership extraction on cJSON's parse chain.

Bug: cJSON_Parse -> "ownership unresolved" (should be creates/owner=caller),
even though cJSON_ParseWithLengthOpts resolved to OWNED. The chain is:

    cJSON_Parse -> cJSON_ParseWithOpts -> cJSON_ParseWithLengthOpts -> cJSON_New_Item(alloc)

so the propagation should reach it. This prints the RAW extracted record for each
link so we can see where it breaks.

Run from ~/header-intent:
    python3 diag_ownership.py
"""
from src.layers.libclang_engine import LibclangEngine
from src.layers.l2_ownership import classify_ownership, _is_alloc_name

SRC = "/tmp/cjson/cJSON.c"
ARGS = ["-I", "/tmp/cjson"]

CHAIN = [
    "cJSON_New_Item",
    "cJSON_ParseWithLengthOpts",
    "cJSON_ParseWithOpts",
    "cJSON_ParseWithLength",
    "cJSON_Parse",
    "cJSON_Duplicate",
    "cJSON_GetObjectItem",
    "cJSON_SetValuestring",
    "cJSON_DeleteItemFromArray",
]

eng = LibclangEngine(ARGS)
recs = eng.ownership_records(SRC, ARGS)

print("=== RAW OWNERSHIP RECORDS (what the extractor saw) ===")
for name in CHAIN:
    r = recs.get(name)
    if r is None:
        print(f"  {name:34} <NOT FOUND in records>")
        continue
    print(f"  {name:34} returns_ptr={r.returns_pointer}  origin={r.origin!r}  "
          f"escaped={r.escaped}  handle_params={r.handle_params}")

print()
print("=== is_alloc_name check ===")
for n in ("cJSON_New_Item", "malloc", "global_hooks.allocate", "allocate", "cJSON_ParseWithLengthOpts"):
    print(f"  _is_alloc_name({n!r}) = {_is_alloc_name(n)}")

print()
print("=== CLASSIFIED VERDICTS ===")
facts = classify_ownership(recs)
for name in CHAIN:
    f = facts.get(name)
    if f:
        print(f"  {name:34} owner={f.owner:8} conf={f.confidence}  {f.reason}")

print()
print("=== handle_records: which params are seen as FREED (spurious destroys?) ===")
hrecs = eng.handle_records(SRC, ARGS)
for name in ("cJSON_Delete", "cJSON_SetValuestring", "cJSON_DeleteItemFromArray",
             "cJSON_ReplaceItemViaPointer"):
    r = hrecs.get(name)
    if r:
        print(f"  {name:34} freed={r.freed}  struct_params={list(r.struct_ptr_params)}")
