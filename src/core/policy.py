from __future__ import annotations

from ..spec.vocab import Role, Intent
from ..spec.schema import FunctionSpec

CONFIDENCE_THRESHOLD = 0.5


class SpecViolation(Exception):
    """This function cannot be exposed safely. Fail-safe: refuse to generate."""


def check_exposable(fn: FunctionSpec) -> None:
    """Raise SpecViolation if `fn` must not be exposed by ANY protocol."""
    if fn.restype == "c_void_p" and fn.lifecycle not in ("creates", "borrows"):
        raise SpecViolation(
            f"{fn.name}: returns a raw void* that is not a managed handle; "
            f"refuse to auto-generate (fail-safe)."
        )

    for p in fn.params:
        if p.role in (Role.HANDLE, Role.OUT_HANDLE):  
            continue
        if p.role is Role.SCALAR and p.ctype == "c_void_p" and p.by_ref:
            raise SpecViolation(
                f"{fn.name}: param {p.name!r} is a pointer to a raw void* "
                f"(would expose an address as a bare integer); refuse to "
                f"auto-generate (fail-safe). If this receives a NEW handle, "
                f"it should be classified OUT_HANDLE, not SCALAR."
            )
        if p.role is Role.OPAQUE:
            raise SpecViolation(
                f"{fn.name}: param {p.name!r} is opaque (unresolved pointer, "
                f"callback, or writable buffer); refuse to auto-generate (fail-safe)."
            )
        if not p.intent.verified and p.intent.confidence < CONFIDENCE_THRESHOLD:
            raise SpecViolation(
                f"{fn.name}: param {p.name!r} is low-confidence "
                f"(role={p.role.value}, conf={p.intent.confidence}, "
                f"verified={p.intent.verified}); refuse to auto-generate (fail-safe)."
            )


def is_exposable(fn: FunctionSpec) -> bool:
    try:
        check_exposable(fn)
        return True
    except SpecViolation:
        return False