
from __future__ import annotations

import ctypes
import types

from ..spec.io import load_yaml
from ..core.invoker import build_capabilities
from ..core.handles import HandleTable


def bind_module(so_path: str, spec_path_or_spec, name: str = "cbind"):
    """Return a live module whose attributes are the library's capabilities."""
    spec = load_yaml(spec_path_or_spec) if isinstance(spec_path_or_spec, str) else spec_path_or_spec
    lib = ctypes.CDLL(so_path)
    handles = HandleTable()
    caps, refused = build_capabilities(lib, spec, handles)

    mod = types.ModuleType(name)
    mod.__doc__ = f"Ferrule bindings for {spec.library} ({len(caps)} functions)"
    mod._handles = handles
    mod._refused = refused
    for cap in caps:
        fn = (lambda c: lambda **kw: c.invoke(**kw))(cap)
        fn.__name__ = cap.name
        fn.__doc__ = cap.doc
        setattr(mod, cap.name, fn)
    return mod


_PY_NAME = {int: "int", float: "float", str: "str", bool: "bool", list: "list",
            type(None): "None", dict: "dict"}


def _ann(t) -> str:
    return _PY_NAME.get(t, "object")


def _ret_ann(cap) -> str:
    if cap.returns_mapping:
        return "dict"
    return _ann(cap.outputs[0].py_type) if cap.outputs else "None"


def generate_source(spec_path_or_spec, so_path: str, module_doc: str = "") -> str:
    """Emit readable Python source binding the library. Requires only the SPEC --
    proving the spec alone carries enough intent to generate a target."""
    spec = load_yaml(spec_path_or_spec) if isinstance(spec_path_or_spec, str) else spec_path_or_spec
    lib = ctypes.CDLL(so_path)
    caps, refused = build_capabilities(lib, spec, HandleTable())

    L = []
    L.append('"""')
    L.append(f"{module_doc or f'Ferrule-generated bindings for {spec.library}.'}")
    L.append("")
    L.append("Generated from a verified capability spec. Handle ownership is enforced:")
    L.append("a BORROWED handle can be read but never freed.")
    if refused:
        L.append("")
        L.append("Refused (not exposed, fail-safe):")
        for n, why in refused:
            L.append(f"  - {n}: {why}")
    L.append('"""')
    L.append("import ctypes")
    L.append("")
    L.append("from src.spec.io import load_yaml")
    L.append("from src.core.invoker import build_capabilities")
    L.append("from src.core.handles import HandleTable, OwnershipError")
    L.append("")
    L.append(f"_SO   = {so_path!r}")
    L.append(f"_SPEC = {spec.library!r} + '.spec.yaml'")
    L.append("")
    L.append("_lib = ctypes.CDLL(_SO)")
    L.append("_handles = HandleTable()")
    L.append("_caps = {c.name: c for c in build_capabilities(_lib, load_yaml(_SPEC), _handles)[0]}")
    L.append("")
    for cap in caps:
        args = ", ".join(f"{f.name}: {_ann(f.py_type)}" for f in cap.inputs)
        call = ", ".join(f"{f.name}={f.name}" for f in cap.inputs)
        L.append(f"def {cap.name}({args}) -> {_ret_ann(cap)}:")
        L.append('    """' + cap.doc)
        if cap.lifecycle:
            L.append(f"    lifecycle: {cap.lifecycle}" +
                     (f"  owner: {cap.owner}" if cap.owner else ""))
        if cap.outputs:
            outs = ", ".join(f"{f.name}: {_ann(f.py_type)}" for f in cap.outputs)
            L.append(f"    returns: {outs}")
        L.append('    """')
        L.append(f"    return _caps[{cap.name!r}].invoke({call})")
        L.append("")
    return "\n".join(L)
