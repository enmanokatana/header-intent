"""Unified pipeline: L1+L2+fuse+verify in one call, with buildability report."""
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline import infer_spec
from src.server.build import build_tools
from src.server.handles import HandleTable

# fake-decl source (parses without cpp) covering all idioms
PP = r"""
typedef unsigned long size_t;
void *malloc(size_t); void free(void *);
typedef struct expr { double v; } expr;
int imax(int a, int b) { return a > b ? a : b; }
void divmod(int a, int b, int *q, int *r) { *q = a / b; *r = a % b; }
void scale_inplace(double *v, double k) { *v = *v * k; }
int str_len(const char *s) { int n=0; while(s[n]) n++; return n; }
int sum(const int *arr, int n) { int s=0; for(int i=0;i<n;i++) s+=arr[i]; return s; }
expr *expr_create(double x) { expr *e = malloc(sizeof(expr)); e->v = x; return e; }
double expr_eval(expr *e) { return e->v; }
void expr_free(expr *e) { free(e); }
"""
REAL = "#include <stdlib.h>\n" + "\n".join(
    l for l in PP.splitlines() if "malloc(size_t)" not in l and "typedef unsigned long" not in l)

SIG = {
 "imax": {"argnames": ["a", "b"], "argtypes": [ctypes.c_int, ctypes.c_int], "restype": ctypes.c_int, "pointers": {}},
 "divmod": {"argnames": ["a", "b", "q", "r"], "argtypes": [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)], "restype": None, "pointers": {"q": "out", "r": "out"}},
 "scale_inplace": {"argnames": ["v", "k"], "argtypes": [ctypes.POINTER(ctypes.c_double), ctypes.c_double], "restype": None, "pointers": {"v": "out"}},
 "str_len": {"argnames": ["s"], "argtypes": [ctypes.c_char_p], "restype": ctypes.c_int, "pointers": {}},
 "sum": {"argnames": ["arr", "n"], "argtypes": [ctypes.POINTER(ctypes.c_int), ctypes.c_int], "restype": ctypes.c_int, "pointers": {"arr": "out"}},
 "expr_create": {"argnames": ["x"], "argtypes": [ctypes.c_double], "restype": ctypes.c_void_p, "pointers": {}},
 "expr_eval": {"argnames": ["e"], "argtypes": [ctypes.c_void_p], "restype": ctypes.c_double, "pointers": {}},
 "expr_free": {"argnames": ["e"], "argtypes": [ctypes.c_void_p], "restype": None, "pointers": {}},
}


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    d = tmp_path_factory.mktemp("pl")
    src, so = d / "pp.c", d / "l.so"
    src.write_text(PP)
    (d / "real.c").write_text(REAL)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(so), str(d / "real.c")], check=True)
    return str(src), str(so)


def test_pipeline_all_idioms_buildable(env):
    src, so = env
    spec, report = infer_spec("pl", signatures=SIG, source=src, so=so,
                              engine="pycparser", preprocessed_source=PP)
    assert set(report.buildable) == set(SIG)      # all 8 build
    assert report.refused == []

def test_pipeline_derives_handles_and_arrays(env):
    src, so = env
    spec, report = infer_spec("pl", signatures=SIG, source=src, so=so,
                              engine="pycparser", preprocessed_source=PP)
    assert any("expr_create: creates" in h for h in report.handles)
    assert any("expr_free: destroys" in h for h in report.handles)
    assert any("sum: arr[n]" in a for a in report.arrays)

def test_pipeline_flags_conflicts(env):
    src, so = env
    spec, report = infer_spec("pl", signatures=SIG, source=src, so=so,
                              engine="pycparser", preprocessed_source=PP)
    pairs = {(c.function, c.param, c.l2) for c in report.conflicts}
    assert ("scale_inplace", "v", "inout") in pairs
    assert ("sum", "arr", "in") in pairs

def test_pipeline_tools_execute(env):
    src, so = env
    spec, _ = infer_spec("pl", signatures=SIG, source=src, so=so,
                         engine="pycparser", preprocessed_source=PP)
    lib = ctypes.CDLL(so)
    t = {x.name: x for x in build_tools(lib, spec, HandleTable())}
    assert t["scale_inplace"].invoke(v=3.0, k=4.0) == {"v": 12.0}
    assert t["sum"].invoke(arr=[3, 1, 4, 1, 5, 9]) == 23
    c = t["expr_create"].invoke(x=8.0)
    assert t["expr_eval"].invoke(handle=c["handle"]) == 8.0

def test_pipeline_degrades_without_source():
    # no source -> L1 + verify only, arrays/handles skipped, scalars still fine
    spec, report = infer_spec("pl", signatures={
        "imax": SIG["imax"], "str_len": SIG["str_len"]})
    assert "imax" in {f for f in spec.functions}
    assert any("no source" in s for s in report.skipped)
