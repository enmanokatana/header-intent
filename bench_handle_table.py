"""
Benchmark: overhead of Ferrule's HandleTable on the generated-binding call path.

Isolates three layers so the paper can state which one actually costs what:
  1. raw ctypes call            -- floor, no Ferrule involved
  2. HandleTable.get() alone    -- the dict lookup the reviewer is asking about
  3. full Capability.invoke()   -- what a real caller (MCP tool / gRPC handler /
                                   plain Python binding) actually pays per call

Run against the real cJSON fixture already used elsewhere in this repo
(reuse_cjson_test_manual.py), not a mock -- a compiled .so loaded via ctypes.CDLL,
driven through the same bind_module()/build_capabilities() path the generator emits.

Usage: venv/bin/python bench_handle_table.py
"""

from __future__ import annotations

import ctypes
import statistics
import timeit

from src.core.handles import HandleTable
from src.core.invoker import build_capabilities
from src.emit.python import bind_module
from src.spec.io import load_yaml

SO_PATH = "/tmp/cjson/libcjson.so"
SPEC_PATH = "cjson.spec.yaml"
N = 500_000
REPEATS = 7  # timeit repeats; report min (least noise) and median


def ns_per_call(fn, number=N, repeat=REPEATS):
    samples = timeit.repeat(fn, number=number, repeat=repeat)
    per_call_ns = [s / number * 1e9 for s in samples]
    return min(per_call_ns), statistics.median(per_call_ns)


def main():
    # --- shared setup: one parsed document, reused by all three layers ---
    lib = ctypes.CDLL(SO_PATH)
    spec = load_yaml(SPEC_PATH)
    handles = HandleTable()
    caps, refused = build_capabilities(lib, spec, handles)
    cap_by_name = {c.name: c for c in caps}

    m = bind_module(SO_PATH, SPEC_PATH)  # separate HandleTable instance, same .so
    doc_handle = m.cJSON_Parse(value="[1,2,3,4,5]")["handle"]

    doc_ptr_bench = handles  # table used for the raw/get-only layers below
    parse = lib.cJSON_Parse
    parse.argtypes = [ctypes.c_char_p]
    parse.restype = ctypes.c_void_p
    raw_ptr = parse(b"[1,2,3,4,5]")
    raw_hid = doc_ptr_bench.put(raw_ptr, owned=True)

    # --- layer 1: raw ctypes call, no Ferrule on the path at all ---
    get_size = lib.cJSON_GetArraySize
    get_size.argtypes = [ctypes.c_void_p]
    get_size.restype = ctypes.c_int
    assert get_size(raw_ptr) == 5
    t_raw_min, t_raw_med = ns_per_call(lambda: get_size(raw_ptr))

    # --- layer 2: HandleTable.get() in isolation (the dict lookup itself) ---
    assert handles.get(raw_hid) == raw_ptr
    t_get_min, t_get_med = ns_per_call(lambda: handles.get(raw_hid))

    # --- layer 3: full generated-binding call (Capability.invoke) ---
    cap = cap_by_name["cJSON_GetArraySize"]
    assert cap.invoke(handle=raw_hid) == 5
    t_invoke_min, t_invoke_med = ns_per_call(lambda: cap.invoke(handle=raw_hid))

    # --- layer 3b: through bind_module's public closure, i.e. what a caller
    #     of the emitted module actually calls (adds the **kwargs lambda hop) ---
    assert m.cJSON_GetArraySize(handle=doc_handle) == 5
    t_pub_min, t_pub_med = ns_per_call(lambda: m.cJSON_GetArraySize(handle=doc_handle))

    # --- layer 4: put()/pop() cost (lock + two dict ops), the lifecycle-mutating
    #     path used by "creates"/"destroys" rather than "uses" ---
    def put_pop_cycle():
        hid = handles.put(raw_ptr, owned=False)  # owned=False: skip actually freeing raw_ptr
        handles.get(hid)
        handles._items.pop(hid)
        handles._owned.pop(hid, None)

    t_pp_min, t_pp_med = ns_per_call(put_pop_cycle, number=100_000, repeat=REPEATS)

    def row(label, min_ns, med_ns):
        print(f"{label:38s} min={min_ns:8.1f} ns/call  median={med_ns:8.1f} ns/call"
              f"  ({1e9/min_ns:,.0f} calls/sec)")

    print(f"cJSON fixture: {SO_PATH}, N={N:,} calls, {REPEATS} repeats\n")
    row("raw ctypes call", t_raw_min, t_raw_med)
    row("HandleTable.get() alone", t_get_min, t_get_med)
    row("Capability.invoke() (uses)", t_invoke_min, t_invoke_med)
    row("bind_module() public call", t_pub_min, t_pub_med)
    row("put()+get()+pop() cycle", t_pp_min, t_pp_med)

    print()
    overhead_get = t_get_min
    overhead_invoke = t_invoke_min - t_raw_min
    marshalling = overhead_invoke - overhead_get
    print(f"handle-table lookup cost:        {overhead_get:.1f} ns/call")
    print(f"total Ferrule overhead vs raw:    {overhead_invoke:.1f} ns/call")
    print(f"  of which marshalling/dispatch:  {marshalling:.1f} ns/call "
          f"({marshalling/overhead_invoke*100:.0f}% of overhead)")
    print(f"  of which handle-table lookup:   {overhead_get:.1f} ns/call "
          f"({overhead_get/overhead_invoke*100:.0f}% of overhead)")

    m.cJSON_Delete(handle=doc_handle)

    # --- does the "hash map lookup" degrade as the table fills up? ---
    print("\nHandleTable.get() cost vs. number of live handles (O(1) check):")
    scale_table = HandleTable()
    dummy_hid = scale_table.put(raw_ptr, owned=False)
    for size in (10, 1_000, 100_000, 1_000_000):
        while len(scale_table) < size:
            scale_table.put(raw_ptr, owned=False)
        t_min, t_med = ns_per_call(lambda: scale_table.get(dummy_hid),
                                    number=200_000, repeat=5)
        print(f"  {size:>9,} live handles: min={t_min:6.1f} ns/call  median={t_med:6.1f} ns/call")


if __name__ == "__main__":
    main()
