"""
verify_out_params exists to answer one question: "does this out/inout param
actually get written." For a function with NO by-ref out/inout params, there
is nothing to verify -- yet the probe used to call the real C function anyway,
purely because its signature happened to be all-scalar (the eligibility filter
only excludes STRING/OPAQUE/HANDLE/ARRAY roles, not "has zero out-params").

Found via a live sqlite3 MCP server: sqlite3_hard_heap_limit64(int64 n) takes
n BY VALUE and returns the previous limit -- no out-params at all -- but sets
a GLOBAL, PERSISTENT allocator ceiling as a side effect. Probing it with a
sentinel like 0x5150 (~20KB) permanently capped the process's memory limit,
so every subsequent sqlite3_open failed with SQLITE_NOMEM. The bug was not
sqlite3-specific: it's a gap in the probe's own methodology, "all-scalar
signature" does not imply "safe to call with synthetic values," it only held
for cJSON's stateless API by coincidence.

Fix: skip the call entirely when out_params is empty. This is lossless (there
was nothing to learn) and removes the unconditional real-function call for
any by-value-only function, regardless of what side effects it might have.
"""
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.spec.vocab import Role, Intent
from src.spec.schema import FunctionSpec, ParamSpec, Evidenced
from src.verify.probes import verify_out_params

REAL_C = r"""
#include <stdlib.h>
static long g_limit = -1;
long dangerous_set_limit(long n) { g_limit = n; return n; }
void divmod_(int a, int b, int *q, int *r) { *q = a / b; *r = a % b; }
int get_limit(void) { return (int)g_limit; }
"""


@pytest.fixture(scope="module")
def so(tmp_path_factory):
    d = tmp_path_factory.mktemp("probe_side_effects")
    src, lib = d / "r.c", d / "l.so"
    src.write_text(REAL_C)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(lib), str(src)], check=True)
    return str(lib)


def _dangerous_fn():
    return FunctionSpec("dangerous_set_limit", [
        ParamSpec("n", Role.SCALAR, Evidenced(Intent.IN, ["type"], 1.0, verified=True),
                 "c_long", by_ref=False),
    ], restype="c_long")


def _divmod_fn():
    return FunctionSpec("divmod_", [
        ParamSpec("a", Role.SCALAR, Evidenced(Intent.IN, ["type"], 1.0, verified=True),
                 "c_int", by_ref=False),
        ParamSpec("b", Role.SCALAR, Evidenced(Intent.IN, ["type"], 1.0, verified=True),
                 "c_int", by_ref=False),
        ParamSpec("q", Role.SCALAR, Evidenced(Intent.OUT, ["type"], 0.5, verified=False),
                 "c_int", by_ref=True),
        ParamSpec("r", Role.SCALAR, Evidenced(Intent.OUT, ["type"], 0.5, verified=False),
                 "c_int", by_ref=True),
    ], restype=None)


def test_no_out_params_means_no_call_at_all(so):
    """THE fix: a by-value-only function must never be called by the probe,
    since there is nothing it could possibly confirm."""
    lib = ctypes.CDLL(so)
    get_limit = lib.get_limit
    get_limit.restype = ctypes.c_int
    before = get_limit()

    result = verify_out_params(lib, _dangerous_fn())

    after = get_limit()
    assert result == {}
    assert after == before, "the real function must never have been called"

def test_genuine_out_params_are_still_verified(so):
    """The fix must not regress real out-param verification (cJSON's actual
    use case: divmod-style functions with real by-ref out params)."""
    lib = ctypes.CDLL(so)
    result = verify_out_params(lib, _divmod_fn())
    assert result == {"q": True, "r": True}
