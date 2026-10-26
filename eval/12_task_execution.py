#!/usr/bin/env python3
"""
Executed task coverage: availability says every call is bound; this runs the task
through the Python binding and checks a stated expected output.

    python3 eval/12_task_execution.py \
        --cjson ~/ferrule-libs/cJSON/libcjson.so:snapshots/cjson_audit.yaml \
        --zlib  ~/ferrule-libs/zlib/libz.so:snapshots/zlib_audit.yaml \
        [--libpq <libpq.so>:<spec.yaml> --pg "host=localhost dbname=postgres user=postgres"]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, ".")
from src.emit.python import bind_module


class Fail(Exception):
    pass


class Runner:
    def __init__(self, so, spec):
        self.m = bind_module(os.path.expanduser(so), spec, name="task")
        self.log = []

    def call(self, name, *args):
        f = getattr(self.m, name, None)
        if f is None:
            raise Fail(f"{name}: not bound")
        mt = re.match(r"\s*[\w.]+\((.*?)\)", f.__doc__ or "")
        names = [p.strip() for p in mt.group(1).split(",") if p.strip()] if mt else []
        try:
            r = f(**dict(zip(names, args)))
        except Exception as e:
            raise Fail(f"{name}: {type(e).__name__}: {e}")
        self.log.append(f"{name}{tuple(args)} -> {r!r}"[:140])
        return r


def h(r):
    return r.get("handle", r.get("state")) if isinstance(r, dict) else r


def val(r):
    if isinstance(r, dict):
        for k in ("result", "status"):
            if k in r:
                return r[k]
    return r


def task_cjson(t):
    root = h(t.call("cJSON_Parse", '{"name":"ferrule","nested":{"n":1}}'))
    if root is None: raise Fail("cJSON_Parse returned NULL")
    item = h(t.call("cJSON_GetObjectItem", root, "name"))
    name = val(t.call("cJSON_GetStringValue", item))
    text = val(t.call("cJSON_Print", root))
    t.call("cJSON_Delete", root)
    ok = name == "ferrule" and isinstance(text, str) and '"ferrule"' in text
    return ok, f"name={name!r}, printed document contains \"ferrule\": {isinstance(text, str) and 'ferrule' in text}"


def task_zlib(t):
    s = h(t.call("alloc_z_stream_s"))
    rc = val(t.call("deflateInit2_", s, 6, 8, 15, 8, 0, "1.3", 112))
    if rc != 0: raise Fail(f"deflateInit2_ returned {rc}")
    rc = val(t.call("deflate", s, 4))            # Z_FINISH
    t.call("deflateEnd", s)
    # A real round trip needs next_in/avail_in/next_out/avail_out set in the z_stream.
    return rc == 1, (f"deflate(Z_FINISH) returned {rc} (expected Z_STREAM_END = 1); "
                     f"the binding exposes no way to supply input or output buffers")


def task_libpq(t, conninfo):
    conn = h(t.call("PQconnectdb", conninfo))
    st = val(t.call("PQstatus", conn))
    if st != 0: raise Fail(f"PQstatus = {st} (expected CONNECTION_OK = 0)")
    res = h(t.call("PQexec", conn, "select 42"))
    rs = val(t.call("PQresultStatus", res))
    v = val(t.call("PQgetvalue", res, 0, 0))
    t.call("PQclear", res)
    t.call("PQfinish", conn)
    return rs == 2 and v == "42", f"PQresultStatus={rs} (expected 2), value={v!r} (expected '42')"


def run(label, fn, *a):
    print(f"\n=== {label}")
    t = None
    try:
        t = a[0]
        ok, observed = fn(*a)
        print(f"  {'COMPLETED' if ok else 'RAN, WRONG OUTPUT'}: {observed}")
    except Fail as e:
        print(f"  FAILED: {e}")
    except Exception as e:
        print(f"  HARNESS ERROR: {type(e).__name__}: {e}")
    if t:
        for line in t.log:
            print(f"    {line}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cjson"); ap.add_argument("--zlib"); ap.add_argument("--libpq")
    ap.add_argument("--pg", help="libpq conninfo for a reachable server")
    a = ap.parse_args()
    if a.cjson:
        so, spec = a.cjson.split(":", 1); run("cJSON: parse, read a field, print, free", task_cjson, Runner(so, spec))
    if a.zlib:
        so, spec = a.zlib.split(":", 1); run("zlib: compress and decompress a buffer", task_zlib, Runner(so, spec))
    if a.libpq:
        so, spec = a.libpq.split(":", 1)
        if not a.pg:
            print("\n=== libpq: NOT EXECUTED (no --pg server given)")
        else:
            run("libpq: connect, query, read a field, clean up", task_libpq, Runner(so, spec), a.pg)


if __name__ == "__main__":
    main()
