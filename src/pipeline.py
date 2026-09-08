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
from .layers.l2_static import l2_intents, l2_param_order
from .layers.l2_handles import analyze_handles, apply_handle_facts, analyze_handles_multi
from .layers.l2_ownership import (analyze_ownership, apply_ownership_facts,
                                  analyze_string_ownership, apply_string_ownership_facts,
                                  analyze_ownership_multi, analyze_string_ownership_multi)
from .layers.l2_out_handles import (analyze_out_handles, apply_out_handle_facts,
                                    analyze_out_handles_multi)
from .layers.l2_arrays import analyze_arrays, apply_array_facts
from .fuse.fusion import fuse_l2_into_spec
from .verify.probes import apply_verification
from .core.invoker import build_capabilities
from .core.policy import SpecViolation


def _bn(path):
    import os
    return os.path.basename(path)
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
    """Run the whole inference stack. Returns (LibrarySpec, InferReport)."""
    report = InferReport()

    if signatures is None:
        if header is None:
            raise ValueError("provide `signatures` or `header`")
        from .models.extract import extract_signatures
        signatures, skipped_sigs = extract_signatures(header, clang_args=clang_args)
        for s in skipped_sigs:
            report.skipped.append(f"L0 {s}")
    spec = spec_from_signatures(library, signatures, overrides)

    sources = None
    if source is not None:
        sources = [source] if isinstance(source, str) else list(source)

    if sources:
        eng = None
        if engine == "libclang":
            from .layers.libclang_engine import LibclangEngine
            eng = LibclangEngine(clang_args)

        multi = len(sources) > 1

        try:
            if eng:
                intents, porder = {}, {}
                for s in sources:
                    try:
                        i = l2_intents(s, engine=eng)
                        po = l2_param_order(s, engine=eng)
                    except Exception as fe:
                        report.skipped.append(f"def_use {_bn(s)}: {type(fe).__name__}, skipped")
                        continue
                    for k, v in i.items():
                        intents.setdefault(k, v)
                    for k, v in po.items():
                        porder.setdefault(k, v)
            else:
                src_arg = preprocessed_source or open(sources[0]).read()
                intents = l2_intents(src_arg, engine=eng)
                porder = l2_param_order(src_arg, engine=eng)
            report.conflicts = fuse_l2_into_spec(spec, intents, porder)
        except Exception as e:
            report.skipped.append(f"def_use: {e!r}")

        try:
            if eng and multi:
                facts, _, sk = analyze_handles_multi(sources, engine=eng, clang_args=clang_args)
                report.skipped += [f"handles {n}" for n in sk]
            elif eng:
                facts, _ = analyze_handles(engine=eng, path=sources[0], clang_args=clang_args)
            else:
                facts, _ = analyze_handles(preprocessed_source or open(sources[0]).read())
            report.handles = apply_handle_facts(spec, facts)
        except Exception as e:
            report.skipped.append(f"handles: {e!r}")

        try:
            if eng and multi:
                own, sk = analyze_ownership_multi(sources, engine=eng, clang_args=clang_args)
                report.skipped += [f"ownership {n}" for n in sk]
            elif eng:
                own = analyze_ownership(engine=eng, path=sources[0], clang_args=clang_args)
            else:
                own = analyze_ownership(preprocessed_source or open(sources[0]).read())
            report.ownership = apply_ownership_facts(spec, own)
        except Exception as e:
            report.skipped.append(f"ownership: {e!r}")

        try:
            if eng and multi:
                sown, sk = analyze_string_ownership_multi(sources, engine=eng, clang_args=clang_args)
                report.skipped += [f"string_ownership {n}" for n in sk]
            elif eng:
                sown = analyze_string_ownership(engine=eng, path=sources[0], clang_args=clang_args)
            else:
                sown = analyze_string_ownership(preprocessed_source or open(sources[0]).read())
            report.ownership += apply_string_ownership_facts(spec, sown)
        except Exception as e:
            report.skipped.append(f"string_ownership: {e!r}")

        try:
            oh_candidates = {fn: sig.get("out_handle_candidates", {})
                             for fn, sig in signatures.items()
                             if sig.get("out_handle_candidates")}
            if oh_candidates:
                if eng and multi:
                    oh_facts, sk = analyze_out_handles_multi(
                        sources, candidates=oh_candidates, engine=eng, clang_args=clang_args)
                    report.skipped += [f"out_handles {n}" for n in sk]
                elif eng:
                    oh_facts = analyze_out_handles(candidates=oh_candidates, engine=eng,
                                                   path=sources[0], clang_args=clang_args)
                else:
                    oh_facts = analyze_out_handles(
                        preprocessed_source or open(sources[0]).read(), candidates=oh_candidates)
                report.ownership += apply_out_handle_facts(spec, oh_facts)
        except Exception as e:
            report.skipped.append(f"out_handles: {e!r}")

        text = preprocessed_source if preprocessed_source else (
            open(sources[0]).read() if engine == "pycparser" else None)
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
    else:
        from .core.policy import check_exposable, SpecViolation as _SV
        buildable, refused = [], []
        for name, fn in spec.functions.items():
            try:
                check_exposable(fn)
                buildable.append(name)
            except _SV as e:
                refused.append((name, str(e)))
        report.buildable = buildable
        report.refused = refused

    return spec, report