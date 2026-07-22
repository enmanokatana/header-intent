from __future__ import annotations

import ctypes
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .vocab import Intent, Role

# --- ctype-name <-> ctypes object registry (so specs serialize as strings) ---
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
    # fixed-width aliases: distinct NAMES some extractors may emit, even though
    # ctypes implements them as aliases of the types above on most platforms
    # (e.g. c_int64 is c_longlong)  registering the alias name avoids a
    # KeyError while `ctype_by_name` still returns a working, identical type.
    "c_int8": ctypes.c_int8, "c_uint8": ctypes.c_uint8,
    "c_int16": ctypes.c_int16, "c_uint16": ctypes.c_uint16,
    "c_int32": ctypes.c_int32, "c_uint32": ctypes.c_uint32,
    "c_int64": ctypes.c_int64, "c_uint64": ctypes.c_uint64,
}

def ctype_by_name(name: str):
    return _CTYPES[name]

def name_of_ctype(t) -> str:
    for k, v in _CTYPES.items():
        if v is t:
            return k
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
    intent: Evidenced           # Evidenced[Intent]
    ctype: str                  # value type name; for a pointer this is the POINTEE
    by_ref: bool = False        # True if the C param is a pointer (bind POINTER(ctype))
    # for later(unused now): dimension, owner, handle_type
    dimension: Optional[str] = None
    owner: Optional[str] = None
    handle_type: Optional[str] = None


@dataclass
class FunctionSpec:
    name: str
    params: list[ParamSpec] = field(default_factory=list)
    restype: Optional[str] = None          # ctype name, or None for void
    lifecycle: Optional[str] = None        # "creates" | "borrows" | "uses" | "destroys"
    handle_type: Optional[str] = None      # the opaque type this fn's lifecycle concerns
    owner: Optional[str] = None            # "caller" (may free) | "library" (borrowed)
    string_owner: Optional[str] = None     # for char* returns: "caller" (we auto-free
                                            # after copying) | "library" (never free)
    handle_out_param: Optional[str] = None # name of a T** param that RECEIVES a new
                                            # handle (sqlite3_open(path, &db) idiom);
                                            # the handle comes from this param, not
                                            # the return value (which is often a status)


@dataclass
class LibrarySpec:
    library: str
    functions: dict[str, FunctionSpec] = field(default_factory=dict)


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
    for k in ("dimension", "owner", "handle_type"):
        v = getattr(p, k)
        if v is not None:
            d[k] = v
    return d

def from_dict(d: dict) -> LibrarySpec:
    funcs = {}
    for fname, fd in d.get("functions", {}).items():
        params = []
        for pd in fd.get("params", []):
            iv = pd["intent"]
            params.append(ParamSpec(
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
                dimension=pd.get("dimension"),
                owner=pd.get("owner"),
                handle_type=pd.get("handle_type"),
            ))
        funcs[fname] = FunctionSpec(name=fname, params=params, restype=fd.get("restype"),
                                    lifecycle=fd.get("lifecycle"), handle_type=fd.get("handle_type"),
                                    owner=fd.get("owner"), string_owner=fd.get("string_owner"),
                                    handle_out_param=fd.get("handle_out_param"))
    return LibrarySpec(library=d["library"], functions=funcs)