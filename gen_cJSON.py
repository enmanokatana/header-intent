import ctypes
from src.layers.l1_signature import spec_from_signatures
from src.layers.l2_handles import analyze_handles, apply_handle_facts
from src.layers.libclang_engine import LibclangEngine, handle_records_files
from src.layers.l2_handles import classify_records
from src.verify.probes import apply_verification
from src.spec.io import dump_yaml

# Ensure this matches the name of the .so file you generated
SO   = "/tmp/cJSON/libcjson.so" 
LIBC = "/tmp/cJSON/cJSON.c"
ARGS = ["-I/tmp/cJSON"]

# L0/L1 signatures for the core cJSON functions we expose
# cJSON struct pointers are treated as c_void_p handles.
SIG = {
  "cJSON_Parse": {
      "argnames": ["value"],
      "argtypes": [ctypes.c_char_p],
      "restype": ctypes.c_void_p,  # Returns cJSON *
      "pointers": {}
  },
  "cJSON_Print": {
      "argnames": ["item"],
      "argtypes": [ctypes.c_void_p], # Accepts cJSON *
      "restype": ctypes.c_char_p,    # Returns char * (JSON string)
      "pointers": {}
  },
  "cJSON_Delete": {
      "argnames": ["item"],
      "argtypes": [ctypes.c_void_p], # Accepts cJSON *
      "restype": None,               # void return
      "pointers": {}
  },
  "cJSON_GetArraySize": {
      "argnames": ["array"],
      "argtypes": [ctypes.c_void_p], # Accepts cJSON *
      "restype": ctypes.c_int,       # Returns int
      "pointers": {}
  }
}

# Change project name to cjson
spec = spec_from_signatures("cjson", SIG)

# Handle lifecycle from the cJSON source file via libclang
# Removed SHIM here assuming you don't have a cJSON_Shim.c
records = handle_records_files([LIBC], ARGS)
facts, htypes = classify_records(records)

print("handle types:", htypes)
for n, f in facts.items():
    if f.role:
        print(f"  {n}: {f.role} {f.handle_type}")

apply_handle_facts(spec, facts)

# verify out-params against the real .so, then save
apply_verification(ctypes.CDLL(SO), spec)

# Save to a new cjson yaml file
dump_yaml(spec, "cjson.spec.yaml")
print("wrote cjson.spec.yaml")