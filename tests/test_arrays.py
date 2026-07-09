"""Phase 2 slice 3: array<->length pairing, applied to spec + generated tools."""
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.spec.vocab import Role
from src.layers.l1_signature import spec_from_signatures
from src.layers.l2_arrays import analyze_arrays, apply_array_facts
from src.server.build import build_tools

C_SRC = r"""
int sum(const int *arr, int n) { int s=0; for(int i=0;i<n;i++) s+=arr[i]; return s; }
double dot(const double *a, const double *b, int len) { double s=0; for(int i=0;i<len;i++) s+=a[i]*b[i]; return s; }
int maxv(const int *arr, int n) { int m=arr[0]; for(int i=1;i<n;i++) if(arr[i]>m) m=arr[i]; return m; }
int first(const int *p) { return p[0]; }
"""

SIG = {
    "sum": {"argnames": ["arr", "n"],
            "argtypes": [ctypes.POINTER(ctypes.c_int), ctypes.c_int],
            "restype": ctypes.c_int, "pointers": {"arr": "out"}},
    "dot": {"argnames": ["a", "b", "len"],
            "argtypes": [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int],
            "restype": ctypes.c_double, "pointers": {"a": "out", "b": "out"}},
    "maxv": {"argnames": ["arr", "n"],
             "argtypes": [ctypes.POINTER(ctypes.c_int), ctypes.c_int],
             "restype": ctypes.c_int, "pointers": {"arr": "out"}},
}


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    d = tmp_path_factory.mktemp("p2a")
    src, so = d / "l.c", d / "l.so"
    src.write_text(C_SRC)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(so), str(src)], check=True)
    return ctypes.CDLL(str(so))


def test_loop_bound_pairs_array_and_length():
    a = analyze_arrays(C_SRC)
    assert a["sum"][0].array_param == "arr" and a["sum"][0].length_param == "n"
    assert a["sum"][0].source == "loop_bound"

def test_shared_length_across_two_arrays():
    a = analyze_arrays(C_SRC)
    dot = {f.array_param: f.length_param for f in a["dot"]}
    assert dot == {"a": "len", "b": "len"}

def test_no_length_no_pairing():
    a = analyze_arrays(C_SRC)
    assert "first" not in a          # p[0] indexed by a constant, no length param

def test_roles_applied():
    spec = spec_from_signatures("t", SIG)
    apply_array_facts(spec, analyze_arrays(C_SRC))
    p = {x.name: x for x in spec.functions["sum"].params}
    assert p["arr"].role is Role.ARRAY and p["arr"].dimension == "n"
    assert p["n"].role is Role.LENGTH_OF

def test_generated_array_tools(lib):
    spec = spec_from_signatures("t", SIG)
    apply_array_facts(spec, analyze_arrays(C_SRC))
    t = {x.name: x for x in build_tools(lib, spec)}
    assert t["sum"].invoke(arr=[3, 1, 4, 1, 5, 9]) == 23
    assert t["maxv"].invoke(arr=[3, 1, 4, 1, 5, 9]) == 9
    assert t["dot"].invoke(a=[1.0, 2.0, 3.0], b=[4.0, 5.0, 6.0]) == 32.0

def test_length_hidden_from_schema(lib):
    spec = spec_from_signatures("t", SIG)
    apply_array_facts(spec, analyze_arrays(C_SRC))
    t = {x.name: x for x in build_tools(lib, spec)}
    assert [n for n, _ in t["sum"].params] == ["arr"]        # n hidden
    assert [n for n, _ in t["dot"].params] == ["a", "b"]     # len hidden