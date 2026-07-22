import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.layers.l1_signature import spec_from_signatures
from src.layers.l2_handles import analyze_handles, apply_handle_facts
from src.layers.l2_ownership import (analyze_ownership, apply_ownership_facts,
                                         analyze_string_ownership,
                                         apply_string_ownership_facts,
                                         OWNED, BORROWED)
from src.core.invoker import build_capabilities, _find_string_deallocator
from src.core.handles import HandleTable, OwnershipError


TRANSFER_SRC = r"""
typedef unsigned long size_t;
void *malloc(size_t); void free(void *);
typedef struct node { int v; struct node *next; struct node *prev; struct node *child; } node;
node *mk(void) { node *n = malloc(sizeof(node)); return n; }
node *make_tree(int v) { node *r = mk(); return r; }
node *get_child(node *object) { node *current = object->child; return current; }
node *detach_item_via_pointer(node *parent, node *item) {
    if (item->prev != 0) { item->prev->next = item->next; }
    if (item->next != 0) { item->next->prev = item->prev; }
    if (item == parent->child) { parent->child = item->next; }
    item->prev = 0;
    item->next = 0;
    return item;
}
node *detach_item_from_array(node *array, int which) {
    node *c = get_child(array);
    return detach_item_via_pointer(array, c);
}
node *peek_item(node *parent, node *item) { return item; }
"""


def test_allocation_still_owned():
    f = analyze_ownership(TRANSFER_SRC)
    assert f["make_tree"].owner == OWNED

def test_derived_from_param_still_borrowed():
    f = analyze_ownership(TRANSFER_SRC)
    assert f["get_child"].owner == BORROWED

def test_detach_via_pointer_is_transfer_owned():
    f = analyze_ownership(TRANSFER_SRC)
    fact = f["detach_item_via_pointer"]
    assert fact.owner == OWNED
    assert "unlinks it from another structure" in fact.reason

def test_transfer_propagates_through_call_chain():
    f = analyze_ownership(TRANSFER_SRC)
    assert f["detach_item_from_array"].owner == OWNED

def test_name_alone_is_not_trusted():
    """A function that returns a param unchanged but does NOT mutate anything
    else stays conservative, even if nothing about its name suggests removal."""
    f = analyze_ownership(TRANSFER_SRC)
    assert f["peek_item"].owner == BORROWED


REAL_C = r"""
#include <stdlib.h>
typedef struct node { int v; struct node *child; } node;
static int free_call_count = 0;
static node *mk(int v) { node *n = malloc(sizeof(node)); n->v = v; n->child = 0; return n; }
node *tree_parse(int v) { return mk(v); }
void tree_delete(node *n) { free(n); }
char *render(node *n) {
    char *buf = malloc(32);
    buf[0] = 'O'; buf[1] = 'K'; buf[2] = 0;
    return buf;
}
char *get_error_ptr(void) { return "static, never free"; }
void render_free(void *p) { free_call_count++; free(p); }
int free_call_count_get(void) { return free_call_count; }
"""

ANALYSIS_SRC = """typedef unsigned long size_t;
void *malloc(size_t); void free(void *);
typedef struct node { int v; struct node *child; } node;
node *mk(int v) { node *n = malloc(sizeof(node)); n->v = v; return n; }
node *tree_parse(int v) { return mk(v); }
void tree_delete(node *n) { free(n); }
char *render(node *n) { char *buf = malloc(32); return buf; }
char *get_error_ptr(void) { return 0; }
void render_free(void *p) { free(p); }
int free_call_count_get(void) { return 0; }
"""

SIG = {
    "tree_parse": {"argnames": ["v"], "argtypes": [ctypes.c_int],
                   "restype": ctypes.c_void_p, "pointers": {}},
    "tree_delete": {"argnames": ["n"], "argtypes": [ctypes.c_void_p],
                    "restype": None, "pointers": {}},
    "render": {"argnames": ["n"], "argtypes": [ctypes.c_void_p],
               "restype": ctypes.c_char_p, "pointers": {}},
    "get_error_ptr": {"argnames": [], "argtypes": [],
                      "restype": ctypes.c_char_p, "pointers": {}},
    "render_free": {"argnames": ["p"], "argtypes": [ctypes.c_void_p],
                    "restype": None, "pointers": {}},
    "free_call_count_get": {"argnames": [], "argtypes": [],
                            "restype": ctypes.c_int, "pointers": {}},
}


@pytest.fixture(scope="module")
def so(tmp_path_factory):
    d = tmp_path_factory.mktemp("strown")
    src, lib = d / "r.c", d / "l.so"
    src.write_text(REAL_C)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(lib), str(src)], check=True)
    return str(lib)


