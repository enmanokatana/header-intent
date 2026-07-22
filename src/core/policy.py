from __future__ import annotations

from ..spec.vocab import Role, Intent
from ..spec.schema import FunctionSpec

CONFIDENCE_THRESHOLD = 0.5


class SpecViolation(Exception):
    """This function cannot be exposed safely. Fail-safe: refuse to generate."""


def check_exposable(fn: FunctionSpec) -> None:
    """Raise SpecViolation if `fn` must not be exposed by ANY protocol."""
    #  a raw void* RETURN that is not a managed handle would hand out a bare
    #    pointer address as an integer (cJSON_malloc).
    if fn.restype == "c_void_p" and fn.lifecycle not in ("creates", "borrows"):
        raise SpecViolation(
            f"{fn.name}: returns a raw void* that is not a managed handle; "
            f"refuse to auto-generate (fail-safe)."
        )

    for p in fn.params:
        if p.role in (Role.HANDLE, Role.OUT_HANDLE):  
            continue
        #  a SCALAR-role param whose underlying ctype is void* would expose a
        # raw pointer address as a bare integer the exact same hole as an
        # unmanaged void* RETURN , just via an out-param instead. This
        # matters because a manually-hinted "out" pointer-to-pointer param
        # (sqlite3_open(path, &db) before OUT_HANDLE recognizes it) previously
        # fell through as plain SCALAR and leaked the handle as an int.
        if p.role is Role.SCALAR and p.ctype == "c_void_p" and p.by_ref:
            raise SpecViolation(
                f"{fn.name}: param {p.name!r} is a pointer to a raw void* "
                f"(would expose an address as a bare integer); refuse to "
                f"auto-generate (fail-safe). If this receives a NEW handle, "
                f"it should be classified OUT_HANDLE, not SCALAR."
            )
        # opaque params: unresolved pointers, function pointers, and non-const
        #    char* write buffers (cJSON_Minify / cJSON_PrintPreallocated binding
        #    those as strings is heap corruption).
        if p.role is Role.OPAQUE:
            raise SpecViolation(
                f"{fn.name}: param {p.name!r} is opaque (unresolved pointer, "
                f"callback, or writable buffer); refuse to auto-generate (fail-safe)."
            )
        # low-confidence, unverified inference is not trusted.
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