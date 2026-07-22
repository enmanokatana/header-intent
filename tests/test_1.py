"""
what we are testing: L1 spec generation, YAML
round-trip, behavioral verification, spec-driven tool calls, and the fail-safe
guard for low-confidence / opaque pointers.
"""
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.spec.vocab import Intent, Role
from src.spec.schema import Evidenced, ParamSpec, FunctionSpec, LibrarySpec
from src.spec.io import dumps_yaml, loads_yaml
from src.layers.l1_signature import spec_from_signatures
from src.verify.probes import apply_verification
from src.server.build import build_tools, build_tool, SpecViolation

C_SRC = """
int imax(int a, int b) { return a > b ? a : b; }
void divmod(int a, int b, int *q, int *r) { *q = a / b; *r = a % b; }
void scale_inplace(double *v, double k) { *v = *v * k; }
int str_len(const char *s) { int n=0; while (s[n]) n++; return n; }
int noop_reads(const int *p) { return *p; }   /* reads only: NOT an out-param */
"""

SIGNATURES = {
    "imax": {"argnames": ["a", "b"], "argtypes": [ctypes.c_int, ctypes.c_int],
             "restype": ctypes.c_int, "pointers": {}},
    "divmod": {"argnames": ["a", "b", "q", "r"],
               "argtypes": [ctypes.c_int, ctypes.c_int,
                            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)],
               "restype": None, "pointers": {"q": "out", "r": "out"}},
    "scale_inplace": {"argnames": ["v", "k"],
                      "argtypes": [ctypes.POINTER(ctypes.c_double), ctypes.c_double],
                      "restype": None, "pointers": {"v": "out"}},
    "str_len": {"argnames": ["s"], "argtypes": [ctypes.c_char_p],
                "restype": ctypes.c_int, "pointers": {}},
}
OVERRIDES = {"scale_inplace": {"v": "inout"}}


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    d = tmp_path_factory.mktemp("flib")
    src, so = d / "lib.c", d / "libtest.so"
    src.write_text(C_SRC)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(so), str(src)], check=True)
    return ctypes.CDLL(str(so))


@pytest.fixture
def spec():
    return spec_from_signatures("testlib", SIGNATURES, OVERRIDES)


def _param(spec, fn, name):
    return next(p for p in spec.functions[fn].params if p.name == name)

def test_scalar_in_is_verified_by_type(spec):
    p = _param(spec, "imax", "a")
    assert p.role is Role.SCALAR and p.intent.value is Intent.IN
    assert p.intent.verified and p.intent.confidence == 1.0

def test_const_pointer_out_inferred_unverified(spec):
    p = _param(spec, "divmod", "q")
    assert p.intent.value is Intent.OUT
    assert p.intent.sources == ["const_ness"]
    assert not p.intent.verified          # not trusted until a probe confirms
    assert p.intent.confidence == 0.9

def test_manual_override_makes_inout_verified(spec):
    p = _param(spec, "scale_inplace", "v")
    assert p.intent.value is Intent.INOUT
    assert p.intent.sources == ["manual"] and p.intent.verified

def test_string_param(spec):
    p = _param(spec, "str_len", "s")
    assert p.role is Role.STRING and p.intent.value is Intent.IN

def test_void_restype_none(spec):
    assert spec.functions["divmod"].restype is None
    assert spec.functions["imax"].restype == "c_int"


def test_yaml_round_trip_stable(spec):
    once = dumps_yaml(spec)
    assert dumps_yaml(loads_yaml(once)) == once

def test_yaml_preserves_evidence(spec):
    back = loads_yaml(dumps_yaml(spec))
    p = _param(back, "divmod", "q")
    assert p.intent.value is Intent.OUT and p.intent.confidence == 0.9


def test_probe_confirms_real_out_params(lib, spec):
    apply_verification(lib, spec)
    q = _param(spec, "divmod", "q")
    assert q.intent.verified
    assert "behavioral_probe" in q.intent.sources

def test_probe_downgrades_a_false_out(lib):
    # claim noop_reads' p is 'out', but the function only READS it -> must downgrade
    sig = {"noop_reads": {"argnames": ["p"], "argtypes": [ctypes.POINTER(ctypes.c_int)],
                          "restype": ctypes.c_int, "pointers": {"p": "out"}}}
    s = spec_from_signatures("t", sig)
    before = _param(s, "noop_reads", "p").intent.confidence
    apply_verification(lib, s)
    p = _param(s, "noop_reads", "p")
    assert not p.intent.verified
    assert p.intent.confidence < before   # halved because no write observed


def test_tools_call_real_library(lib, spec):
    apply_verification(lib, spec)
    t = {x.name: x for x in build_tools(lib, spec)}
    assert t["imax"].invoke(a=4, b=9) == 9
    assert t["divmod"].invoke(a=17, b=5) == {"q": 3, "r": 2}
    assert t["scale_inplace"].invoke(v=3.0, k=4.0) == {"v": 12.0}
    assert t["str_len"].invoke(s="hello") == 5

def test_out_params_hidden_inout_visible(lib, spec):
    apply_verification(lib, spec)
    t = {x.name: x for x in build_tools(lib, spec)}
    assert [n for n, _ in t["divmod"].params] == ["a", "b"]          # q, r hidden
    assert [n for n, _ in t["scale_inplace"].params] == ["v", "k"]   # v visible


def test_opaque_pointer_refused(lib):
    sig = {"weird": {"argnames": ["p"], "argtypes": [ctypes.POINTER(ctypes.c_int)],
                     "restype": None, "pointers": {}}}   # pointer, unclassified
    s = spec_from_signatures("t", sig)
    assert s.functions["weird"].params[0].role is Role.OPAQUE
    with pytest.raises(SpecViolation):
        build_tool(lib, s.functions["weird"])

def test_low_confidence_unverified_refused(lib):
    fn = FunctionSpec("x", [ParamSpec("p", Role.SCALAR,
                                      Evidenced(Intent.OUT, ["guess"], 0.3, verified=False),
                                      "c_int")], restype=None)
    with pytest.raises(SpecViolation):
        build_tool(lib, fn)