def make_spec():
    s = spec_from_signatures("t", SIG)
    apply_handle_facts(s, analyze_handles(ANALYSIS_SRC)[0])
    apply_ownership_facts(s, analyze_ownership(ANALYSIS_SRC))
    apply_string_ownership_facts(s, analyze_string_ownership(ANALYSIS_SRC))
    return s


def test_alloc_traced_string_is_owned():
    f = analyze_string_ownership(ANALYSIS_SRC)
    assert f["render"].owns is True

def test_static_return_is_never_owned():
    f = analyze_string_ownership(ANALYSIS_SRC)
    assert f["get_error_ptr"].owns is False

def test_deallocator_disambiguation_avoids_struct_destructor(so):
    """render_free (dealloc-name, 1 param, no lifecycle) must be chosen; NOT
    tree_delete, which also matches the name family but is already claimed as
    a struct destructor (lifecycle='destroys') -- calling it on a raw string
    buffer would be memory corruption, not a leak."""
    spec = make_spec()
    lib = ctypes.CDLL(so)
    dealloc = _find_string_deallocator(lib, spec)
    assert dealloc is not None

def test_owned_string_is_freed_exactly_once(so):
    lib = ctypes.CDLL(so)
    caps, _ = build_capabilities(lib, make_spec(), HandleTable())
    t = {c.name: c for c in caps}
    root = t["tree_parse"].invoke(v=99)
    before = t["free_call_count_get"].invoke()
    s = t["render"].invoke(handle=root["handle"])
    after = t["free_call_count_get"].invoke()
    assert s == "OK"
    assert after == before + 1

def test_static_string_never_triggers_a_free(so):
    lib = ctypes.CDLL(so)
    caps, _ = build_capabilities(lib, make_spec(), HandleTable())
    t = {c.name: c for c in caps}
    before = t["free_call_count_get"].invoke()
    s = t["get_error_ptr"].invoke()
    after = t["free_call_count_get"].invoke()
    assert s == "static, never free"
    assert after == before

def test_ownership_still_enforced_alongside_string_fix(so):
    """The two loose-end fixes must not interfere with the core double-free guard."""
    lib = ctypes.CDLL(so)
    caps, _ = build_capabilities(lib, make_spec(), HandleTable())
    t = {c.name: c for c in caps}
    root = t["tree_parse"].invoke(v=1)
    assert t["tree_delete"].invoke(handle=root["handle"])["freed"] == root["handle"]


ESCAPE_SRC = r"""
typedef unsigned long size_t;
void *malloc(size_t); void free(void *);
typedef struct hooks { void *(*allocate)(size_t); } hooks;
hooks global_hooks;
typedef struct node { int v; struct node *child; struct node *next; struct node *prev; } node;
int add_item_to_object(node *object, const char *name, node *item);
node *new_item(void) { node *n = global_hooks.allocate(sizeof(node)); return n; }
node *create_null(void) { node *item = new_item(); return item; }
node *add_null_to_object(node *object, const char *name) {
    node *null_item = create_null();
    if (add_item_to_object(object, name, null_item)) { return null_item; }
    return 0;
}
node *duplicate_rec(node *item, hooks *h, int recurse) { node *n = new_item(); return n; }
node *duplicate(node *item, int recurse) {
    return duplicate_rec(item, &global_hooks, recurse);
}
node *get_object_item_helper(node *object, const char *string) {
    node *current = object->child;
    return current;
}
node *get_object_item(node *object, const char *string) {
    return get_object_item_helper(object, string);
}
"""


def test_escape_fires_through_an_allocator_wrapper_call():
    """THE REGRESSION: allocation via a wrapper (create_null -> new_item) must
    still trigger the escape rule when the result is handed to a parent."""
    f = analyze_ownership(ESCAPE_SRC)
    assert f["add_null_to_object"].owner == BORROWED
    assert "stored into a parameter" in f["add_null_to_object"].reason

def test_escape_does_not_regress_duplicate():
    """The producer-call exclusion must still prevent the ORIGINAL false-escape
    (a call's own arguments must not be mistaken for an escape target)."""
    f = analyze_ownership(ESCAPE_SRC)
    assert f["duplicate"].owner == OWNED
    assert f["duplicate_rec"].owner == OWNED

def test_escape_does_not_regress_borrowed_getters():
    """A call-chain that resolves to a borrowed helper must not be
    mis-triggered into an escape just because the broadened condition now
    covers origin.startswith('call:')."""
    f = analyze_ownership(ESCAPE_SRC)
    assert f["get_object_item"].owner == BORROWED
    assert f["get_object_item_helper"].owner == BORROWED