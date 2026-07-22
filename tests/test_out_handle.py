
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.layers.l1_signature import spec_from_signatures
from src.core.invoker import build_capabilities
from src.core.handles import HandleTable
from src.core.policy import check_exposable, SpecViolation
from src.spec.vocab import Role, Intent
from src.spec.schema import Evidenced

REAL_C = r"""
#include <stdlib.h>
typedef struct sqlite3 { int magic; } sqlite3;
#define SQLITE_OK 0
#define SQLITE_CANTOPEN 14

int sqlite3_open(const char *filename, sqlite3 **ppDb) {
    if (filename == 0 || filename[0] == 0) { *ppDb = 0; return SQLITE_CANTOPEN; }
    sqlite3 *db = malloc(sizeof(sqlite3));
    db->magic = 12345;
    *ppDb = db;
    return SQLITE_OK;
}
int sqlite3_close(sqlite3 *db) { free(db); return SQLITE_OK; }
int sqlite3_get_magic(sqlite3 *db) { return db->magic; }
"""

SIG = {
    "sqlite3_open": {"argnames": ["filename", "ppDb"],
                     "argtypes": [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)],
                     "restype": ctypes.c_int, "pointers": {}},
    "sqlite3_close": {"argnames": ["db"], "argtypes": [ctypes.c_void_p],
                      "restype": ctypes.c_int, "pointers": {}},
    "sqlite3_get_magic": {"argnames": ["db"], "argtypes": [ctypes.c_void_p],
                          "restype": ctypes.c_int, "pointers": {}},
}


def _mark_handle(fn, pname, handle_type, lifecycle):
    for p in fn.params:
        if p.name == pname:
            p.role = Role.HANDLE
            p.handle_type = handle_type
            p.intent = Evidenced(Intent.IN, ["handle_analysis"], 0.9, verified=False)
    fn.lifecycle = lifecycle
    fn.handle_type = handle_type


def make_spec():
    s = spec_from_signatures("sqlite3", SIG,
                             out_handles={"sqlite3_open": {"ppDb": "sqlite3"}})
    _mark_handle(s.functions["sqlite3_close"], "db", "sqlite3", "destroys")
    _mark_handle(s.functions["sqlite3_get_magic"], "db", "sqlite3", "uses")
    return s


@pytest.fixture(scope="module")
def so(tmp_path_factory):
    d = tmp_path_factory.mktemp("sqlish")
    src, lib = d / "r.c", d / "l.so"
    src.write_text(REAL_C)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(lib), str(src)], check=True)
    return str(lib)


def test_l1_recognizes_out_handle_role():
    fn = make_spec().functions["sqlite3_open"]
    assert fn.handle_out_param == "ppDb"
    assert fn.lifecycle == "creates" and fn.owner == "caller"
    out_p = next(p for p in fn.params if p.name == "ppDb")
    assert out_p.role is Role.OUT_HANDLE
    assert out_p.handle_type == "sqlite3"

def test_open_success_returns_handle_and_status(so):
    lib = ctypes.CDLL(so)
    caps, refused = build_capabilities(lib, make_spec(), HandleTable())
    assert not refused
    t = {c.name: c for c in caps}
    r = t["sqlite3_open"].invoke(filename="test.db")
    assert r["status"] == 0
    assert r["handle"] is not None

def test_open_failure_returns_no_handle(so):
    lib = ctypes.CDLL(so)
    caps, _ = build_capabilities(lib, make_spec(), HandleTable())
    t = {c.name: c for c in caps}
    r = t["sqlite3_open"].invoke(filename="")
    assert r["handle"] is None
    assert r["status"] == 14

def test_handle_from_out_param_is_usable(so):
    lib = ctypes.CDLL(so)
    caps, _ = build_capabilities(lib, make_spec(), HandleTable())
    t = {c.name: c for c in caps}
    r = t["sqlite3_open"].invoke(filename="test.db")
    assert t["sqlite3_get_magic"].invoke(handle=r["handle"]) == 12345
    closed = t["sqlite3_close"].invoke(handle=r["handle"])
    assert closed["freed"] == r["handle"]


def test_scalar_voidp_out_param_is_refused():
    """Without OUT_HANDLE recognition (e.g. a plain 'out' hint on a void**),
    the param must NOT fall through as SCALAR -- that would expose a raw
    pointer address as a bare integer."""
    sig = {"raw_open": {"argnames": ["path", "out"],
                        "argtypes": [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)],
                        "restype": ctypes.c_int, "pointers": {"out": "out"}}}
    s = spec_from_signatures("t", sig)          # NOTE: no out_handles hint
    with pytest.raises(SpecViolation):
        check_exposable(s.functions["raw_open"])

def test_normal_scalar_out_params_still_work():
    """The new refusal must be specific to void* -- int*/double* out-params
    (divmod-style) must be unaffected."""
    sig = {"divmod_": {"argnames": ["a", "b", "q", "r"],
                       "argtypes": [ctypes.c_int, ctypes.c_int,
                                    ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)],
                       "restype": None, "pointers": {"q": "out", "r": "out"}}}
    s = spec_from_signatures("t", sig)
    check_exposable(s.functions["divmod_"])     # must not raise
