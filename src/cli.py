"""
ferrule CLI.

  ferrule infer  <header.h> [lib.so] --source <src.c>  -> full L1+L2 stack -> spec
  ferrule verify <lib.so> <spec.yaml>                  -> probes + updates spec

Signature extraction (L0) is Ferrule's own libclang extractor -- self-contained,
no external toolkit required.
"""
import argparse
import ctypes

import yaml

from .spec.io import dump_yaml, load_yaml, dumps_yaml
from .layers.l1_signature import spec_from_signatures
from .verify.probes import apply_verification


def cmd_infer(args):
    from .pipeline import infer_spec

    overrides = {}
    if args.overrides:
        overrides = yaml.safe_load(open(args.overrides)) or {}
    clang_args = []
    for inc in (args.include or []):
        clang_args += ["-I", inc]

    spec, report = infer_spec(
        args.library_name or "lib",
        header=args.header,
        source=args.source,
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


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ferrule")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("infer", help="header + source -> capability spec (full L1+L2 stack)")
    pi.add_argument("header", help="C header to extract signatures from (libclang)")
    pi.add_argument("lib", nargs="?", help="optional .so to verify + report buildability")
    pi.add_argument("--source", help="C source (.c) for L2 static analysis")
    pi.add_argument("--engine", default="libclang", choices=["libclang", "pycparser"],
                    help="L2 analysis engine (libclang reads .c directly; pycparser needs preprocessed)")
    pi.add_argument("--include", "-I", action="append", help="include dir for libclang (repeatable)")
    pi.add_argument("--overrides", help="YAML {func: {param: intent}} for exceptions")
    pi.add_argument("--library-name")
    pi.add_argument("-o", "--out", help="write spec YAML here")
    pi.add_argument("--print-spec", action="store_true", help="also print the spec YAML")
    pi.set_defaults(func=cmd_infer)

    pv = sub.add_parser("verify", help="probe a lib and update a spec's verified flags")
    pv.add_argument("lib")
    pv.add_argument("spec")
    pv.set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()