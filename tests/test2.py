"""
Ferrule Phase 2 tests: L2 def-use analysis, evidence fusion, and the by_ref /
probe fixes it surfaced. Compiles a small real .so and parses the same source.
"""
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.spec.vocab import Intent, Role
from src.layers.l1_signature import spec_from_signatures
from src.layers.l2_static import l2_intents, PycparserEngine, _intent_of
from src.fuse.fusion import fuse_l2_into_spec, fuse_intent
from src.spec.schema import Evidenced
from src.verify.probes import apply_verification
from src.server.build import build_tools

C_SRC = r"""
int imax(int a, int b) { return a > b ? a : b; }
void divmod(int a, int b, int *q, int *r) { *q = a / b; *r = a % b; }
void scale_inplace(double *v, double k) { *v = *v * k; }
int reads_only(int *p) { return *p + 1; }
void accumulate(int *acc, int x) { *acc = *acc + x; }
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
    "reads_only": {"argnames": ["p"], "argtypes": [ctypes.POINTER(ctypes.c_int)],
                   "restype": ctypes.c_int, "pointers": {"p": "out"}},
    "accumulate": {"argnames": ["acc", "x"],
                   "argtypes": [ctypes.POINTER(ctypes.c_int), ctypes.c_int],
                   "restype": None, "pointers": {"acc": "out"}},
}


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    d = tmp_path_factory.mktemp("p2")
    src, so = d / "l.c", d / "l.so"
    src.write_text(C_SRC)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(so), str(src)], check=True)
    return ctypes.CDLL(str(so))


# --- L2 def-use -----------------------------------------------------------
def test_defuse_classifier_units():
    assert _intent_of(["write"]) is Intent.OUT
    assert _intent_of(["read", "write"]) is Intent.INOUT
    assert _intent_of(["read"]) is Intent.IN
    assert _intent_of([]) is None

def test_l2_derives_intents_from_source():
    l2 = l2_intents(C_SRC)
    assert l2["divmod"]["q"].value is Intent.OUT
    assert l2["scale_inplace"]["v"].value is Intent.INOUT   # read-then-write
    assert l2["reads_only"]["p"].value is Intent.IN         # read-only, despite non-const
    assert l2["accumulate"]["acc"].value is Intent.INOUT    # *acc = *acc + x

def test_l2_confidence_and_sources():
    l2 = l2_intents(C_SRC)
    ev = l2["scale_inplace"]["v"]
    assert ev.sources == ["def_use"] and ev.confidence == 0.95 and not ev.verified


# --- fusion ---------------------------------------------------------------
def test_fusion_agreement_compounds():
    l1 = Evidenced(Intent.OUT, ["const_ness"], 0.9)
    l2 = Evidenced(Intent.OUT, ["def_use"], 0.95)
    fused, conflict = fuse_intent(l1, l2)
    assert fused.value is Intent.OUT and conflict is None
    assert fused.confidence > 0.95 and set(fused.sources) == {"const_ness", "def_use"}

def test_fusion_refinement_out_to_inout():
    fused, conflict = fuse_intent(
        Evidenced(Intent.OUT, ["const_ness"], 0.9),
        Evidenced(Intent.INOUT, ["def_use"], 0.95))
    assert fused.value is Intent.INOUT
    assert conflict.severity == "refinement"

def test_fusion_true_conflict_out_vs_in():
    fused, conflict = fuse_intent(
        Evidenced(Intent.OUT, ["const_ness"], 0.9),
        Evidenced(Intent.IN, ["def_use"], 0.95))
    assert fused.value is Intent.IN
    assert conflict.severity == "conflict"

def test_fusion_respects_manual_override():
    l1 = Evidenced(Intent.INOUT, ["manual"], 1.0, verified=True)
    l2 = Evidenced(Intent.OUT, ["def_use"], 0.95)
    fused, conflict = fuse_intent(l1, l2)
    assert fused.value is Intent.INOUT and conflict is None   # operator wins


# --- end to end (no manual overrides) -------------------------------------
def test_inout_derived_without_override(lib):
    spec = spec_from_signatures("p2", SIGNATURES)            # no overrides!
    fuse_l2_into_spec(spec, l2_intents(C_SRC))
    apply_verification(lib, spec)
    v = next(p for p in spec.functions["scale_inplace"].params if p.name == "v")
    assert v.intent.value is Intent.INOUT and v.intent.verified
    t = {x.name: x for x in build_tools(lib, spec)}
    assert t["scale_inplace"].invoke(v=3.0, k=4.0) == {"v": 12.0}
    assert t["accumulate"].invoke(acc=10, x=5) == {"acc": 15}

def test_readonly_pointer_becomes_visible_input(lib):
    spec = spec_from_signatures("p2", SIGNATURES)
    fuse_l2_into_spec(spec, l2_intents(C_SRC))
    apply_verification(lib, spec)
    p = next(pp for pp in spec.functions["reads_only"].params if pp.name == "p")
    assert p.intent.value is Intent.IN and p.by_ref          # pointer, but input
    t = {x.name: x for x in build_tools(lib, spec)}
    assert [n for n, _ in t["reads_only"].params] == ["p"]   # visible, not hidden
    assert t["reads_only"].invoke(p=41) == 42                # in-by-ref, no segfault

def test_probe_no_false_negative_on_identity(lib):
    # scale_inplace multiplies; a benign k=1 would hide the write. The two-run
    # non-identity probe must still confirm v is written.
    spec = spec_from_signatures("p2", SIGNATURES)
    fuse_l2_into_spec(spec, l2_intents(C_SRC))
    apply_verification(lib, spec)
    v = next(p for p in spec.functions["scale_inplace"].params if p.name == "v")
    assert v.intent.verified and v.intent.confidence >= 0.9