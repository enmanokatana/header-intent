"""
Phase 3 slice 1: ownership inference (creates vs BORROWED) -- the gap cJSON forced.

cJSON_GetObjectItem returns a pointer INTO the tree you passed in (owned by the
parent). Freeing it double-frees. These tests use cJSON-shaped source and a real
compiled .so to prove the double-free is prevented.
"""
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.layers.l1_signature import spec_from_signatures
from src.layers.l2_handles import analyze_handles, apply_handle_facts
from src.layers.l2_ownership import (analyze_ownership, apply_ownership_facts,
                                         OWNED, BORROWED)
from src.server.build import build_tools
from src.server.handles import HandleTable, OwnershipError

# cJSON-shaped patterns (parse chain, borrowed getter, escape-into-parent)
SRC = r"""
typedef unsigned long size_t;
void *malloc(size_t); void free(void *);
typedef struct hooks { void *(*allocate)(size_t); void (*deallocate)(void *); } hooks;
hooks global_hooks;
typedef struct node { int v; struct node *child; struct node *next; } node;
int add_item_to_object(node *object, node *item);
node *new_item(void) { node *n = global_hooks.allocate(sizeof(node)); return n; }
node *tree_parse_opts(int v) { node *root = new_item(); return root; }
node *tree_parse(int v) { return tree_parse_opts(v); }
node *get_child(node *object) { node *cur = object->child; while (cur != 0) { cur = cur->next; } return cur; }
node *tree_get_child(node *object) { return get_child(object); }
node *tree_add_child(node *object, int v) {
    node *kid = new_item();
    if (add_item_to_object(object, kid)) { return kid; }
    return 0;
}
node *tree_dup(node *item) { node *fresh = new_item(); return fresh; }
int tree_value(node *item) { return item->v; }
void tree_delete(node *item) { global_hooks.deallocate(item); }
"""

# real compiled library (the .so we actually call)
REAL = r"""
#include <stdlib.h>
typedef struct node { int v; struct node *child; struct node *next; } node;
static node *new_item(void) { node *n = malloc(sizeof(node)); n->child=0; n->next=0; n->v=0; return n; }
node *tree_parse(int v) { node *r = new_item(); r->v=v; r->child = new_item(); r->child->v = v*2; return r; }
node *tree_get_child(node *object) { return object->child; }
int tree_value(node *item) { return item->v; }
void tree_delete(node *item) { if (item->child) free(item->child); free(item); }
"""

SIG = {
    "tree_parse": {"argnames": ["v"], "argtypes": [ctypes.c_int],
                   "restype": ctypes.c_void_p, "pointers": {}},
    "tree_get_child": {"argnames": ["object"], "argtypes": [ctypes.c_void_p],
                       "restype": ctypes.c_void_p, "pointers": {}},
    "tree_value": {"argnames": ["item"], "argtypes": [ctypes.c_void_p],
                   "restype": ctypes.c_int, "pointers": {}},
    "tree_delete": {"argnames": ["item"], "argtypes": [ctypes.c_void_p],
                    "restype": None, "pointers": {}},
}


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    d = tmp_path_factory.mktemp("own")
    src, so = d / "r.c", d / "l.so"
    src.write_text(REAL)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(so), str(src)], check=True)
    return ctypes.CDLL(str(so))


# --- ownership analysis ---------------------------------------------------
def test_allocation_is_owned():
    f = analyze_ownership(SRC)
    assert f["new_item"].owner == OWNED
    assert f["tree_dup"].owner == OWNED

def test_call_chain_propagates_ownership():
    f = analyze_ownership(SRC)
    assert f["tree_parse_opts"].owner == OWNED
    assert f["tree_parse"].owner == OWNED          # via tree_parse_opts -> new_item

def test_pointer_from_parameter_is_borrowed():
    f = analyze_ownership(SRC)
    assert f["get_child"].owner == BORROWED        # cur = object->child
    assert f["tree_get_child"].owner == BORROWED   # propagates

def test_traversal_keeps_the_borrow():
    # cur = cur->next inside a loop must NOT clobber the param taint
    f = analyze_ownership(SRC)
    assert f["get_child"].confidence >= 0.9        # resolved by rule, not fail-safe

def test_escape_into_parent_is_borrowed():
    # allocates, then hands the node to the parent object -> parent owns it
    f = analyze_ownership(SRC)
    assert f["tree_add_child"].owner == BORROWED
    assert "stored into a parameter" in f["tree_add_child"].reason


# --- deallocator detection (cJSON frees via a hooks function pointer) -----
def test_hooks_deallocator_detected_as_destroys():
    facts, _ = analyze_handles(SRC)
    assert facts["tree_delete"].role == "destroys"   # global_hooks.deallocate(item)


# --- spec + runtime enforcement ------------------------------------------
def _spec():
    s = spec_from_signatures("own", SIG)
    apply_handle_facts(s, analyze_handles(SRC)[0])
    apply_ownership_facts(s, analyze_ownership(SRC))
    return s

def test_creates_demoted_to_borrows_in_spec():
    s = _spec()
    assert s.functions["tree_parse"].lifecycle == "creates"
    assert s.functions["tree_parse"].owner == "caller"
    assert s.functions["tree_get_child"].lifecycle == "borrows"
    assert s.functions["tree_get_child"].owner == "library"

def test_borrowed_handle_can_be_read(lib):
    s = _spec()
    H = HandleTable()
    t = {x.name: x for x in build_tools(lib, s, H)}
    root = t["tree_parse"].invoke(v=21)
    child = t["tree_get_child"].invoke(handle=root["handle"])
    assert child["borrowed"] is True
    assert t["tree_value"].invoke(handle=child["handle"]) == 42   # reads fine

def test_freeing_a_borrowed_handle_is_refused(lib):
    s = _spec()
    H = HandleTable()
    t = {x.name: x for x in build_tools(lib, s, H)}
    root = t["tree_parse"].invoke(v=21)
    child = t["tree_get_child"].invoke(handle=root["handle"])
    with pytest.raises(OwnershipError):
        t["tree_delete"].invoke(handle=child["handle"])
    # and the owner still frees cleanly -> no double free, process survives
    assert t["tree_delete"].invoke(handle=root["handle"])["freed"] == root["handle"]

def test_guard_runs_before_the_c_call(lib):
    # the check must precede the C free; otherwise the memory is already gone
    s = _spec()
    H = HandleTable()
    t = {x.name: x for x in build_tools(lib, s, H)}
    root = t["tree_parse"].invoke(v=21)
    child = t["tree_get_child"].invoke(handle=root["handle"])
    with pytest.raises(OwnershipError):
        t["tree_delete"].invoke(handle=child["handle"])
    assert t["tree_value"].invoke(handle=child["handle"]) == 42   # still alive!
