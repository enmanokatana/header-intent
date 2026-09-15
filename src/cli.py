"""
ferrule CLI.

  ferrule infer  <header.h> [lib.so] --source <src.c>  -> full L1+L2 stack -> spec
  ferrule verify <lib.so> <spec.yaml>                  -> probes + updates spec

Signature extraction (L0) is Ferrule's own libclang extractor -- self-contained,
no external toolkit required.
"""
import argparse
import ctypes
import sys

import yaml

from .spec.io import dump_yaml, load_yaml, dumps_yaml
from .layers.l1_signature import spec_from_signatures
from .verify.probes import apply_verification


def cmd_infer(args):
    from .pipeline import infer_spec
    import os, glob

    overrides = {}
    if args.overrides:
        overrides = yaml.safe_load(open(args.overrides)) or {}
    clang_args = []
    for inc in (args.include or []):
        clang_args += ["-I", inc]

    # Resolve sources: explicit --source paths (repeatable) plus any *.c found
    # under --source-dir. Preserve order and de-duplicate. A single source stays
    # a plain string for back-compat; multiple become a list (multi-file).
    src_list = list(args.source or [])
    if args.source_dir:
        src_list += sorted(glob.glob(os.path.join(args.source_dir, "**", "*.c"),
                                     recursive=True))
    seen, sources = set(), []
    for s in src_list:
        rp = os.path.abspath(s)
        if rp not in seen:
            seen.add(rp)
            sources.append(s)
    if not sources:
        source_arg = None
    elif len(sources) == 1:
        source_arg = sources[0]
    else:
        source_arg = sources
        print(f"[multi-file] {len(sources)} source files for L2 analysis")

    spec, report = infer_spec(
        args.library_name or "lib",
        header=args.header,
        source=source_arg,
        so=args.lib,
        engine=args.engine,
        clang_args=clang_args,
        overrides=overrides,
    )
    print(report.summary())
    if args.out:
        dump_yaml(spec, args.out)
        print(f"\nwrote {args.out}")
    elif args.print_spec:
        print()
        print(dumps_yaml(spec))


def cmd_verify(args):
    spec = load_yaml(args.spec)
    apply_verification(ctypes.CDLL(args.lib), spec)
    dump_yaml(spec, args.spec)
    print(f"verified and updated {args.spec}")


def cmd_sweep(args):
    """Confidence-threshold sensitivity analysis over an existing spec."""
    from .core.policy import sweep_thresholds
    spec = load_yaml(args.spec)
    thresholds = [float(x) for x in args.thresholds.split(",")] if args.thresholds else None
    rows = sweep_thresholds(spec, thresholds)
    total = len(spec.functions)
    print(f"threshold sweep for {args.spec} ({total} functions)")
    print(f"{'thresh':>7} {'buildable':>10} {'refused':>8} {'refused(low-conf)':>18} {'bound %':>8}")
    for t, b, r, rlc in rows:
        pct = 100.0 * b / total if total else 0.0
        print(f"{t:>7.2f} {b:>10} {r:>8} {rlc:>18} {pct:>7.1f}%")
    if args.csv:
        import csv
        with open(args.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["threshold", "buildable", "refused", "refused_low_confidence", "total"])
            for t, b, r, rlc in rows:
                w.writerow([t, b, r, rlc, total])
        print(f"wrote {args.csv}")


def cmd_emit(args):
    """spec -> a protocol target (proto | python | mcp-list)."""
    import ctypes
    from .core.invoker import build_capabilities
    from .core.handles import HandleTable

    spec = load_yaml(args.spec)
    lib = ctypes.CDLL(args.lib)
    caps, refused = build_capabilities(lib, spec, HandleTable())
    print(f"[ferrule] {len(caps)} capabilities, {len(refused)} refused", file=sys.stderr)
    for n, why in refused:
        print(f"  - {n}: {why}", file=sys.stderr)

    if args.target == "proto":
        from .emit.proto import generate_proto
        pf = generate_proto(caps, package=args.package or spec.library,
                            service=args.service or "Library")
        out = pf.text
        if pf.stateless:
            print(f"[ferrule] stateless (no session): {pf.stateless}", file=sys.stderr)
    elif args.target == "python":
        from .emit.python import generate_source
        out = generate_source(spec, args.lib)
    else:                                   # list
        out = "\n".join(f"{c.name}({', '.join(f.name for f in c.inputs)})"
                         f" -> {', '.join(f.name for f in c.outputs) or 'void'}"
                         + (f"  [{c.lifecycle} owner={c.owner}]" if c.lifecycle else "")
                         for c in caps)

    if args.out:
        open(args.out, "w").write(out)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ferrule")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("infer", help="header + source -> capability spec (full L1+L2 stack)")
    pi.add_argument("header", help="C header to extract signatures from (libclang)")
    pi.add_argument("lib", nargs="?", help="optional .so to verify + report buildability")
    pi.add_argument("--source", action="append", default=None,
                    help="C source (.c) for L2 static analysis. Repeatable: "
                         "pass --source multiple times for a multi-file library.")
    pi.add_argument("--source-dir", default=None,
                    help="Directory to recursively glob for *.c files as L2 "
                         "sources (multi-file). Combined with any --source paths.")
    pi.add_argument("--engine", default="libclang", choices=["libclang", "pycparser"],
                    help="L2 analysis engine (libclang reads .c directly; pycparser needs preprocessed)")
    pi.add_argument("--include", "-I", action="append", help="include dir for libclang (repeatable)")
    pi.add_argument("--overrides", help="YAML {func: {param: intent}} for exceptions")
    pi.add_argument("--library-name")
    pi.add_argument("-o", "--out", help="write spec YAML here")
    pi.add_argument("--print-spec", action="store_true", help="also print the spec YAML")
    pi.set_defaults(func=cmd_infer)

    pe = sub.add_parser("emit", help="capability spec -> a protocol target")
    pe.add_argument("spec", help="spec YAML from `infer`")
    pe.add_argument("lib", help="the .so the spec describes")
    pe.add_argument("--target", default="proto", choices=["proto", "python", "list"],
                    help="what to emit (default: proto)")
    pe.add_argument("--package", help="proto package name")
    pe.add_argument("--service", help="proto service name")
    pe.add_argument("-o", "--out", help="write here (else stdout)")
    pe.set_defaults(func=cmd_emit)

    pv = sub.add_parser("verify", help="probe a lib and update a spec's verified flags")
    pv.add_argument("lib")
    pv.add_argument("spec")
    pv.set_defaults(func=cmd_verify)

    ps = sub.add_parser("sweep", help="confidence-threshold sensitivity analysis over a spec")
    ps.add_argument("spec", help="capability spec (.yaml) to analyze")
    ps.add_argument("--thresholds", default=None,
                    help="comma-separated thresholds, e.g. 0.3,0.4,0.5,0.6,0.7 (default that set)")
    ps.add_argument("--csv", default=None, help="also write the sweep table to this CSV path")
    ps.set_defaults(func=cmd_sweep)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()