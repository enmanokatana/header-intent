"""
Evidence fusion combine intent facts from multiple layers into one, with
provenance preserved and conflicts flagged.

Rules:
  * Agreement compounds. If two layers agree, keep the value, merge sources,
    and raise confidence.
  * Sound-and-more-informed wins. L2 def-use reads the function body; L1
    const-ness reads only the signature. On disagreement, L2 wins.
  * Conflict is signal. A disagreement is recorded; opposite-direction ones
    (in vs out) are higher severity than refinements (out vs inout).

`manual` overrides are respected: an operator-asserted (verified) fact is not
overridden by inference.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..spec.vocab import Intent
from ..spec.schema import Evidenced, LibrarySpec

# severity of a disagreement
_REFINEMENT = {frozenset({Intent.OUT, Intent.INOUT}),
               frozenset({Intent.IN, Intent.INOUT})}   # same "side", just sharper


@dataclass
class Conflict:
    function: str
    param: str
    l1: str
    l2: str
    severity: str        # "refinement" | "conflict"
    resolved_to: str


def _is_manual(ev: Evidenced) -> bool:
    return "manual" in ev.sources


def fuse_intent(l1: Evidenced | None, l2: Evidenced | None):
    """Fuse two intent facts. Returns (fused Evidenced, Conflict|None)."""
    if l1 is None:
        return l2, None
    if l2 is None:
        return l1, None

    # operator-asserted facts are authoritative
    if _is_manual(l1):
        return l1, None

    if l1.value == l2.value:
        sources = list(dict.fromkeys(l1.sources + l2.sources))
        conf = min(0.99, max(l1.confidence, l2.confidence) + 0.05)  # agreement bump
        return Evidenced(l1.value, sources, conf, verified=l1.verified or l2.verified), None

    # disagreement: def-use (L2) is more informed than const-ness (L1)
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


def fuse_l2_into_spec(spec: LibrarySpec, l2: dict[str, dict[str, Evidenced]]) -> list[Conflict]:
    """Update each param's intent by fusing L1 (already in the spec) with L2.
    Returns the list of conflicts found (with function/param filled in)."""
    conflicts: list[Conflict] = []
    for fname, fn in spec.functions.items():
        fl2 = l2.get(fname, {})
        for p in fn.params:
            l2_fact = fl2.get(p.name)
            if l2_fact is None:
                continue
            fused, conflict = fuse_intent(p.intent, l2_fact)
            p.intent = fused
            if conflict is not None:
                conflict.function = fname
                conflict.param = p.name
                conflicts.append(conflict)
    return conflicts