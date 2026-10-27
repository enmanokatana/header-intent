#!/usr/bin/env python3
"""
Runtime cost for Table XIV.

    python3 eval/14_runtime_cost.py ~/ferrule-libs/cJSON/libcjson.so snapshots/cjson_esc.yaml

  lookup    HandleTable.get on a table holding N handles, N = 10^2 .. 10^6
  wrapped   cJSON_GetArraySize through the generated Python binding
  bare      the same C function through plain ctypes, for the overhead

Each figure is the median of 7 repetitions of a timeit loop, in ns per call.
"""
import ctypes
import os
import platform
import random
import statistics
import sys
import timeit

sys.path.insert(0, ".")
from src.core.handles import HandleTable
from src.emit.python import bind_module


def ns_per(fn, number, repeat=7):
    return statistics.median(timeit.repeat(fn, number=number, repeat=repeat)) / number * 1e9


def main():
    so, spec = os.path.expanduser(sys.argv[1]), sys.argv[2]
    print(f"python {platform.python_version()}  {platform.machine()}  {platform.platform()}")

    print("\nhandle-table lookup")
    for n in (10**2, 10**3, 10**4, 10**5, 10**6):
        t = HandleTable()
        ids = [t.put(object(), owned=True) for _ in range(n)]
        probe = random.Random(0).sample(ids, min(1000, n))
        get = t.get

        def sweep():
            for i in probe:
                get(i)

        print(f"  {n:>9,} handles: {ns_per(sweep, 100) / len(probe):7.1f} ns")

    m = bind_module(so, spec, name="cost")
    h = m.cJSON_Parse(value="[1,2,3]")["handle"]
    wrapped = ns_per(lambda: m.cJSON_GetArraySize(handle=h), 200000)

    lib = ctypes.CDLL(so)
    lib.cJSON_Parse.restype = ctypes.c_void_p
    lib.cJSON_Parse.argtypes = [ctypes.c_char_p]
    lib.cJSON_GetArraySize.restype = ctypes.c_int
    lib.cJSON_GetArraySize.argtypes = [ctypes.c_void_p]
    p = lib.cJSON_Parse(b"[1,2,3]")
    bare = ns_per(lambda: lib.cJSON_GetArraySize(p), 200000)

    print("\ncall cost (cJSON_GetArraySize)")
    print(f"  wrapped (Ferrule): {wrapped:7.1f} ns  ({1e9 / wrapped / 1e6:.2f} M calls/s)")
    print(f"  bare ctypes:       {bare:7.1f} ns")
    print(f"  overhead:          {wrapped - bare:7.1f} ns per call")


if __name__ == "__main__":
    main()