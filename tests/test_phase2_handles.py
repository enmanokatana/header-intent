
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.spec.vocab import Role
from src.layers.l1_signature import spec_from_signatures
from src.layers.l2_handles import analyze_handles, apply_handle_facts
from src.server.build import build_tools, build_tool, SpecViolation
from src.server.handles import HandleTable

C_SO = r"""
#include <stdlib.h>
typedef struct expr { double v; } expr;
expr *expr_create(double x) { expr *e = malloc(sizeof(expr)); e->v = x; return e; }
double expr_eval(expr *e) { return e->v; }
void expr_free(expr *e) { free(e); }
"""

C_SRC = r"""
typedef unsigned long size_t;
void *malloc(size_t); void free(void *);
typedef struct expr { double v; } expr;
expr *expr_create(double x) { expr *e = malloc(sizeof(expr)); e->v = x; return e; }
double expr_eval(expr *e) { return e->v; }
void expr_free(expr *e) { free(e); }
"""

SIGNATURES = {
    "expr_create": {"argnames": ["x"], "argtypes": [ctypes.c_double],
                    "restype": ctypes.c_void_p, "pointers": {}},
    "expr_eval": {"argnames": ["e"], "argtypes": [ctypes.c_void_p],
                  "restype": ctypes.c_double, "pointers": {}},
    "expr_free": {"argnames": ["e"], "argtypes": [ctypes.c_void_p],
                  "restype": None, "pointers": {}},
}


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    d = tmp_path_factory.mktemp("p2h")
    src, so = d / "l.c", d / "l.so"
    src.write_text(C_SO)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(so), str(src)], check=True)
    return ctypes.CDLL(str(so))


def test_lifecycle_roles_derived():
    facts, htypes = analyze_handles(C_SRC)
    assert htypes == {"expr"}
    assert facts["expr_create"].role == "creates"
    assert facts["expr_eval"].role == "uses"
    assert facts["expr_free"].role == "destroys"
    assert facts["expr_free"].handle_param == "e"

def test_only_handed_out_types_are_handles():
    src = r"""
    typedef struct opts { int n; } opts;
    int use_opts(opts *o) { return o->n; }
    """
    facts, htypes = analyze_handles(src)
    assert htypes == set()          # opts never returned -> not a handle
    assert facts == {}


def test_apply_upgrades_opaque_to_handle():
    spec = spec_from_signatures("expr", SIGNATURES)
    # before: e is a raw void* -> OPAQUE (unsafe to expose as a value)
    assert spec.functions["expr_eval"].params[0].role is Role.OPAQUE
    facts, _ = analyze_handles(C_SRC)
    apply_handle_facts(spec, facts)
    assert spec.functions["expr_eval"].params[0].role is Role.HANDLE
    assert spec.functions["expr_create"].lifecycle == "creates"
    assert spec.functions["expr_free"].lifecycle == "destroys"

def test_raw_void_ptr_refused_without_handle_analysis(lib):
    spec = spec_from_signatures("expr", SIGNATURES)
    with pytest.raises(SpecViolation):
        build_tool(lib, spec.functions["expr_eval"], HandleTable())


def test_generated_lifecycle_tools(lib):
    spec = spec_from_signatures("expr", SIGNATURES)
    apply_handle_facts(spec, analyze_handles(C_SRC)[0])
    H = HandleTable()
    t = {x.name: x for x in build_tools(lib, spec, H)}

    created = t["expr_create"].invoke(x=42.0)
    assert created == {"handle": 1}
    assert t["expr_eval"].invoke(handle=1) == 42.0
    assert t["expr_free"].invoke(handle=1) == {"freed": 1, "live_handles": 0}
    with pytest.raises(KeyError):
        t["expr_eval"].invoke(handle=1)          # use-after-free rejected

def test_handle_schema_shapes(lib):
    spec = spec_from_signatures("expr", SIGNATURES)
    apply_handle_facts(spec, analyze_handles(C_SRC)[0])
    t = {x.name: x for x in build_tools(lib, spec, HandleTable())}
    assert [n for n, _ in t["expr_create"].params] == ["x"]        # no handle in
    assert [n for n, _ in t["expr_eval"].params] == ["handle"]     # handle only
    assert [n for n, _ in t["expr_free"].params] == ["handle"]
