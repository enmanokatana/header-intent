import ctypes

from ..spec.vocab import Intent, Role
from ..spec.schema import (
    Evidenced, ParamSpec, FunctionSpec, LibrarySpec, name_of_ctype,
)


def _is_pointer(ct) -> bool:
    return isinstance(ct, type) and issubclass(ct, ctypes._Pointer)


def _classify(name: str, ct, pointers: dict, override: dict, out_handles: dict) -> ParamSpec:
    if name in out_handles:
        return ParamSpec(name, Role.OUT_HANDLE,
                         Evidenced(Intent.OUT, ["type"], 0.9, verified=False),
                         "c_void_p", by_ref=True, handle_type=out_handles[name])

    #manual override wins (operator-asserted -> verified)
    if name in override:
        intent = Intent(override[name])          # "out" | "inout" | "in"
        if _is_pointer(ct):
            role, ctype, by_ref = Role.SCALAR, name_of_ctype(ct._type_), True
        elif ct is ctypes.c_char_p:
            role, ctype, by_ref = Role.STRING, "c_char_p", False
        else:
            role, ctype, by_ref = Role.SCALAR, name_of_ctype(ct), False
        return ParamSpec(name, role, Evidenced(intent, ["manual"], 1.0, verified=True), ctype, by_ref)

    # strings: const char* -> c_char_p, definitely input
    if ct is ctypes.c_char_p:
        return ParamSpec(name, Role.STRING, Evidenced(Intent.IN, ["type"], 1.0, verified=True), "c_char_p")

    # pointers: rely on the const-based classifier's verdict
    if _is_pointer(ct):
        if pointers.get(name) == "out":
            return ParamSpec(name, Role.SCALAR,
                             Evidenced(Intent.OUT, ["const_ness"], 0.9, verified=False),
                             name_of_ctype(ct._type_), by_ref=True)
        # unclassified pointer -> opaque, unknown intent (flagged for review)
        return ParamSpec(name, Role.OPAQUE,
                         Evidenced(Intent.IN, [], 0.0, verified=False),
                         "c_void_p", by_ref=True)

    # raw void* can't be exposed safely as a value; opaque until a handle
    # analysis upgrades it (else the fail-safe guard refuses it).
    if ct is ctypes.c_void_p:
        return ParamSpec(name, Role.OPAQUE,
                         Evidenced(Intent.IN, [], 0.0, verified=False), "c_void_p")

    # 4. plain scalar -> input by value
    return ParamSpec(name, Role.SCALAR, Evidenced(Intent.IN, ["type"], 1.0, verified=True),
                     name_of_ctype(ct))


def spec_from_signatures(library: str, signatures: dict, overrides: dict | None = None,
                         out_handles: dict | None = None) -> LibrarySpec:
    overrides = overrides or {}
    out_handles = out_handles or {}
    funcs = {}
    for fname, sig in signatures.items():
        ov = overrides.get(fname, {})
        oh = out_handles.get(fname, {})
        params = [
            _classify(n, ct, sig.get("pointers", {}), ov, oh)
            for n, ct in zip(sig["argnames"], sig["argtypes"])
        ]
        rt = sig["restype"]
        handle_out = next((p.name for p in params if p.role is Role.OUT_HANDLE), None)
        fn = FunctionSpec(
            name=fname, params=params,
            restype=None if rt is None else name_of_ctype(rt),
        )
        if handle_out:
            fn.handle_out_param = handle_out
            fn.lifecycle = "creates"
            fn.owner = "caller"
            fn.handle_type = oh[handle_out]
        funcs[fname] = fn
    return LibrarySpec(library=library, functions=funcs)