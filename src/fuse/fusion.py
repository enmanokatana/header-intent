
from __future__ import annotations

from dataclasses import dataclass

from ..spec.vocab import Intent
from ..spec.schema import Evidenced, LibrarySpec

_REFINEMENT = {frozenset({Intent.OUT, Intent.INOUT}),
               frozenset({Intent.IN, Intent.INOUT})}  


@dataclass
class Conflict:
    function: str
    param: str
    l1: str
    l2: str
    severity: str      
    resolved_to: str


def _is_manual(ev: Evidenced) -> bool:
    return "manual" in ev.sources


def fuse_intent(l1: Evidenced | None, l2: Evidenced | None):
    """Fuse two intent facts. Returns (fused Evidenced, Conflict|None)."""
    if l1 is None:
        return l2, None
    if l2 is None:
        return l1, None

    if _is_manual(l1):
        return l1, None

    if l1.value == l2.value:
        sources = list(dict.fromkeys(l1.sources + l2.sources))
        conf = min(0.99, max(l1.confidence, l2.confidence) + 0.05)  
        return Evidenced(l1.value, sources, conf, verified=l1.verified or l2.verified), None

    pair = frozenset({l1.value, l2.value})
    severity = "refinement" if pair in _REFINEMENT else "conflict"
    fused = Evidenced(
        l2.value,
        list(dict.fromkeys(l2.sources + [f"l1_said_{l1.value.value}"])),
        l2.confidence * (1.0 if severity == "refinement" else 0.8),
        verified=False,
    )
    conflict = Conflict("", "", l1.value.value, l2.value.value, severity, l2.value.value)
    return fused, conflict


def fuse_l2_into_spec(spec: LibrarySpec, l2: dict[str, dict[str, Evidenced]],
                      param_order: dict[str, list[str]] | None = None) -> list[Conflict]:

    conflicts: list[Conflict] = []
    param_order = param_order or {}
    for fname, fn in spec.functions.items():
        fl2 = l2.get(fname, {})
        if not fl2:
            continue
        src_order = param_order.get(fname, [])
        spec_ptr_params = [p for p in fn.params if p.by_ref]
        for p in fn.params:
            l2_fact = fl2.get(p.name)
            if l2_fact is None and src_order and p.name not in src_order:
                for src_name, fact in fl2.items():
                    if src_name in src_order and src_name not in [q.name for q in fn.params]:
                        idx = src_order.index(src_name)
                        if idx < len(spec_ptr_params) and spec_ptr_params[idx].name == p.name:
                            l2_fact = fact
                            break
            if l2_fact is None:
                continue
            fused, conflict = fuse_intent(p.intent, l2_fact)
            p.intent = fused
            if conflict is not None:
                conflict.function = fname
                conflict.param = p.name
                conflicts.append(conflict)
    return conflicts