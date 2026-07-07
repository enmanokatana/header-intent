"""
ferrule CLI (phase 1).

  ferrule infer  <header.h> <lib.so> [--overrides o.yaml] -> writes spec.yaml
  ferrule verify <lib.so> <spec.yaml>                     -> probes + updates spec

`infer` needs the libclang/CAST parser to extract signatures from the header.
That parser lives in the cToMcp toolkit; here we import it if available and
otherwise explain how to point at it. The spec-building, verification, and
serialization are all self-contained in ferrule.
"""
import argparse
import ctypes
import sys

import yaml

from .spec.io import dump_yaml, load_yaml, dumps_yaml
from .layers.l1_signature import spec_from_signatures
from .verify.probes import apply_verification


def _load_signatures(header_path: str):
    """Bridge to the existing libclang/CAST parser to get ctypes signatures.
    Expected to return {fname: {argnames, argtypes, restype, pointers}}."""
    try:
        from header_parser_cast import parse_header   # from the cToMcp toolkit
    except ImportError:
        sys.exit(
            "could not import header_parser_cast. Put the cToMcp mcp/ toolkit on "
            "PYTHONPATH so ferrule can extract signatures from the header."
        )
    return parse_header(header_path)


def cmd_infer(args):
    signatures = _load_signatures(args.header)
    overrides = {}
    if args.overrides:
        overrides = yaml.safe_load(open(args.overrides)) or {}
    spec = spec_from_signatures(args.library_name or "lib", signatures, overrides)
    if args.lib:
        apply_verification(ctypes.CDLL(args.lib), spec)
    if args.out:
        dump_yaml(spec, args.out)
        print(f"wrote {args.out}")
    else:
        print(dumps_yaml(spec))


def cmd_verify(args):
    spec = load_yaml(args.spec)
    apply_verification(ctypes.CDLL(args.lib), spec)
    dump_yaml(spec, args.spec)
    print(f"verified and updated {args.spec}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ferrule")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("infer", help="header -> capability spec")
    pi.add_argument("header")
    pi.add_argument("lib", nargs="?", help="optional .so to behaviorally verify against")
    pi.add_argument("--overrides", help="YAML {func: {param: intent}} for exceptions")
    pi.add_argument("--library-name")
    pi.add_argument("-o", "--out", help="write spec here (else stdout)")
    pi.set_defaults(func=cmd_infer)

    pv = sub.add_parser("verify", help="probe a lib and update a spec's verified flags")
    pv.add_argument("lib")
    pv.add_argument("spec")
    pv.set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()