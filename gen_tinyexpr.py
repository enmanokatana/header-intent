import ctypes
from src.layers.l1_signature import spec_from_signatures
from src.layers.l2_handles import analyze_handles, apply_handle_facts
from src.layers.libclang_engine import LibclangEngine, handle_records_files
from src.layers.l2_handles import classify_records
from src.verify.probes import apply_verification
from src.spec.io import dump_yaml

SO   = "/tmp/tinyexpr/libtinyexpr.so"
LIBC = "/tmp/tinyexpr/tinyexpr.c"
SHIM = "/tmp/tinyexpr/te_shim.c"
ARGS = ["-I/tmp/tinyexpr"]

SIG = {
  "te_interp":    {"argnames": ["expression", "error"],
                   "argtypes": [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)],
                   "restype": ctypes.c_double, "pointers": {"error": "out"}},
  "compile_expr": {"argnames": ["expression"], "argtypes": [ctypes.c_char_p],
                   "restype": ctypes.c_void_p, "pointers": {}},
  "te_eval":      {"argnames": ["n"], "argtypes": [ctypes.c_void_p],
                   "restype": ctypes.c_double, "pointers": {}},
  "te_free":      {"argnames": ["n"], "argtypes": [ctypes.c_void_p],
                   "restype": None, "pointers": {}},
}

spec = spec_from_signatures("tinyexpr", SIG)

records = handle_records_files([LIBC, SHIM], ARGS)
facts, htypes = classify_records(records)
print("handle types:", htypes)
for n, f in facts.items():
    if f.role:
        print(f"  {n}: {f.role} {f.handle_type}")
apply_handle_facts(spec, facts)

apply_verification(ctypes.CDLL(SO), spec)
dump_yaml(spec, "tinyexpr.spec.yaml")
print("wrote tinyexpr.spec.yaml")