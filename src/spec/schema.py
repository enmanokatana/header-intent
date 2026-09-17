"""
Capability spec schema (dataclass-based; swap to Pydantic in a richer env).

Every semantic fact is wrapped in Evidenced: the value plus where it came from,
how confident we are, and whether a behavioral probe confirmed it. The spec is
"the answer plus how much to trust it and why."
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .vocab import Intent, Role

_CTYPES = {
    "c_int": ctypes.c_int, "c_uint": ctypes.c_uint,
    "c_long": ctypes.c_long, "c_ulong": ctypes.c_ulong,
    "c_longlong": ctypes.c_longlong, "c_ulonglong": ctypes.c_ulonglong,
    "c_short": ctypes.c_short, "c_ushort": ctypes.c_ushort,
    "c_byte": ctypes.c_byte, "c_ubyte": ctypes.c_ubyte,
    "c_float": ctypes.c_float, "c_double": ctypes.c_double,
    "c_longdouble": ctypes.c_longdouble,
    "c_bool": ctypes.c_bool, "c_char": ctypes.c_char,
    "c_char_p": ctypes.c_char_p, "c_void_p": ctypes.c_void_p,
    "c_wchar": ctypes.c_wchar, "c_wchar_p": ctypes.c_wchar_p,
    "c_size_t": ctypes.c_size_t, "c_ssize_t": ctypes.c_ssize_t,
    "c_int8": ctypes.c_int8, "c_uint8": ctypes.c_uint8,
    "c_int16": ctypes.c_int16, "c_uint16": ctypes.c_uint16,
    "c_int32": ctypes.c_int32, "c_uint32": ctypes.c_uint32,
    "c_int64": ctypes.c_int64, "c_uint64": ctypes.c_uint64,
}

def ctype_by_name(name: str):
    if name.startswith("POINTER(") and name.endswith(")"):
        inner = name[len("POINTER("):-1]
        return ctypes.POINTER(ctype_by_name(inner))
    return _CTYPES[name]

def name_of_ctype(t) -> str:
    for k, v in _CTYPES.items():
        if v is t:
            return k
    if isinstance(t, type) and issubclass(t, ctypes._Pointer):
        try:
            return f"POINTER({name_of_ctype(t._type_)})"
        except KeyError:
            pass
    raise KeyError(f"no registered ctype name for {t!r}")


@dataclass
class Evidenced:
    """A fact plus its provenance, confidence, and verification status."""
    value: Any
    sources: list[str] = field(default_factory=list)
    confidence: float = 0.0
    verified: bool = False


@dataclass
class ParamSpec:
    name: str
    role: Role
    intent: Evidenced
    ctype: str
    by_ref: bool = False
    dimension: Optional[str] = None
    owner: Optional[str] = None
    handle_type: Optional[str] = None
    # The pointee struct name for a `T*` or `T**` parameter, recorded by L0 and
    # previously discarded. It carries NO claim that T is a handle -- it is the
    # evidence l2_handle_propagation needs in order to ASK that question. This
    # must survive serialization or a spec reloaded from YAML analyzes as if L0
    # had never seen a struct pointer at all.
    pointee: Optional[str] = None
    # ABI dimensions for a CALLER_STATE parameter, from clang's own layout
    # computation. Present only when the binding must allocate the struct
    # itself; absent means the size is unknown and the policy refuses it.
    state_size: Optional[int] = None
    state_align: Optional[int] = None


@dataclass
class FunctionSpec:
    name: str
    params: list[ParamSpec] = field(default_factory=list)
    restype: Optional[str] = None
    lifecycle: Optional[str] = None
    handle_type: Optional[str] = None
    owner: Optional[str] = None
    string_owner: Optional[str] = None
    handle_out_param: Optional[str] = None


@dataclass
class LibrarySpec:
    library: str
    functions: dict[str, FunctionSpec] = field(default_factory=dict)


# Optional ParamSpec fields that serialize only when set. Keeping this as ONE
# list, consumed by both directions, is what stops a new field from being
# written but never read (or vice versa) -- the failure mode where analysis
# silently degrades on any spec that went through a YAML round-trip.
_OPTIONAL_PARAM_FIELDS = ("dimension", "owner", "handle_type",
                          "pointee", "state_size", "state_align")


def to_dict(spec: LibrarySpec) -> dict:
    out = {"library": spec.library, "functions": {}}
    for fname, fn in spec.functions.items():
        entry = {
            "restype": fn.restype,
            "params": [_param_to_dict(p) for p in fn.params],
        }
        if fn.lifecycle is not None:
            entry["lifecycle"] = fn.lifecycle
        if fn.handle_type is not None:
            entry["handle_type"] = fn.handle_type
        if fn.owner is not None:
            entry["owner"] = fn.owner
        if fn.string_owner is not None:
            entry["string_owner"] = fn.string_owner
        if fn.handle_out_param is not None:
            entry["handle_out_param"] = fn.handle_out_param
        out["functions"][fname] = entry
    return out

def _param_to_dict(p: ParamSpec) -> dict:
    d = {
        "name": p.name,
        "role": p.role.value,
        "ctype": p.ctype,
        "by_ref": p.by_ref,
        "intent": {
            "value": p.intent.value.value if isinstance(p.intent.value, Intent) else p.intent.value,
            "sources": list(p.intent.sources),
            "confidence": p.intent.confidence,
            "verified": p.intent.verified,
        },
    }
    for k in _OPTIONAL_PARAM_FIELDS:
        v = getattr(p, k, None)
        if v is not None:
            d[k] = v
    return d

def from_dict(d: dict) -> LibrarySpec:
    funcs = {}
    for fname, fd in d.get("functions", {}).items():
        params = []
        for pd in fd.get("params", []):
            iv = pd["intent"]
            p = ParamSpec(
                name=pd["name"],
                role=Role(pd["role"]),
                ctype=pd["ctype"],
                by_ref=pd.get("by_ref", False),
                intent=Evidenced(
                    value=Intent(iv["value"]),
                    sources=list(iv.get("sources", [])),
                    confidence=float(iv.get("confidence", 0.0)),
                    verified=bool(iv.get("verified", False)),
                ),
            )
            for k in _OPTIONAL_PARAM_FIELDS:
                if pd.get(k) is not None:
                    setattr(p, k, pd[k])
            params.append(p)
        funcs[fname] = FunctionSpec(name=fname, params=params, restype=fd.get("restype"),
                                    lifecycle=fd.get("lifecycle"), handle_type=fd.get("handle_type"),
                                    owner=fd.get("owner"), string_owner=fd.get("string_owner"),
                                    handle_out_param=fd.get("handle_out_param"))
    return LibrarySpec(library=d["library"], functions=funcs)