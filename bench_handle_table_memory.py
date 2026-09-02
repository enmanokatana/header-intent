"""
Memory-footprint companion to bench_handle_table.py.

Measures the Python-side bookkeeping cost of HandleTable itself -- i.e. the
_items/_owned dicts -- independent of whatever the handle points to (the C-side
allocation, e.g. a parsed cJSON tree, is unaffected by this and lives in the C
heap regardless of whether Ferrule tracks it).

Two measurements per table size:
  - tracemalloc delta: precise bytes attributable to Python allocations made
    while populating the table (dict growth + the object identities themselves).
  - RSS delta (resource.ru_maxrss): real-world process memory high-water mark,
    includes allocator overhead/fragmentation tracemalloc doesn't count.

Each key maps to a *distinct* Python int simulating a distinct C pointer address
(small cached ints below 257 would understate this -- real pointers are large
and never share identity).

Usage: venv/bin/python bench_handle_table_memory.py
"""

from __future__ import annotations

import gc
import resource
import tracemalloc

from src.core.handles import HandleTable

SIZES = (1_000, 10_000, 100_000, 1_000_000)
BASE_ADDR = 0x7F0000000000  # plausible-looking heap address, forces unique ints


def rss_kb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KB on Linux


def measure(size: int):
    gc.collect()
    tracemalloc.start()
    rss_before = rss_kb()
    snap_before = tracemalloc.take_snapshot()

    table = HandleTable()
    for i in range(size):
        table.put(BASE_ADDR + i * 64, owned=True)  # distinct fake pointer per handle

    snap_after = tracemalloc.take_snapshot()
    rss_after = rss_kb()
    traced_bytes = sum(s.size_diff for s in snap_after.compare_to(snap_before, "filename"))
    tracemalloc.stop()

    return table, traced_bytes, (rss_after - rss_before) * 1024  # KB -> bytes


def main():
    print(f"{'live handles':>13} | {'tracemalloc':>14} | {'bytes/handle':>13} | "
          f"{'RSS delta':>12} | {'bytes/handle (RSS)':>18}")
    print("-" * 82)
    tables = []  # keep alive so sizes don't overlap/get GC'd between rows
    for size in SIZES:
        table, traced, rss_delta = measure(size)
        tables.append(table)
        print(f"{size:>13,} | {traced/1024:>11.1f} KB | {traced/size:>10.1f} B | "
              f"{rss_delta/1024:>9.1f} KB | {rss_delta/size:>15.1f} B")

    print()
    print("For reference, a bare Python dict of size 1,000,000 mapping int->int "
          "costs on the order of tens of MB in CPython; HandleTable keeps TWO such "
          "dicts (_items, _owned), so its footprint is expected to be a small "
          "multiple of one dict's overhead, not a new order of magnitude.")


if __name__ == "__main__":
    main()
