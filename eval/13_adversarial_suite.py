#!/usr/bin/env python3
"""
Adversarial ownership and lifecycle suite. Each scenario runs in its own
process through the real Python binding; a crash is recorded, not fatal.

    python3 eval/13_adversarial_suite.py \
        --cjson  ~/ferrule-libs/cJSON/libcjson.so:snapshots/cjson_esc.yaml \
        --sqlite ~/ferrule-libs/libsqlite3.so:snapshots/sqlite_audit.yaml

Outcome classes
  CORRECT          the sequence behaves as the library's contract requires
  REFUSED          the binding refuses the unsafe step before calling C
  UNSAFE ACCEPTED  the binding passes a freed or transferred object to C;
                   no crash was observed, but the access is invalid
  MEMORY ERROR     the process was killed (double free, segfault)
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys

PRELUDE = r'''
import os, re, sys
sys.path.insert(0, ".")
from src.emit.python import bind_module
m = bind_module(os.path.expanduser(SO), SPEC, name="adv")
def call(name, *args):
    f = getattr(m, name, None)
    if f is None:
        print(f"  {name}: NOT BOUND"); print("OUTCOME: NOT RUN | " + name + " not bound"); sys.exit(0)
    mt = re.match(r"\s*[\w.]+\((.*?)\)", f.__doc__ or "")
    names = [p.strip() for p in mt.group(1).split(",") if p.strip()] if mt else []
    try:
        r = f(**dict(zip(names, args))); print(f"  {name}{args} -> {r!r}"[:150], flush=True); return True, r
    except Exception as e:
        print(f"  {name}{args} -> {type(e).__name__}: {e}"[:150], flush=True); return False, None
def h(r):
    return r.get("handle", r.get("state")) if isinstance(r, dict) else r
def outcome(cls, why):
    print(f"OUTCOME: {cls} | {why}", flush=True); sys.exit(0)
'''

SCENARIOS = {
    "cjson": [
        ("attachment", "an owned node added to a tree is then freed on its own", r'''
ok, a = call("cJSON_CreateObject"); a = h(a)
ok, b = call("cJSON_CreateString", "v"); b = h(b)
ok, _ = call("cJSON_AddItemToObject", a, b, "k")
if not ok: outcome("NOT RUN", "the attach itself failed")
ok, _ = call("cJSON_Delete", b)
if not ok: outcome("REFUSED", "freeing a node after it was attached")
call("cJSON_Delete", a)
outcome("UNSAFE ACCEPTED", "the attached node was freed, then freed again with its parent")
'''),
        ("detachment", "a borrowed handle is used after its node is detached and freed", r'''
ok, a = call("cJSON_Parse", '{"x":{"y":1}}'); a = h(a)
ok, c = call("cJSON_GetObjectItem", a, "x"); c = h(c)
ok, d = call("cJSON_DetachItemFromObject", a, "x"); d = h(d)
if not ok or d is None: outcome("NOT RUN", "the detach itself failed")
ok, _ = call("cJSON_Delete", d)
if not ok: outcome("REFUSED", "freeing the detached node")
ok, _ = call("cJSON_GetObjectItem", c, "y")
if not ok: outcome("CORRECT", "the stale borrowed handle was refused")
outcome("UNSAFE ACCEPTED", "a borrowed handle to the freed node was still accepted")
'''),
        ("replacement", "a borrowed handle is used after its node is replaced", r'''
ok, a = call("cJSON_Parse", '{"x":{"y":1}}'); a = h(a)
ok, c = call("cJSON_GetObjectItem", a, "x"); c = h(c)
ok, n = call("cJSON_CreateObject"); n = h(n)
ok, _ = call("cJSON_ReplaceItemInObject", a, n, "x")
if not ok: outcome("NOT RUN", "the replace itself failed")
ok, _ = call("cJSON_GetObjectItem", c, "y")
if not ok: outcome("CORRECT", "the handle to the replaced node was refused")
outcome("UNSAFE ACCEPTED", "a borrowed handle to the replaced, freed node was still accepted")
'''),
        ("deletion", "a borrowed handle is used after its parent deletes it", r'''
ok, a = call("cJSON_Parse", '{"x":{"y":1}}'); a = h(a)
ok, c = call("cJSON_GetObjectItem", a, "x"); c = h(c)
ok, _ = call("cJSON_DeleteItemFromObject", a, "x")
if not ok: outcome("NOT RUN", "the delete itself failed")
ok, _ = call("cJSON_GetObjectItem", c, "y")
if not ok: outcome("CORRECT", "the handle to the deleted child was refused")
outcome("UNSAFE ACCEPTED", "a borrowed handle to the deleted child was still accepted")
'''),
        ("mixed ownership", "a node created by its parent is freed directly, then via the parent", r'''
ok, a = call("cJSON_CreateObject"); a = h(a)
ok, b = call("cJSON_AddObjectToObject", a, "o"); b = h(b)
ok, _ = call("cJSON_Delete", b)
if ok: call("cJSON_Delete", a); outcome("UNSAFE ACCEPTED", "a parent-owned node was freed directly")
call("cJSON_Delete", a)
ok, _ = call("cJSON_GetObjectItem", b, "z")
if not ok: outcome("CORRECT", "direct free refused; node invalidated with its parent")
outcome("UNSAFE ACCEPTED", "direct free refused, but the node survived its parent")
'''),
    ],
    "sqlite": [
        ("failed operation", "a failed open still returns a handle that must be closed", r'''
ok, r = call("sqlite3_open", "/nonexistent-dir/x.db")
hh = h(r); st = r.get("status") if isinstance(r, dict) else None
if hh is None: outcome("REFUSED", "no handle returned for the failed open, so it cannot be closed")
ok, c = call("sqlite3_close", hh)
if ok and st not in (0, None): outcome("CORRECT", f"open failed (status {st}); its handle was still closed")
outcome("CORRECT" if ok else "REFUSED", f"open status {st}, close accepted={ok}")
'''),
    ],
}


def run(lib, so, spec, name, desc, body):
    code = f"SO={so!r}\nSPEC={spec!r}\n" + PRELUDE + body
    env = dict(os.environ, MALLOC_PERTURB_="165")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60)
    steps = [l for l in p.stdout.splitlines() if not l.startswith("OUTCOME:")]
    out = next((l for l in p.stdout.splitlines() if l.startswith("OUTCOME:")), None)
    if p.returncode < 0:
        cls, why = "MEMORY ERROR", f"killed by {signal.Signals(-p.returncode).name}"
    elif out:
        cls, why = [s.strip() for s in out[len("OUTCOME:"):].split("|", 1)]
    else:
        cls, why = "HARNESS ERROR", (p.stderr.strip().splitlines() or ["no output"])[-1]
    print(f"\n[{cls}] {lib} / {name}: {desc}\n  -> {why}")
    for s in steps:
        print(s)
    return cls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cjson"); ap.add_argument("--sqlite")
    a = ap.parse_args()
    results = []
    for lib in ("cjson", "sqlite"):
        arg = getattr(a, lib)
        if not arg:
            continue
        so, spec = arg.split(":", 1)
        for name, desc, body in SCENARIOS[lib]:
            results.append((lib, name, run(lib, so, spec, name, desc, body)))
    print("\nSUMMARY")
    for lib, name, cls in results:
        print(f"  {lib:7} {name:18} {cls}")


if __name__ == "__main__":
    main()