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

# --- ctype-name <-> ctypes object registry (so specs serialize as strings) ---
_CTYPES = {
    "c_int": ctypes.c_int, "c_uint": ctypes.c_uint,
    "c_long": ctypes.c_long, "c_ulong": ctypes.c_ulong,
    "c_longlong": ctypes.c_longlong, "c_short": ctypes.c_short,
    "c_float": ctypes.c_float, "c_double": ctypes.c_double,
    "c_bool": ctypes.c_bool, "c_char": ctypes.c_char,
    "c_char_p": ctypes.c_char_p, "c_void_p": ctypes.c_void_p,
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
    # phase 2/3 fields (unused now): dimension, owner, handle_type
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


@dataclass
class LibrarySpec:
    library: str
    functions: dict[str, FunctionSpec] = field(default_factory=dict)


# --- (de)serialization to plain dicts (for YAML) ----------------------------
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
                                    owner=fd.get("owner"))
    return LibrarySpec(library=d["library"], functions=funcs)