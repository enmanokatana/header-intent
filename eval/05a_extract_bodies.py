#!/usr/bin/env python3
"""
Extract the declaration and implementation body of every sampled function.

    python3 eval/05a_extract_bodies.py

Writes snapshots/bodies_<lib>.json: {name: {"decl": ..., "body": ..., "file": ...}}

The LLM baseline must see the SAME input Ferrule sees -- the public declaration
and the implementation source -- or the comparison measures input, not method.
Functions whose defining file does not parse get body=null; those are recorded
rather than dropped, because "the source was unavailable" is a real condition
both systems face.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys

from clang import cindex

L = os.path.expanduser("~/ferrule-libs")

# mirrors run_libs.sh
LIBS = {
    "cjson": dict(header=f"{L}/cJSON/cJSON.h",
                  sources=[f"{L}/cJSON/cJSON.c"],
                  args=[f"-I{L}/cJSON"]),
    "sqlite": dict(header=f"{L}/sqlite/sqlite3.h",
                   sources=[f"{L}/sqlite/sqlite3.c"],
                   args=[f"-I{L}/sqlite"]),
    "zlib": dict(header=f"{L}/zlib/zlib.h",
                 sources=sorted(glob.glob(f"{L}/zlib/*.c")),
                 args=[f"-I{L}/zlib"]),
    "libpng": dict(header=f"{L}/libpng/png.h",
                   sources=sorted(glob.glob(f"{L}/libpng/*.c")),
                   args=[f"-I{L}/libpng", f"-I{L}/zlib"]),
    "libpq": dict(header=f"{L}/postgresql/src/interfaces/libpq/libpq-fe.h",
                  sources=sorted(glob.glob(
                      f"{L}/postgresql/src/interfaces/libpq/*.c")),
                  args=[f"-I{L}/postgresql/src/include",
                        f"-I{L}/postgresql/src/port",
                        f"-I{L}/postgresql/src/interfaces/libpq"]),
    "libgit2": dict(header=f"{L}/libgit2/include/git2.h",
                    sources=sorted(glob.glob(f"{L}/libgit2/src/libgit2/**/*.c",
                                             recursive=True)),
                    args=[f"-I{L}/libgit2/include", f"-I{L}/libgit2/src/util",
                          f"-I{L}/libgit2/src/libgit2",
                          f"-I{L}/libgit2/build/src/util",
                          f"-I{L}/libgit2/deps/xdiff", f"-I{L}/libgit2/deps/pcre",
                          f"-I{L}/libgit2/deps/ntlmclient"]),
}

AUDIT = "eval_output/audit"
OUT = "snapshots"


def wanted(lib):
    p = f"{AUDIT}/audit_{lib}_blind.csv"
    if not os.path.exists(p):
        return set()
    with open(p, newline="") as f:
        return {r["function"] for r in csv.DictReader(f)}


def text_of(cursor):
    e = cursor.extent
    try:
        with open(e.start.file.name, errors="replace") as f:
            return f.read()[e.start.offset:e.end.offset]
    except Exception:
        return None


def main():
    os.makedirs(OUT, exist_ok=True)
    index = cindex.Index.create()
    for lib, cfg in LIBS.items():
        names = wanted(lib)
        if not names:
            continue
        found = {n: {"decl": None, "body": None, "file": None} for n in names}

        # declarations from the public header
        try:
            tu = index.parse(cfg["header"], args=cfg["args"])
            for c in tu.cursor.walk_preorder():
                if (c.kind == cindex.CursorKind.FUNCTION_DECL
                        and c.spelling in names and not c.is_definition()):
                    found[c.spelling]["decl"] = " ".join(
                        (text_of(c) or "").split())
        except Exception as e:
            print(f"  ! {lib}: header parse failed: {e}")

        # bodies from the implementation sources
        remaining = {n for n in names if found[n]["body"] is None}
        for src in cfg["sources"]:
            if not remaining:
                break
            try:
                tu = index.parse(src, args=cfg["args"])
            except Exception:
                continue
            for c in tu.cursor.walk_preorder():
                if (c.kind == cindex.CursorKind.FUNCTION_DECL
                        and c.is_definition() and c.spelling in remaining):
                    t = text_of(c)
                    if t:
                        found[c.spelling]["body"] = t
                        found[c.spelling]["file"] = os.path.basename(src)
                        remaining.discard(c.spelling)

        with open(f"{OUT}/bodies_{lib}.json", "w") as f:
            json.dump(found, f, indent=1)
        have = sum(1 for v in found.values() if v["body"])
        decl = sum(1 for v in found.values() if v["decl"])
        print(f"  {lib:<9} {len(names):>3} sampled, {decl:>3} decls, "
              f"{have:>3} bodies  -> {OUT}/bodies_{lib}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
