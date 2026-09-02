"""
L2 out-param-handle CONFIRMATION (layers/l2_out_handles.py) -- promotes an L0
candidate (any T** to a struct) to a real Role.OUT_HANDLE only when the source
proves it receives a fresh allocation. This is what unblocks sqlite3_open,
which is itself a one-line wrapper around an internal (non-header) allocator:

    int sqlite3_open(const char *filename, sqlite3 **ppDb) {
        return openDatabase(filename, ppDb, ...);   // ppDb forwarded, unmodified
    }
    static int openDatabase(..., sqlite3 **ppDb, ...) {
        sqlite3 *db = sqlite3MallocZero(...);
        *ppDb = db;                                  // the REAL allocation
        ...
    }

Confirmation must therefore (a) trace through a local variable, not just a
literal `*out = malloc(...)`, and (b) resolve ONE level of forwarding into an
internal helper the header never declares -- both are exercised here against
a REAL compiled library, end to end through core/invoker.py.
"""
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.layers.l1_signature import spec_from_signatures
from src.layers.l2_handles import analyze_handles, apply_handle_facts
from src.layers.l2_ownership import analyze_ownership, apply_ownership_facts
from src.layers.l2_out_handles import analyze_out_handles, apply_out_handle_facts
from src.core.invoker import build_capabilities
from src.core.handles import HandleTable

REAL_C = r"""
#include <stdlib.h>
typedef struct sqlite3 { int magic; } sqlite3;
static int open_database(const char *filename, sqlite3 **ppDb, int flags) {
    if (filename == 0 || filename[0] == 0) { *ppDb = 0; return 14; }
    sqlite3 *db = malloc(sizeof(sqlite3));
    db->magic = 12345;
    *ppDb = db;
    return 0;
}
int sqlite3_open(const char *filename, sqlite3 **ppDb) {
    return open_database(filename, ppDb, 6);
}
int sqlite3_close(sqlite3 *db) { free(db); return 0; }
int sqlite3_get_magic(sqlite3 *db) { return db->magic; }
sqlite3 *sqlite3_context_db_handle(sqlite3 *ctx) { return ctx; }
"""

ANALYSIS_SRC = """typedef unsigned long size_t;
void *malloc(size_t); void free(void *);
typedef struct sqlite3 { int magic; } sqlite3;
int open_database(const char *filename, sqlite3 **ppDb, int flags) {
    sqlite3 *db = malloc(sizeof(sqlite3));
    *ppDb = db;
    return 0;
}
int sqlite3_open(const char *filename, sqlite3 **ppDb) {
    return open_database(filename, ppDb, 6);
}
int sqlite3_close(sqlite3 *db) { free(db); return 0; }
int sqlite3_get_magic(sqlite3 *db) { return db->magic; }
sqlite3 *sqlite3_context_db_handle(sqlite3 *ctx) { return ctx; }
"""

# realistic: ONLY the header-declared function is a candidate from L0.
# open_database is a static internal helper never declared in a header.
CANDIDATES = {"sqlite3_open": {"ppDb": "sqlite3"}}

SIG = {
    "sqlite3_open": {"argnames": ["filename", "ppDb"],
                     "argtypes": [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)],
                     "restype": ctypes.c_int, "pointers": {}},
    "sqlite3_close": {"argnames": ["db"], "argtypes": [ctypes.c_void_p],
                      "restype": ctypes.c_int, "pointers": {}},
    "sqlite3_get_magic": {"argnames": ["db"], "argtypes": [ctypes.c_void_p],
                          "restype": ctypes.c_int, "pointers": {}},
    "sqlite3_context_db_handle": {"argnames": ["ctx"], "argtypes": [ctypes.c_void_p],
                                  "restype": ctypes.c_void_p, "pointers": {}},
}


def make_spec():
    s = spec_from_signatures("sqlite3", SIG)          # NOTE: no out_handles hint
    apply_handle_facts(s, analyze_handles(ANALYSIS_SRC)[0])
    apply_ownership_facts(s, analyze_ownership(ANALYSIS_SRC))
    apply_out_handle_facts(s, analyze_out_handles(ANALYSIS_SRC, candidates=CANDIDATES))
    return s


@pytest.fixture(scope="module")
def so(tmp_path_factory):
    d = tmp_path_factory.mktemp("sqlopen")
    src, lib = d / "r.c", d / "l.so"
    src.write_text(REAL_C)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(lib), str(src)], check=True)
    return str(lib)


def test_direct_alloc_write_confirms():
    from src.layers.l2_out_handles import analyze_out_handles
    facts = analyze_out_handles(ANALYSIS_SRC, candidates={"open_database": {"ppDb": "sqlite3"}})
    assert facts[("open_database", "ppDb")].confirmed

def test_forward_through_internal_wrapper_confirms():
    """THE key case: sqlite3_open itself never writes ppDb -- it forwards to a
    static helper the header never declares."""
    facts = analyze_out_handles(ANALYSIS_SRC, candidates=CANDIDATES)
    assert facts[("sqlite3_open", "ppDb")].confirmed
    assert "forwards to" in facts[("sqlite3_open", "ppDb")].reason

def test_non_allocating_write_does_not_confirm():
    """Writing NULL (or any non-alloc value) through the out-param must NOT
    confirm -- this is what correctly keeps sqlite3_vtab_in_first/next refused."""
    from src.layers.l2_out_handles import analyze_out_handles
    src = """typedef struct sqlite3_value { int x; } sqlite3_value;
def_placeholder_unused = 0;
"""
    src = """typedef struct T { int x; } T;
void iterate(T *cur, T **out) { *out = 0; }
"""
    facts = analyze_out_handles(src, candidates={"iterate": {"out": "T"}})
    assert not facts[("iterate", "out")].confirmed

