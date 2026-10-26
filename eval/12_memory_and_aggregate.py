"""
Two small fixes in one file.

(A) fix F28 -- corrected handle-table memory measurement.
    688 bytes/handle from ru_maxrss deltas is implausible for two dict entries, and
    the reported figure DECREASES at 1M handles, which is the signature of a noisy
    measurement (RSS includes the stored objects, allocator slack, and arena growth,
    and is not monotone in what you are trying to measure). tracemalloc plus
    sys.getsizeof on the two dicts separates the table's own bookkeeping from the
    objects it holds.

(B) fix F25 -- one coverage/refusal table for ALL six libraries.
    Table III currently reports refusal reasons for two libraries and Table V reports
    coverage for the other four. That asymmetry reads as selective reporting even
    when it is not.

Usage
-----
    python3 12_memory_and_aggregate.py memory
    python3 12_memory_and_aggregate.py aggregate --repo /path/to/header-intent \\
        --spec eval_results/cjson/spec.yaml --so .../libcjson.so [--spec ... --so ...] \\
        --latex coverage_table.tex
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import tracemalloc


# ------------------------------------------------------------------ (A) memory

def _import_handle_table():
    """Work both inside the repo (src.core.handles) and standalone next to the
    patched handles.py in ferrule_patches/core/."""
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.getcwd(), os.path.dirname(here), os.path.join(os.path.dirname(here), "core")):
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        from src.core.handles import HandleTable
        return HandleTable
    except ImportError:
        from handles import HandleTable
        return HandleTable


def measure_memory(counts=(1_000, 10_000, 100_000, 1_000_000)):
    HandleTable = _import_handle_table()

    print(f"{'live handles':>14} {'dict bytes/handle':>19} {'total tracemalloc/handle':>26}")
    print("-" * 62)
    for n in counts:
        tracemalloc.start()
        base = tracemalloc.get_traced_memory()[0]
        t = HandleTable()
        for i in range(n):
            t.put(i, owned=True)                  # store an int: no object overhead
        traced = tracemalloc.get_traced_memory()[0] - base
        dicts = sys.getsizeof(t._items) + sys.getsizeof(t._owned) \
            + sys.getsizeof(t._parent) + sys.getsizeof(t._children)
        tracemalloc.stop()
        print(f"{n:>14,} {dicts/n:>19.1f} {traced/n:>26.1f}")
        del t

    print()
    print("Report the dict column: it is the table's own bookkeeping, which is what the")
    print("paper claims to measure. The tracemalloc column includes the stored handle")
    print("objects, which belong to the caller, not to the table. If the two differ a")
    print("lot, say which one the table reports -- that sentence is the whole fix.")


# --------------------------------------------------------------- (B) aggregate

def aggregate(repo, specs, sos, latex=None):
    sys.path.insert(0, repo)
    from src.spec.io import load_yaml
    from src.core.invoker import build_capabilities
    from src.core.handles import HandleTable
    from src.core.policy import check_exposable, SpecViolation

    hdr = ("library", "exported", "bound", "refused", "opaque", "voidp",
           "lowconf", "lifecycle")
    rows = []
    for spec_path, so in zip(specs, sos):
        spec = load_yaml(spec_path)
        lib = ctypes.CDLL(so)
        caps, _ = build_capabilities(lib, spec, HandleTable())
        bound = {c.name for c in caps}

        opaque = voidp = lowconf = other = 0
        for name, fn in spec.functions.items():
            if name in bound:
                continue
            try:
                check_exposable(fn)
                other += 1
            except SpecViolation as e:
                msg = str(e)
                if "opaque" in msg:
                    opaque += 1
                elif "void*" in msg:
                    voidp += 1
                elif "low-confidence" in msg:
                    lowconf += 1
                else:
                    other += 1
        rows.append(dict(library=spec.library, exported=len(spec.functions),
                         bound=len(bound), refused=len(spec.functions) - len(bound),
                         opaque=opaque, voidp=voidp, lowconf=lowconf,
                         lifecycle=sum(1 for f in spec.functions.values() if f.lifecycle)))

    w = max(len(h) for h in hdr)
    print("  ".join(h.ljust(12) if h == "library" else h.rjust(w) for h in hdr))
    print("-" * 90)
    for r in rows:
        print("  ".join([r["library"].ljust(12)] + [str(r[h]).rjust(w) for h in hdr[1:]]))

    if latex:
        with open(latex, "w") as f:
            for r in rows:
                f.write(f"{r['library']} & {r['exported']} & {r['bound']} & "
                        f"{r['refused']} & {r['opaque']} & {r['voidp']} & "
                        f"{r['lowconf']} & {r['lifecycle']} \\\\\n")
        print(f"\nwrote {latex}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("memory")
    a = sub.add_parser("aggregate")
    a.add_argument("--repo", required=True)
    a.add_argument("--spec", action="append", required=True)
    a.add_argument("--so", action="append", required=True)
    a.add_argument("--latex")
    args = ap.parse_args()

    if args.cmd == "memory":
        measure_memory()
    else:
        aggregate(args.repo, args.spec, args.so, args.latex)


if __name__ == "__main__":
    main()
