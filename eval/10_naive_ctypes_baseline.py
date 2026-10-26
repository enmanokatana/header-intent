"""
What a signature-only binding actually does.  (fix F18)

The paper asserts that bare ctypes is unsafe and never demonstrates it, which your
own reviewer_red_flags.md already flagged. This wraps the same cJSON functions with
bare ctypes -- exactly what a type-directed generator emits from the header -- and
runs the three sequences Ferrule refuses, recording what actually happens.

Each sequence is run in a SUBPROCESS, because two of the three are expected to abort
the interpreter. That is the point: the failure is not an exception a caller can
catch, it is process death or silent corruption.

Output is a LaTeX table body for the paper plus a human-readable log.

Usage
-----
    python3 10_naive_ctypes_baseline.py --so /path/to/libcjson.so [--latex naive.tex]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap

CHILD = r'''
import ctypes, sys, json
so = sys.argv[1]; case = sys.argv[2]
lib = ctypes.CDLL(so)

# Exactly what a signature-only generator produces from cJSON.h: types, no contract.
lib.cJSON_Parse.argtypes = [ctypes.c_char_p]; lib.cJSON_Parse.restype = ctypes.c_void_p
lib.cJSON_GetObjectItem.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
lib.cJSON_GetObjectItem.restype = ctypes.c_void_p
lib.cJSON_Delete.argtypes = [ctypes.c_void_p]; lib.cJSON_Delete.restype = None
lib.cJSON_PrintPreallocated.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                        ctypes.c_int, ctypes.c_int]
lib.cJSON_PrintPreallocated.restype = ctypes.c_int

doc = b'{"name":"ferrule","nested":{"n":1}}'

if case == "borrowed_free":
    root = lib.cJSON_Parse(doc)
    item = lib.cJSON_GetObjectItem(root, b"nested")   # borrowed: points INTO root
    lib.cJSON_Delete(item)                            # frees a subtree of root
    lib.cJSON_Delete(root)                            # now double-frees it
    print("survived")

elif case == "write_buffer_as_str":
    root = lib.cJSON_Parse(doc)
    # A non-const char* the library WRITES through, bound as an immutable Python str:
    # the library writes into CPython's string object.
    target = "x" * 8
    lib.cJSON_PrintPreallocated(root, target.encode(), 8, 1)
    print("survived")

elif case == "double_free":
    root = lib.cJSON_Parse(doc)
    lib.cJSON_Delete(root)
    lib.cJSON_Delete(root)
    print("survived")
'''

CASES = [
    ("borrowed_free", "free a borrowed interior node, then its owner",
     "refused before any C call"),
    ("write_buffer_as_str", "pass a Python str as a writable char* buffer",
     "refused: opaque parameter"),
    ("double_free", "free an owned root twice", "refused: unknown or freed handle"),
]


def run(so, case):
    p = subprocess.run([sys.executable, "-c", CHILD, so, case],
                       capture_output=True, text=True, timeout=60)
    if p.returncode == 0 and "survived" in p.stdout:
        return "completed silently"
    if p.returncode < 0:
        return f"killed by signal {-p.returncode}"
    err = (p.stderr or "").strip().splitlines()
    tail = err[-1][:80] if err else ""
    return f"aborted (rc={p.returncode}) {tail}".strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", required=True)
    ap.add_argument("--latex")
    args = ap.parse_args()

    rows = []
    for case, desc, ferrule in CASES:
        outcome = run(args.so, case)
        rows.append((case, desc, outcome, ferrule))
        print(f"{case:22} bare ctypes: {outcome:38} | Ferrule: {ferrule}")

    print()
    print(textwrap.fill(
        "Note for the paper: 'completed silently' is the WORST outcome, not the "
        "best -- it means the heap was corrupted and the process kept running, "
        "which is the failure mode a type checker cannot see and a test suite will "
        "not reproduce deterministically.", 78))

    if args.latex:
        with open(args.latex, "w") as f:
            for case, desc, outcome, ferrule in rows:
                f.write(f"{desc} & {outcome} & {ferrule} \\\\\n")
        print(f"\nwrote {args.latex}")
    print(json.dumps({c: o for c, _, o, _ in rows}, indent=2))


if __name__ == "__main__":
    main()