def test_spec_promotion():
    fn = make_spec().functions["sqlite3_open"]
    assert fn.handle_out_param == "ppDb"
    assert fn.lifecycle == "creates" and fn.owner == "caller"

def test_end_to_end_real_so(so):
    lib = ctypes.CDLL(so)
    caps, refused = build_capabilities(lib, make_spec(), HandleTable())
    assert not refused, refused
    t = {c.name: c for c in caps}
    r = t["sqlite3_open"].invoke(filename="test.db")
    assert r["status"] == 0 and r["handle"] is not None
    assert t["sqlite3_get_magic"].invoke(handle=r["handle"]) == 12345
    assert t["sqlite3_close"].invoke(handle=r["handle"])["freed"] == r["handle"]

def test_open_failure_path(so):
    lib = ctypes.CDLL(so)
    caps, _ = build_capabilities(lib, make_spec(), HandleTable())
    t = {c.name: c for c in caps}
    r = t["sqlite3_open"].invoke(filename="")
    assert r["handle"] is None
    assert r["status"] == 14


# ---------------------------------------------------------------------------
# multi-branch reassignment (real sqlite3's actual openDatabase shape): `db`
# is assigned an allocation, then RESET TO NULL on one or more error paths,
# before a single final write-through at a goto-style cleanup label. Found by
# running against real sqlite3.c -- openDatabase itself came back unconfirmed
# because "last assignment wins" origin tracking forgot the allocation the
# moment it saw a later `db = 0` reset.
# ---------------------------------------------------------------------------
MULTI_BRANCH_SRC = """typedef unsigned long size_t;
void *sqlite3MallocZero(size_t); void free(void *);
typedef struct sqlite3 { int magic; } sqlite3;
int openDatabase(const char *filename, sqlite3 **ppDb, int flags) {
    sqlite3 *db;
    int rc;
    *ppDb = 0;
    rc = 0;
    db = sqlite3MallocZero(sizeof(sqlite3));
    if (rc != 0) { db = 0; }
    if (filename == 0) { db = 0; }
    *ppDb = db;
    return rc;
}
int sqlite3_open(const char *filename, sqlite3 **ppDb) {
    return openDatabase(filename, ppDb, 6);
}
"""

MULTI_BRANCH_CANDIDATES = {"sqlite3_open": {"ppDb": "sqlite3"}}


def test_alloc_survives_a_later_null_reset_on_an_error_path():
    """THE fix: db=alloc(...) then LATER db=0 (error path) must not erase the
    allocation evidence -- there exists a real path where the out-param
    receives a fresh allocation, which is the property we actually care about."""
    from src.layers.l2_out_handles import analyze_out_handles
    facts = analyze_out_handles(MULTI_BRANCH_SRC, candidates=MULTI_BRANCH_CANDIDATES)
    assert facts[("openDatabase", "ppDb")].confirmed
    assert facts[("sqlite3_open", "ppDb")].confirmed

def test_multiple_null_resets_still_confirm():
    """Two separate error branches both resetting to NULL, as real sqlite3 does,
    must not compound into a false negative."""
    from src.layers.l2_out_handles import _records_from_pycparser
    recs = _records_from_pycparser(MULTI_BRANCH_SRC, MULTI_BRANCH_CANDIDATES)
    assert recs[("openDatabase", "ppDb")].origin == "alloc"

def test_never_allocated_variable_still_refused():
    """The fail-safe must still hold: a variable that is NEVER assigned an
    allocation anywhere must stay unconfirmed, regardless of how many times
    it's reassigned to other non-alloc values."""
    from src.layers.l2_out_handles import analyze_out_handles
    src = """typedef struct T { int x; } T;
    int iterate(T *cur, T **out) {
        T *next;
        next = 0;
        if (cur != 0) { next = 0; }
        *out = next;
        return 0;
    }
    """
    facts = analyze_out_handles(src, candidates={"iterate": {"out": "T"}})
    assert not facts[("iterate", "out")].confirmed


def test_first_write_reset_does_not_shadow_the_real_final_write():
    """Regression pin: a defensive `*out = 0;` BEFORE the real allocation write
    must not shadow the real `*out = alloc_var;` that comes later in the same
    function. This exact ordering (early reset, then the real write at a
    cleanup label) is openDatabase's actual shape and broke confirmation
    entirely after a performance-motivated rewrite accidentally changed the
    out-param write tracking from last-write-wins to first-write-wins."""
    from src.layers.l2_out_handles import analyze_out_handles
    src = """typedef unsigned long size_t;
    void *sqlite3MallocZero(size_t); void free(void *);
    typedef struct sqlite3 { int magic; } sqlite3;
    int openDatabase(const char *filename, sqlite3 **ppDb, int flags) {
        sqlite3 *db;
        int rc;
        *ppDb = 0;
        db = sqlite3MallocZero(sizeof(sqlite3));
        if (filename == 0) { db = 0; }
        if (rc != 0) { db = 0; }
        *ppDb = db;
        return rc;
    }
    """
    facts = analyze_out_handles(src, candidates={"openDatabase": {"ppDb": "sqlite3"}})
    assert facts[("openDatabase", "ppDb")].confirmed, \
        "the real final write must win over the earlier defensive reset"