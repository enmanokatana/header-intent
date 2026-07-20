"""
Unified inference pipeline: signatures -> L1 -> L2 (def-use, handles, arrays)
-> fuse -> verify -> spec, in one call. Degrades gracefully: no source => L1 +
verify only; no .so => no behavioral verification.

Also produces a buildability report -- which functions generate a tool and
which are refused (fail-safe) and why -- the honest "what works / what's the
gap" summary for a real library.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field

from .layers.l1_signature import spec_from_signatures
from .layers.l2_static import l2_intents
from .layers.l2_handles import analyze_handles, apply_handle_facts
from .layers.l2_ownership import analyze_ownership, apply_ownership_facts
from .layers.l2_arrays import analyze_arrays, apply_array_facts
from .fuse.fusion import fuse_l2_into_spec
from .verify.probes import apply_verification
from .server.build import build_tool, SpecViolation
from .server.handles import HandleTable


@dataclass
class InferReport:
    handles: list = field(default_factory=list)
    arrays: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    ownership: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    buildable: list = field(default_factory=list)
    refused: list = field(default_factory=list)   # (fn, reason)

    def summary(self) -> str:
        lines = [
            f"buildable tools : {len(self.buildable)}  {sorted(self.buildable)}",
            f"refused         : {len(self.refused)}",
        ]
        for fn, why in self.refused:
            lines.append(f"    - {fn}: {why}")
        if self.handles:
            lines.append(f"handle lifecycle: {self.handles}")
        if self.arrays:
            lines.append(f"arrays          : {self.arrays}")
        if self.ownership:
            lines.append(f"ownership       : {self.ownership}")
        if self.conflicts:
            lines.append(f"L1/L2 conflicts : {[(c.function, c.param, c.l1, '->', c.l2) for c in self.conflicts]}")
        if self.skipped:
            lines.append(f"skipped analyses: {self.skipped}")
        return "\n".join(lines)


def infer_spec(library: str, *, signatures: dict | None = None, header: str | None = None,
               source: str | None = None, so: str | None = None,
               engine: str = "libclang", clang_args=None, overrides=None,
               preprocessed_source: str | None = None):
    """Run the whole inference stack. Returns (LibrarySpec, InferReport)."""
    report = InferReport()

    # --- signatures (L0) ---
    if signatures is None:
        if header is None:
            raise ValueError("provide `signatures` or `header`")
        from .models.extract import extract_signatures      # Ferrule's own L0 (no cToMcp)
        signatures, skipped_sigs = extract_signatures(header, clang_args=clang_args)
        for s in skipped_sigs:
            report.skipped.append(f"L0 {s}")
    spec = spec_from_signatures(library, signatures, overrides)

    # --- L2 (needs source) ---
    if source is not None:
        eng = None
        if engine == "libclang":
            from .layers.libclang_engine import LibclangEngine
            eng = LibclangEngine(clang_args)

        # def-use -> fuse
        try:
            intents = l2_intents(source if eng else (preprocessed_source or open(source).read()), engine=eng)
            report.conflicts = fuse_l2_into_spec(spec, intents)
        except Exception as e:
            report.skipped.append(f"def_use: {e!r}")

        # handles
        try:
            if eng:
                facts, _ = analyze_handles(engine=eng, path=source, clang_args=clang_args)
            else:
                facts, _ = analyze_handles(preprocessed_source or open(source).read())
            report.handles = apply_handle_facts(spec, facts)
        except Exception as e:
            report.skipped.append(f"handles: {e!r}")

        # ownership: creates vs borrowed (prevents double-free on borrowed returns)
        try:
            if eng:
                own = analyze_ownership(engine=eng, path=source, clang_args=clang_args)
            else:
                own = analyze_ownership(preprocessed_source or open(source).read())
            report.ownership = apply_ownership_facts(spec, own)
        except Exception as e:
            report.skipped.append(f"ownership: {e!r}")

        # arrays (pycparser-only today: needs preprocessed text)
        text = preprocessed_source if preprocessed_source else (open(source).read() if engine == "pycparser" else None)
        if text is not None:
            try:
                report.arrays = apply_array_facts(spec, analyze_arrays(text))
            except Exception as e:
                report.skipped.append(f"arrays: {e!r}")
        else:
            report.skipped.append("arrays: needs preprocessed source (libclang array analysis not built yet)")
    else:
        report.skipped.append("all L2: no source given (L1 + verify only)")

    # --- verify + buildability (needs .so) ---
    if so is not None:
        lib = ctypes.CDLL(so)
        apply_verification(lib, spec)
        H = HandleTable()
        for fn in spec.functions.values():
            try:
                build_tool(lib, fn, H)
                report.buildable.append(fn.name)
            except SpecViolation as e:
                report.refused.append((fn.name, str(e).split(";")[0]))
            except Exception as e:
                report.refused.append((fn.name, f"{type(e).__name__}: {e}"))

    return spec, report