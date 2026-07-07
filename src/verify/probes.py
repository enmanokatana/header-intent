"""
An inferred `out` fact is only trusted once the real function is observed
writing through the pointer. We call the function with a distinctive sentinel in
the out-cell and a benign, non-crashing set of other args; if the cell changes,
the write is confirmed.

This is intentionally conservative: it confirms "is written" (out or inout). It
runs in-process here for testing; in production it belongs in a sandboxed
subprocess with a guard allocator so a wrong guess crashes the probe, not the
host (see verify/sandbox.py).
"""
import ctypes

from ..spec.vocab import Intent, Role
from ..spec.schema import FunctionSpec, ctype_by_name

_SENTINEL = {
    ctypes.c_int: 0x7EED, ctypes.c_uint: 0x7EED,
    ctypes.c_long: 0x7EED, ctypes.c_ulong: 0x7EED, ctypes.c_longlong: 0x7EED,
    ctypes.c_short: 0x7E,
    ctypes.c_float: -12345.5, ctypes.c_double: -12345.5,
    ctypes.c_bool: True,
}

def _benign_input(base):
    # non-crashing default for a read/scalar arg; b=1 avoids divide-by-zero
    if base in (ctypes.c_float, ctypes.c_double):
        return 1.0
    return 1

def verify_out_params(lib, fn: FunctionSpec) -> dict[str, bool]:
    """For each param inferred out/inout, probe whether it's actually written.
    Returns {param_name: written?}. Skips functions with strings/opaque args
    (phase-1 probe only handles scalar signatures safely)."""
    if any(p.role in (Role.STRING, Role.OPAQUE, Role.HANDLE, Role.ARRAY) for p in fn.params):
        return {}

    argtypes = []
    for p in fn.params:
        base = ctype_by_name(p.ctype)
        argtypes.append(ctypes.POINTER(base) if p.intent.value in (Intent.OUT, Intent.INOUT) else base)
    cfn = getattr(lib, fn.name)
    cfn.argtypes = argtypes
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)

    cells, call_args = {}, []
    for p in fn.params:
        base = ctype_by_name(p.ctype)
        if p.intent.value in (Intent.OUT, Intent.INOUT):
            cell = base(_SENTINEL.get(base, 0x7EED))
            cells[p.name] = (cell, cell.value)
            call_args.append(ctypes.byref(cell))
        else:
            call_args.append(_benign_input(base))

    cfn(*call_args)
    return {name: (cell.value != sentinel) for name, (cell, sentinel) in cells.items()}


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