#!/usr/bin/env python3
"""
Split "unsafe" into memory-unsafety and exposability disagreement.

    python3 eval/04f_unsafe_breakdown.py

04b_tally_audit.py counts three things as unsafe:

    owner=caller where the label says library      -> double free
    lifecycle=destroys where the label says not    -> use after free
    bound a function the label marks should_bind=n -> "unsafe to expose"

Only the first two are memory-safety claims. The third says the binding
exposed something the labeller judged unexposable, and on the extended sample
every instance of it is a struct-of-function-pointers initialiser --
cJSON_InitHooks, git_remote_init_callbacks, git_submodule_update_init_options,
git_worktree_add_init_options. Reading their implementations, none can crash:
cJSON_InitHooks null-checks every member and falls back to malloc/free, and
git_remote_init_callbacks writes a template into the struct and reads nothing.
A binding that hands them a zeroed buffer is correct but useless -- the caller
cannot install a callback through a protocol boundary.

That distinction matters because the paper's claim is about memory safety:
"an unresolved ownership question degrades to a leak rather than a double
free". Reporting a useless-but-safe binding under the same heading as a
double-free invitation overstates the error rate and understates the claim.

This reads the same CSVs and reports both separately. It does not modify 04b,
whose pooled figure remains the conservative one.
"""
from __future__ import annotations

import csv
import os

AUDIT = "eval_output/audit"
LIBS = ["cjson", "sqlite", "zlib", "libpng", "libpq", "libgit2", "libxml2"]


def norm(v):
    return (v or "").strip().lower()


def main():
    mem, expo, leaks = [], [], []
    n = 0
    for lib in LIBS:
        b = f"{AUDIT}/audit_{lib}_blind.csv"
        k = f"{AUDIT}/audit_{lib}_key.csv"
        if not (os.path.exists(b) and os.path.exists(k)):
            continue
        key = {r["function"]: r for r in csv.DictReader(open(k, newline=""))}
        for r in csv.DictReader(open(b, newline="")):
            f = r["function"]
            kr = key.get(f)
            if kr is None:
                continue
            n += 1
            lo, ll = norm(r.get("label_owner")), norm(r.get("label_lifecycle"))
            sb = norm(r.get("label_should_bind")) or "y"
            fo, fl = norm(kr.get("ferrule_owner")), norm(kr.get("ferrule_lifecycle"))
            fb = norm(kr.get("ferrule_bound"))

            if fo == "caller" and lo in ("library", "shared"):
                mem.append((lib, f, "owner=caller, label says the library owns it"))
            elif fl == "destroys" and ll and ll != "destroys":
                mem.append((lib, f, f"lifecycle=destroys, label says {ll}"))
            elif fb == "y" and sb == "n":
                expo.append((lib, f, "bound; label says it should not be exposed"))

            if fo in ("library", "") and lo == "caller" and fb == "y":
                leaks.append((lib, f, "owner=library, label says caller"))

    print(f"\n{n} labelled functions\n")
    print(f"MEMORY-UNSAFE  ({len(mem)})  -- permits an operation that corrupts memory")
    for lib, f, why in mem:
        print(f"  {lib:<9} {f:<38} {why}")
    print(f"\nEXPOSABILITY  ({len(expo)})  -- bound, but the label says unexposable")
    for lib, f, why in expo:
        print(f"  {lib:<9} {f:<38} {why}")
    print(f"\nLEAK  ({len(leaks)})  -- forgoes a legitimate free")
    for lib, f, why in leaks:
        print(f"  {lib:<9} {f:<38} {why}")

    if n:
        print(f"\nmemory-unsafe {len(mem)}/{n} = {100*len(mem)/n:.1f}%"
              f"   exposability {len(expo)}/{n} = {100*len(expo)/n:.1f}%"
              f"   leak {len(leaks)}/{n} = {100*len(leaks)/n:.1f}%")
        try:
            from math import sqrt

            def wilson(k, tot, z=1.96):
                p, d = k / tot, 1 + z * z / tot
                c = (p + z * z / (2 * tot)) / d
                m = z * sqrt(p * (1 - p) / tot + z * z / (4 * tot * tot)) / d
                return 100 * (c - m), 100 * (c + m)
            lo, hi = wilson(len(mem), n)
            print(f"memory-unsafe Wilson 95%: [{lo:.1f}%, {hi:.1f}%]")
        except Exception:
            pass
    print("""
The exposability rows are a coverage limitation, not a memory-safety failure:
the binding allocates a zeroed options struct and the initialiser fills it in,
which is correct use, but the caller cannot then install a callback through a
protocol boundary. Report them, and report them apart from the memory rate.""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
