"""
Safety policy -- PROTOCOL-AGNOSTIC. What may be exposed at all.

This lives in the core so every emitter (MCP, gRPC, plain Python, ...) enforces
IDENTICAL refusals. If a protocol backend could skip these checks it could ship a
double-free or a heap-corrupting write buffer; the policy is not the emitter's to
decide.

Each rule below exists because a real library broke on it (cJSON, mostly).
"""
from __future__ import annotations

from ..spec.vocab import Role, Intent
from ..spec.schema import FunctionSpec

CONFIDENCE_THRESHOLD = 0.5


class SpecViolation(Exception):
    """This function cannot be exposed safely. Fail-safe: refuse to generate."""


def check_exposable(fn: FunctionSpec, confidence_threshold: float = CONFIDENCE_THRESHOLD) -> None:
    """Raise SpecViolation if `fn` must not be exposed by ANY protocol.

    `confidence_threshold` gates only rule 3 (low-confidence unverified
    inference); the hard safety rules (raw void* returns/out-params, opaque
    params) fire at every threshold. This lets a sensitivity sweep isolate the
    threshold's effect on the uncertain-inference band without ever relaxing the
    non-negotiable safety rules."""
    # 1. a raw void* RETURN that is not a managed handle would hand out a bare
    #    pointer address as an integer (cJSON_malloc).
    if fn.restype == "c_void_p" and fn.lifecycle not in ("creates", "borrows"):
        raise SpecViolation(
            f"{fn.name}: returns a raw void* that is not a managed handle; "
            f"refuse to auto-generate (fail-safe)."
        )

    for p in fn.params:
        if p.role in (Role.HANDLE, Role.OUT_HANDLE):   # lifecycle-managed, checked at runtime
            continue
        # 1b. a SCALAR-role param whose underlying ctype is void* would expose a
        # raw pointer address as a bare integer -- the exact same hole as an
        # unmanaged void* RETURN (rule 1), just via an out-param instead. This
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
        # 2. opaque params: unresolved pointers, function pointers, and non-const
        #    char* write buffers (cJSON_Minify / cJSON_PrintPreallocated -- binding
        #    those as strings is heap corruption).
        if p.role is Role.OPAQUE:
            raise SpecViolation(
                f"{fn.name}: param {p.name!r} is opaque (unresolved pointer, "
                f"callback, or writable buffer); refuse to auto-generate (fail-safe)."
            )
        # 3. low-confidence, unverified inference is not trusted.
        if not p.intent.verified and p.intent.confidence < confidence_threshold:
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


def sweep_thresholds(spec, thresholds=None) -> list:
    """Confidence-threshold sensitivity analysis. For each threshold, count how
    many functions pass check_exposable. Returns a list of
    (threshold, buildable, refused, refused_low_confidence) rows.

    `refused_low_confidence` isolates the functions refused *specifically* by
    rule 3 at this threshold (i.e. the ones the threshold actually controls),
    as opposed to those refused by the hard safety rules at every threshold.
    This makes the curve interpretable: only the low-confidence band moves.
    """
    if thresholds is None:
        thresholds = [0.3, 0.4, 0.5, 0.6, 0.7]
    fns = list(spec.functions.values())
    rows = []
    for t in thresholds:
        buildable = refused = refused_lowconf = 0
        for fn in fns:
            try:
                check_exposable(fn, confidence_threshold=t)
                buildable += 1
            except SpecViolation as e:
                refused += 1
                if "low-confidence" in str(e):
                    refused_lowconf += 1
        rows.append((t, buildable, refused, refused_lowconf))
    return rows