#!/usr/bin/env python3
"""
Execute the suspected memory errors through Ferrule's real Python binding.

    python3 eval/09_runtime_consequences.py \
        --zlib    /path/libz.so:/path/zlib_spec.yaml \
        --libgit2 /path/libgit2.so:/path/libgit2_spec.yaml \
        --libpq   /path/libpq.so:/path/libpq_spec.yaml \
        --libpng  /path/libpng16.so:/path/libpng_spec.yaml

Any subset of libraries may be given. Each scenario runs in its own process,
because a confirmed double free is expected to kill it.

What each scenario tests
------------------------
gzclose / git_cred_free / git_config_entry_free  (verdict "uses", label "destroys")
    Free the object through the binding, then call the destructor again on the
    same handle. If the runtime still serves the handle, the second call touches
    freed memory: expect SIGABRT (glibc double-free detection) or SIGSEGV.
    A clean REFUSED instead means the runtime does NOT have the bug.

PQconnectPoll  (verdict "destroys", label "uses")
    Call it, then call PQstatus on the same handle. Expect PQstatus to be
    REFUSED (handle dropped) with NO crash: safe but broken.

png_destroy_info_struct, png_get_PLTE
    Only print how the binding exposes them (which parameters are inputs, what
    the lifecycle tag says), since they need a real PNG to exercise.

MALLOC_PERTURB_ fills freed memory with a byte pattern, so a read through a
dangling handle produces garbage instead of plausible stale data.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import tempfile

PRELUDE = r'''
import sys, re, os, tempfile
sys.path.insert(0, ROOT)
from src.emit.python import bind_module
m = bind_module(SO, SPEC, name="t")

def show(n):
    f = getattr(m, n, None)
    if f is None:
        why = [r for r in getattr(m, "_refused", []) if n in str(r)]
        print(f"  {n}: NOT BOUND  {why[:1]}")
        return None
    print(f"  {n}: {f.__doc__}")
    return f

def params(f):
    mt = re.match(r"\s*[\w.]+\((.*?)\)", f.__doc__ or "")
    return [p.strip() for p in mt.group(1).split(",") if p.strip()] if mt else []

def call(n, *args):
    f = getattr(m, n, None)
    if f is None:
        print(f"  {n}: NOT BOUND"); return None
    kw = dict(zip(params(f), args))
    try:
        r = f(**kw)
        print(f"  {n}{tuple(args)} -> {r!r}", flush=True)
        return r
    except Exception as e:
        print(f"  {n}{tuple(args)} -> {type(e).__name__}: {e}", flush=True)
        return None

def hid(r):
    if isinstance(r, int):
        return r
    if isinstance(r, dict):
        if isinstance(r.get("handle"), int):
            return r["handle"]
        for k, v in r.items():
            if k not in ("status", "result", "borrowed", "note", "freed",
                         "live_handles") and isinstance(v, int):
                return v
    if isinstance(r, (tuple, list)):
        for v in r:                      # (handle, status) per Table II
            if isinstance(v, int):
                return v
    return None
'''

SCENARIOS = {
    "zlib": [
        ("gzclose twice (missed destroy)", r'''
show("gzopen"); show("gzclose")
path = os.path.join(tempfile.mkdtemp(), "t.gz")
h = hid(call("gzopen", path, "wb"))
print("  handle:", h)
call("gzclose", h)
print("  -- second gzclose on the same handle --", flush=True)
call("gzclose", h)
print("  reached end without crashing")
'''),
    ],
    "libgit2": [
        ("git_cred_free twice (missed destroy)", r'''
call("git_libgit2_init")
show("git_cred_userpass_plaintext_new"); show("git_cred_free")
h = hid(call("git_cred_userpass_plaintext_new", "user", "pass"))
print("  handle:", h)
call("git_cred_free", h)
print("  -- second git_cred_free on the same handle --", flush=True)
call("git_cred_free", h)
print("  reached end without crashing")
'''),
        ("git_config_entry_free twice (missed destroy)", r'''
call("git_libgit2_init")
show("git_config_open_ondisk"); show("git_config_get_entry"); show("git_config_entry_free")
d = tempfile.mkdtemp(); p = os.path.join(d, "cfg")
open(p, "w").write("[user]\n\tname = ferrule\n")
cfg = hid(call("git_config_open_ondisk", p))
e = hid(call("git_config_get_entry", cfg, "user.name"))
print("  config:", cfg, " entry:", e)
call("git_config_entry_free", e)
print("  -- second git_config_entry_free on the same handle --", flush=True)
call("git_config_entry_free", e)
print("  reached end without crashing")
'''),
    ],
    "libpq": [
        ("PQconnectPoll then PQstatus (false destroy)", r'''
show("PQconnectStart"); show("PQconnectPoll"); show("PQstatus")
h = hid(call("PQconnectStart", "host=127.0.0.1 port=1 connect_timeout=1"))
print("  handle:", h)
call("PQconnectPoll", h)
print("  -- PQstatus on the same handle (expect REFUSED, no crash) --", flush=True)
call("PQstatus", h)
print("  reached end without crashing")
'''),
    ],
    "libpng": [
        ("how the binding exposes the png rows", r'''
for n in ("png_destroy_info_struct", "png_get_PLTE", "png_get_sBIT",
          "png_get_sPLT", "png_get_tIME", "png_free", "png_destroy_read_struct"):
    show(n)
'''),
    ],
}


def describe(rc):
    if rc == 0:
        return "exit 0 (no crash)"
    if rc < 0:
        try:
            return f"KILLED by {signal.Signals(-rc).name}  <-- memory error confirmed"
        except ValueError:
            return f"killed by signal {-rc}"
    return f"exit {rc}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd(), help="repo root (contains src/)")
    for lib in SCENARIOS:
        ap.add_argument(f"--{lib}", metavar="SO:SPEC")
    a = ap.parse_args()

    env = dict(os.environ, MALLOC_PERTURB_="165", PYTHONUNBUFFERED="1")
    ran = False
    for lib, scenarios in SCENARIOS.items():
        arg = getattr(a, lib)
        if not arg:
            continue
        so, spec = arg.split(":", 1)
        for title, body in scenarios:
            ran = True
            code = (f"ROOT={a.root!r}\nSO={so!r}\nSPEC={spec!r}\n" + PRELUDE + body)
            print(f"\n=== {lib}: {title}")
            try:
                p = subprocess.run([sys.executable, "-c", code], env=env,
                                   capture_output=True, text=True, timeout=60)
                print(p.stdout.rstrip())
                err = p.stderr.strip().splitlines()
                if err:
                    print("  stderr: " + "\n  stderr: ".join(err[-4:]))
                print(f"  RESULT: {describe(p.returncode)}")
            except subprocess.TimeoutExpired:
                print("  RESULT: timed out after 60 s")
    if not ran:
        ap.error("give at least one --<lib> SO:SPEC")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
