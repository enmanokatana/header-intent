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

_SENTINELS = {
    ctypes.c_int: (0x7EED, 0x5150), ctypes.c_uint: (0x7EED, 0x5150),
    ctypes.c_long: (0x7EED, 0x5150), ctypes.c_ulong: (0x7EED, 0x5150),
    ctypes.c_longlong: (0x7EED, 0x5150), ctypes.c_short: (0x7E, 0x51),
    ctypes.c_float: (-12345.5, 67890.25), ctypes.c_double: (-12345.5, 67890.25),
    ctypes.c_bool: (True, False),
}

def _benign_input(base):
    if base in (ctypes.c_float, ctypes.c_double):
        return 3.0
    return 3

def verify_out_params(lib, fn: FunctionSpec) -> dict[str, bool]:
    """For each param inferred out/inout, probe whether it's actually written.
    Returns {param_name: written?}. Skips functions with strings/opaque args
    (phase-1 probe only handles scalar signatures safely).

    CALLER_STATE and OUT_HANDLE are skipped for the same reason HANDLE is: the
    probe constructs zeroed scalar arguments, and calling a function like
    deflate() with a zeroed z_stream dereferences internal pointers the library
    wrote during init -- an instant segfault. Observed on zlib: the probe called
    deflate with a zeroed z_stream* and crashed the process.
    """
    if any(p.role in (Role.STRING, Role.OPAQUE, Role.HANDLE, Role.ARRAY,
                      Role.OUT_HANDLE, Role.CALLER_STATE) for p in fn.params):
        return {}

    argtypes = []
    for p in fn.params:
        base = ctype_by_name(p.ctype)
        argtypes.append(ctypes.POINTER(base) if p.by_ref else base)
    try:
        cfn = getattr(lib, fn.name)
    except AttributeError:
        return {}
    cfn.argtypes = argtypes
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)

    out_params = [p for p in fn.params if p.by_ref and p.intent.value in (Intent.OUT, Intent.INOUT)]
    if not out_params:
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
                call_args.append(ctypes.byref(base(_benign_input(base))))
            else:
                call_args.append(_benign_input(base))
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
                    p.intent.confidence *= 0.5