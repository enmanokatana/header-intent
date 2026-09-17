import ctypes

from ..spec.vocab import Intent, Role
from ..spec.schema import (
    Evidenced, ParamSpec, FunctionSpec, LibrarySpec, name_of_ctype,
)


def _is_pointer(ct) -> bool:
    return isinstance(ct, type) and issubclass(ct, ctypes._Pointer)


def _classify(name: str, ct, pointers: dict, override: dict, out_handles: dict,
              struct_ptrs: dict) -> ParamSpec:
    """Classify one parameter from its type alone.

    `struct_ptrs` is L0's {argname: struct_name} for `T*` parameters. The
    classification is UNCHANGED by it -- a struct pointer is still OPAQUE here,
    because at L1 we know only the shape, not whether the library manages the
    type. What changes is that the name is RECORDED on the ParamSpec instead of
    discarded, so l2_handle_propagation can later ask whether this library hands
    that type out. Preserving evidence is not the same as acting on it.
    """
    if name in out_handles:
        return ParamSpec(name, Role.OUT_HANDLE,
                         Evidenced(Intent.OUT, ["type"], 0.9, verified=False),
                         "c_void_p", by_ref=True, handle_type=out_handles[name],
                         pointee=out_handles[name])

    if name in override:
        intent = Intent(override[name])
        if _is_pointer(ct):
            role, ctype, by_ref = Role.SCALAR, name_of_ctype(ct._type_), True
        elif ct is ctypes.c_char_p:
            role, ctype, by_ref = Role.STRING, "c_char_p", False
        else:
            role, ctype, by_ref = Role.SCALAR, name_of_ctype(ct), False
        return ParamSpec(name, role, Evidenced(intent, ["manual"], 1.0, verified=True),
                         ctype, by_ref, pointee=struct_ptrs.get(name))

    if ct is ctypes.c_char_p:
        return ParamSpec(name, Role.STRING,
                         Evidenced(Intent.IN, ["type"], 1.0, verified=True), "c_char_p")

    if _is_pointer(ct):
        if pointers.get(name) == "out":
            return ParamSpec(name, Role.SCALAR,
                             Evidenced(Intent.OUT, ["const_ness"], 0.9, verified=False),
                             name_of_ctype(ct._type_), by_ref=True)
        return ParamSpec(name, Role.OPAQUE,
                         Evidenced(Intent.IN, [], 0.0, verified=False),
                         "c_void_p", by_ref=True, pointee=struct_ptrs.get(name))

    if ct is ctypes.c_void_p:
        return ParamSpec(name, Role.OPAQUE,
                         Evidenced(Intent.IN, [], 0.0, verified=False), "c_void_p",
                         pointee=struct_ptrs.get(name))

    return ParamSpec(name, Role.SCALAR, Evidenced(Intent.IN, ["type"], 1.0, verified=True),
                     name_of_ctype(ct))


def spec_from_signatures(library: str, signatures: dict, overrides: dict | None = None,
                         out_handles: dict | None = None) -> LibrarySpec:
    overrides = overrides or {}
    out_handles = out_handles or {}
    funcs = {}
    for fname, sig in signatures.items():
        if fname == "__struct_sizes__":      # reserved key from L0, not a function
            continue
        ov = overrides.get(fname, {})
        oh = out_handles.get(fname, {})
        sp = sig.get("struct_ptr_params", {})
        params = [
            _classify(n, ct, sig.get("pointers", {}), ov, oh, sp)
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


def pointees_from_spec(spec) -> dict:
    """{function: {param: struct_name}} recovered from the spec itself.

    l2_handle_propagation needs this map, and reading it back off the spec means
    it works identically whether the spec came from a fresh L0 run or was loaded
    from a stored YAML.
    """
    out = {}
    for fname, fn in spec.functions.items():
        m = {p.name: p.pointee for p in fn.params if getattr(p, "pointee", None)}
        if m:
            out[fname] = m
    return out