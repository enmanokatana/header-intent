"""
Libclang L2 engine tests. Auto-skip if libclang isn't installed. These read
real .c files directly (no cpp / fake headers) and check that the libclang
engine produces the SAME handle facts and def-use intents as pycparser.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("clang.cindex")   # skip whole module if libclang missing

from src.layers.libclang_engine import LibclangEngine, handle_records_files
from src.layers.l2_handles import analyze_handles, classify_records
from src.layers.l2_static import l2_intents
from src.spec.vocab import Intent

# a self-contained handle library with real #include (libclang resolves it)
HANDLE_C = r"""
#include <stdlib.h>
typedef struct expr { double v; } expr;
expr *expr_create(double x) { expr *e = malloc(sizeof(expr)); e->v = x; return e; }
double expr_eval(expr *e) { return e->v; }
void expr_free(expr *e) { free(e); }
"""

# def-use cases with a real include
DEFUSE_C = r"""
#include <stddef.h>
void divmod(int a, int b, int *q, int *r) { *q = a / b; *r = a % b; }
void scale_inplace(double *v, double k) { *v = *v * k; }
int reads_only(int *p) { return *p + 1; }
"""


@pytest.fixture
def handle_c(tmp_path):
    p = tmp_path / "handle.c"
    p.write_text(HANDLE_C)
    return str(p)


@pytest.fixture
def defuse_c(tmp_path):
    p = tmp_path / "defuse.c"
    p.write_text(DEFUSE_C)
    return str(p)


# --- handle analysis via libclang (no cpp!) -------------------------------
def test_libclang_handle_records(handle_c):
    recs = LibclangEngine().handle_records(handle_c)
    assert recs["expr_create"].return_pointee == "expr"
    assert recs["expr_eval"].struct_ptr_params == {"e": "expr"}
    assert "e" in recs["expr_free"].freed          # detected free(e)

def test_libclang_handle_lifecycle(handle_c):
    facts, htypes = analyze_handles(engine=LibclangEngine(), path=handle_c)
    assert htypes == {"expr"}
    assert facts["expr_create"].role == "creates"
    assert facts["expr_eval"].role == "uses"
    assert facts["expr_free"].role == "destroys"

def test_libclang_only_defined_functions(handle_c):
    # malloc/free come from <stdlib.h> -- must NOT appear as analyzed functions
    recs = LibclangEngine().handle_records(handle_c)
    assert set(recs) == {"expr_create", "expr_eval", "expr_free"}


# --- def-use via libclang -------------------------------------------------
def test_libclang_defuse_intents(defuse_c):
    intents = l2_intents(defuse_c, engine=LibclangEngine())
    assert intents["divmod"]["q"].value is Intent.OUT
    assert intents["divmod"]["r"].value is Intent.OUT
    assert intents["scale_inplace"]["v"].value is Intent.INOUT
    assert intents["reads_only"]["p"].value is Intent.IN


# --- parity: libclang == pycparser on the same logic ----------------------
def test_libclang_matches_pycparser_classification(handle_c):
    lc_facts, lc_ht = analyze_handles(engine=LibclangEngine(), path=handle_c)
    # pycparser needs preprocessed source; compare classification via records
    recs = LibclangEngine().handle_records(handle_c)
    py_facts, py_ht = classify_records(recs)
    assert {k: v.role for k, v in lc_facts.items()} == {k: v.role for k, v in py_facts.items()}
    assert lc_ht == py_ht
