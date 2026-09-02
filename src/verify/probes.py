"""
Behavioral verification (phase-1 slice: out-param probes).

An inferred `out` fact is only trusted once the real function is observed
writing through the pointer. We call the function with a distinctive sentinel in
the out-cell and a benign, non-crashing set of other args; if the cell changes,
the write is confirmed.

This is intentionally conservative: it confirms "is written" (out or inout). It
runs in-process here for testing; in production it belongs in a sandboxed
subprocess with a guard allocator so a wrong guess crashes the probe, not the
host (see verify/sandbox.py, phase 2).
"""
import ctypes

from ..spec.vocab import Intent, Role
from ..spec.schema import FunctionSpec, ctype_by_name

# two distinct sentinels per type: run the probe twice so an identity op or a
# sentinel that happens to equal the written value can't mask a real write.
_SENTINELS = {
    ctypes.c_int: (0x7EED, 0x5150), ctypes.c_uint: (0x7EED, 0x5150),
    ctypes.c_long: (0x7EED, 0x5150), ctypes.c_ulong: (0x7EED, 0x5150),
    ctypes.c_longlong: (0x7EED, 0x5150), ctypes.c_short: (0x7E, 0x51),
    ctypes.c_float: (-12345.5, 67890.25), ctypes.c_double: (-12345.5, 67890.25),
    ctypes.c_bool: (True, False),
}

def _benign_input(base):
    # 3 avoids identity elements (*1, +0, /1) that would hide a write, and
    # avoids divide-by-zero.
    if base in (ctypes.c_float, ctypes.c_double):
        return 3.0
    return 3

def verify_out_params(lib, fn: FunctionSpec) -> dict[str, bool]:
    """For each param inferred out/inout, probe whether it's actually written.
    Returns {param_name: written?}. Skips functions with strings/opaque args
    (phase-1 probe only handles scalar signatures safely)."""
    if any(p.role in (Role.STRING, Role.OPAQUE, Role.HANDLE, Role.ARRAY) for p in fn.params):
        return {}

    argtypes = []
    for p in fn.params:
        base = ctype_by_name(p.ctype)
        argtypes.append(ctypes.POINTER(base) if p.by_ref else base)
    try:
        cfn = getattr(lib, fn.name)
    except AttributeError:
        # The extracted name is not an exported symbol in this .so. This happens
        # when a header declares something libclang sees as a function but the
        # library does not actually export: a macro/alias (zlib's compressBound_z,
        # deflateBound_z), a static inline, or a symbol gated out of this build.
        # Verification simply cannot probe it; leave it unverified (the fail-safe
        # already treats an unverified out-param conservatively) rather than
        # crashing the whole run. NOTE: ctypes falls through to the main-program
        # symbol table on a miss, so the raised message may name an unrelated
        # missing symbol (e.g. __bswap_16) -- the real cause is that fn.name
        # itself is absent from this library.
        return {}
    cfn.argtypes = argtypes
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)

    out_params = [p for p in fn.params if p.by_ref and p.intent.value in (Intent.OUT, Intent.INOUT)]
    if not out_params:
        # Nothing to verify -- there is no out/inout param whose write we could
        # confirm. The probe exists ONLY to answer "does this pointer get
        # written"; calling the real function anyway, purely because its
        # signature happened to be all-scalar, has zero information to gain and
        # real risk: sqlite3_hard_heap_limit64(n) takes n BY VALUE (no out
        # params at all) but sets a GLOBAL, PERSISTENT memory ceiling as a side
        # effect. Probing it with a sentinel like 0x5150 (~20KB) permanently
        # capped the process's allocator, so every later sqlite3_open failed
        # with SQLITE_NOMEM -- not a bug in that one function, a gap in the
        # probe methodology: it assumed "all-scalar signature" implies "safe
        # to call with synthetic values," which held for cJSON's stateless API
        # but not for sqlite3's global configuration functions.
        return {}

    written = {p.name: False for p in out_params}

    for run in (0, 1):
        cells, call_args = {}, []
        for p in fn.params:
            base = ctype_by_name(p.ctype)
            if p.by_ref and p.intent.value in (Intent.OUT, Intent.INOUT):
                s = _SENTINELS.get(base, (0x7EED, 0x5150))[run]
                cell = base(s)
                cells[p.name] = (cell, s)
                call_args.append(ctypes.byref(cell))
            elif p.by_ref:
                call_args.append(ctypes.byref(base(_benign_input(base))))  # in-by-ref: valid address
            else:
                call_args.append(_benign_input(base))                       # by value
        cfn(*call_args)
        for name, (cell, sentinel) in cells.items():
            if cell.value != sentinel:
                written[name] = True

    return written


def apply_verification(lib, spec) -> None:
    """Run probes and set `verified=True` on out/inout facts confirmed written;
    downgrade (verified stays False, confidence halved) if not observed."""
    for fn in spec.functions.values():
        written = verify_out_params(lib, fn)
        for p in fn.params:
            if p.name in written:
                if written[p.name]:
                    p.intent.verified = True
                    if "behavioral_probe" not in p.intent.sources:
                        p.intent.sources.append("behavioral_probe")
                else:
                    p.intent.confidence *= 0.5   # inferred out but not observed writing