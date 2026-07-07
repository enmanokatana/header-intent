"""
build a capability spec from already-extracted ctypes signatures.

Input is the dict our libclang/CAST parser already produces:
    { fname: {"argnames": [...], "argtypes": [ctypes...],
              "restype": ctype|None, "pointers": {argname: "out"} } }

Every fact is emitted as Evidenced. Sound signals (type, const-ness) get high
confidence; manual overrides are marked verified (the operator asserted them).
This layer reproduces today's behavior in spec form  no new inference risk.
"""

import ctypes

from ..spec.vocab import Intent, Role
from ..spec.schema import (
    Evidenced, ParamSpec, FunctionSpec, LibrarySpec, name_of_ctype,
)


def _is_pointer(ct) -> bool:
    return isinstance(ct, type) and issubclass(ct, ctypes._Pointer)


def _classify(name: str, ct, pointers: dict, override: dict) -> ParamSpec:
    # manual override  always wins (operator-asserted -> verified)
    if name in override:
        intent = Intent(override[name])          # "out" | "inout" | "in"
        if _is_pointer(ct):
            role, ctype = Role.SCALAR, name_of_ctype(ct._type_)
        elif ct is ctypes.c_char_p:
            role, ctype = Role.STRING, "c_char_p"
        else:
            role, ctype = Role.SCALAR, name_of_ctype(ct)
        return ParamSpec(name, role, Evidenced(intent, ["manual"], 1.0, verified=True), ctype)

    # strings: const char* -> c_char_p, definitely input
    if ct is ctypes.c_char_p:
        return ParamSpec(name, Role.STRING, Evidenced(Intent.IN, ["type"], 1.0, verified=True), "c_char_p")

    #pointers: rely on the const-based classifier's verdict
    if _is_pointer(ct):
        if pointers.get(name) == "out":
            return ParamSpec(name, Role.SCALAR,
                             Evidenced(Intent.OUT, ["const_ness"], 0.9, verified=False),
                             name_of_ctype(ct._type_))
        # unclassified pointer -> opaque, unknown intent (flagged for review)
        return ParamSpec(name, Role.OPAQUE,
                         Evidenced(Intent.IN, [], 0.0, verified=False),
                         "c_void_p")

    # 4. plain scalar -> input by value
    return ParamSpec(name, Role.SCALAR, Evidenced(Intent.IN, ["type"], 1.0, verified=True),
                     name_of_ctype(ct))


def spec_from_signatures(library: str, signatures: dict, overrides: dict | None = None) -> LibrarySpec:
    overrides = overrides or {}
    funcs = {}
    for fname, sig in signatures.items():
        ov = overrides.get(fname, {})
        params = [
            _classify(n, ct, sig.get("pointers", {}), ov)
            for n, ct in zip(sig["argnames"], sig["argtypes"])
        ]
        rt = sig["restype"]
        funcs[fname] = FunctionSpec(
            name=fname, params=params,
            restype=None if rt is None else name_of_ctype(rt),
        )
    return LibrarySpec(library=library, functions=funcs)