from __future__ import annotations

import ctypes
from dataclasses import dataclass, field

from .layers.l1_signature import spec_from_signatures
from .layers.l2_static import l2_intents, l2_param_order
from .layers.l2_handles import analyze_handles, apply_handle_facts
from .layers.l2_ownership import (analyze_ownership, apply_ownership_facts,
                                  analyze_string_ownership, apply_string_ownership_facts)
from .layers.l2_out_handles import analyze_out_handles, apply_out_handle_facts
from .layers.l2_arrays import analyze_arrays, apply_array_facts
from .fuse.fusion import fuse_l2_into_spec
from .verify.probes import apply_verification
from .core.invoker import build_capabilities
from .core.policy import SpecViolation
from .core.handles import HandleTable


@dataclass
class InferReport:
    handles: list = field(default_factory=list)
    arrays: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    ownership: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    buildable: list = field(default_factory=list)
    refused: list = field(default_factory=list)   

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
    report = InferReport()

    if signatures is None:
        if header is None:
            raise ValueError("provide `signatures` or `header`")
        from .models.extract import extract_signatures     
        signatures, skipped_sigs = extract_signatures(header, clang_args=clang_args)
        for s in skipped_sigs:
            report.skipped.append(f"L0 {s}")
    spec = spec_from_signatures(library, signatures, overrides)

    if source is not None:
        eng = None
        if engine == "libclang":
            from .layers.libclang_engine import LibclangEngine
            eng = LibclangEngine(clang_args)      # strict: refuses a truncated AST

        try:
            src_arg = source if eng else (preprocessed_source or open(source).read())
            intents = l2_intents(src_arg, engine=eng)
            porder = l2_param_order(src_arg, engine=eng)
            report.conflicts = fuse_l2_into_spec(spec, intents, porder)
        except Exception as e:
            report.skipped.append(f"def_use: {e!r}")

        try:
            if eng:
                facts, _ = analyze_handles(engine=eng, path=source, clang_args=clang_args)
            else:
                facts, _ = analyze_handles(preprocessed_source or open(source).read())
            report.handles = apply_handle_facts(spec, facts)
        except Exception as e:
            report.skipped.append(f"handles: {e!r}")

        try:
            if eng:
                own = analyze_ownership(engine=eng, path=source, clang_args=clang_args)
            else:
                own = analyze_ownership(preprocessed_source or open(source).read())
            report.ownership = apply_ownership_facts(spec, own)
        except Exception as e:
            report.skipped.append(f"ownership: {e!r}")

        try:
            if eng:
                sown = analyze_string_ownership(engine=eng, path=source, clang_args=clang_args)
            else:
                sown = analyze_string_ownership(preprocessed_source or open(source).read())
            notes = apply_string_ownership_facts(spec, sown)
            report.ownership += notes
        except Exception as e:
            report.skipped.append(f"string_ownership: {e!r}")


        try:
            oh_candidates = {fn: sig.get("out_handle_candidates", {})
                             for fn, sig in signatures.items()
                             if sig.get("out_handle_candidates")}
            if oh_candidates:
                if eng:
                    oh_facts = analyze_out_handles(candidates=oh_candidates, engine=eng,
                                                   path=source, clang_args=clang_args)
                else:
                    oh_facts = analyze_out_handles(
                        preprocessed_source or open(source).read(), candidates=oh_candidates)
                notes = apply_out_handle_facts(spec, oh_facts)
                report.ownership += notes
        except Exception as e:
            report.skipped.append(f"out_handles: {e!r}")

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

    if so is not None:
        lib = ctypes.CDLL(so)
        apply_verification(lib, spec)
        H = HandleTable()
        caps, refused = build_capabilities(lib, spec, H)
        report.buildable = [c.name for c in caps]
        report.refused = refused

    return spec, report