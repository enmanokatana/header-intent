
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
    if any(p.role in (Role.STRING, Role.OPAQUE, Role.HANDLE, Role.ARRAY) for p in fn.params):
        return {}

    argtypes = []
    for p in fn.params:
        base = ctype_by_name(p.ctype)
        argtypes.append(ctypes.POINTER(base) if p.by_ref else base)
    cfn = getattr(lib, fn.name)
    cfn.argtypes = argtypes
    cfn.restype = None if fn.restype is None else ctype_by_name(fn.restype)

    out_params = [p for p in fn.params
                  if p.by_ref and p.intent.value in (Intent.OUT, Intent.INOUT)]
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