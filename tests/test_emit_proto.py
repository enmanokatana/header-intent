"""
gRPC / protobuf emitter -- the SECOND protocol, which is what tests the claim that
the capability spec is a real target-agnostic IR.

Key assertions:
  * LENGTH_OF collapses into `repeated` (the length param disappears entirely)
  * out-params become response message fields
  * handle capabilities require a session; pure functions do not
  * OWNERSHIP IS STILL ENFORCED -- over gRPC, by the core, not by this emitter
"""
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.layers.l1_signature import spec_from_signatures
from src.layers.l2_static import l2_intents
from src.layers.l2_arrays import analyze_arrays, apply_array_facts
from src.layers.l2_handles import analyze_handles, apply_handle_facts
from src.layers.l2_ownership import analyze_ownership, apply_ownership_facts
from src.fuse.fusion import fuse_l2_into_spec
from src.core.invoker import build_capabilities
from src.core.handles import HandleTable
from src.emit.proto import (generate_proto, make_servicer, pascal,
                                needs_session, proto_type)

REAL = r"""
#include <stdlib.h>
typedef struct node { int v; struct node *child; } node;
static node *mk(void) { node *n = malloc(sizeof(node)); n->child=0; n->v=0; return n; }
int imax(int a, int b) { return a > b ? a : b; }
void divmod_(int a, int b, int *q, int *r) { *q = a/b; *r = a%b; }
int sum(const int *arr, int n) { int s=0; for(int i=0;i<n;i++) s+=arr[i]; return s; }
node *tree_parse(int v) { node *r = mk(); r->v=v; r->child=mk(); r->child->v=v*2; return r; }
node *tree_child(node *o) { return o->child; }
int tree_value(node *o) { return o->v; }
void tree_delete(node *o) { if (o->child) free(o->child); free(o); }
"""

PP = r"""
typedef unsigned long size_t;
void *malloc(size_t); void free(void *);
typedef struct node { int v; struct node *child; } node;
node *mk(void) { node *n = malloc(sizeof(node)); return n; }
int imax(int a, int b) { return a > b ? a : b; }
void divmod_(int a, int b, int *q, int *r) { *q = a/b; *r = a%b; }
int sum(const int *arr, int n) { int s=0; for(int i=0;i<n;i++) s+=arr[i]; return s; }
node *tree_parse(int v) { node *root = mk(); return root; }
node *tree_child(node *o) { node *c = o->child; return c; }
int tree_value(node *o) { return o->v; }
void tree_delete(node *o) { free(o); }
"""

SIG = {
    "imax": {"argnames": ["a", "b"], "argtypes": [ctypes.c_int, ctypes.c_int],
             "restype": ctypes.c_int, "pointers": {}},
    "divmod_": {"argnames": ["a", "b", "q", "r"],
                "argtypes": [ctypes.c_int, ctypes.c_int,
                             ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)],
                "restype": None, "pointers": {"q": "out", "r": "out"}},
    "sum": {"argnames": ["arr", "n"], "argtypes": [ctypes.POINTER(ctypes.c_int), ctypes.c_int],
            "restype": ctypes.c_int, "pointers": {"arr": "out"}},
    "tree_parse": {"argnames": ["v"], "argtypes": [ctypes.c_int],
                   "restype": ctypes.c_void_p, "pointers": {}},
    "tree_child": {"argnames": ["o"], "argtypes": [ctypes.c_void_p],
                   "restype": ctypes.c_void_p, "pointers": {}},
    "tree_value": {"argnames": ["o"], "argtypes": [ctypes.c_void_p],
                   "restype": ctypes.c_int, "pointers": {}},
    "tree_delete": {"argnames": ["o"], "argtypes": [ctypes.c_void_p],
                    "restype": None, "pointers": {}},
}


def make_spec():
    s = spec_from_signatures("tree", SIG)
    fuse_l2_into_spec(s, l2_intents(PP))
    apply_array_facts(s, analyze_arrays(PP))
    apply_handle_facts(s, analyze_handles(PP)[0])
    apply_ownership_facts(s, analyze_ownership(PP))
    return s


@pytest.fixture(scope="module")
def so(tmp_path_factory):
    d = tmp_path_factory.mktemp("proto")
    src, lib = d / "r.c", d / "l.so"
    src.write_text(REAL)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(lib), str(src)], check=True)
    return str(lib)


@pytest.fixture
def proto(so):
    caps, _ = build_capabilities(ctypes.CDLL(so), make_spec(), HandleTable())
    return generate_proto(caps, package="tree", service="Tree")


                                                                              
def test_array_becomes_repeated_and_length_vanishes(proto):
    assert "repeated int64 arr = 1;" in proto.text
    assert "int64 n =" not in proto.text                                             

def test_out_params_become_response_fields(proto):
    assert "message DivmodResponse {" in proto.text
    body = proto.text.split("message DivmodResponse {")[1].split("}")[0]
    assert "int64 q = 1;" in body and "int64 r = 2;" in body

def test_handle_capabilities_need_a_session(proto):
    assert "message TreeParseRequest {\n  string session_id = 1;" in proto.text

def test_pure_functions_are_stateless(proto):
    assert set(proto.stateless) == {"imax", "divmod_", "sum"}

def test_borrowed_is_documented_and_flagged(proto):
    assert "DO NOT free" in proto.text
    assert "bool borrowed = 2;" in proto.text

def test_session_rpcs_present(proto):
    assert "rpc OpenSession" in proto.text and "rpc CloseSession" in proto.text

def test_name_conversion():
    assert pascal("cJSON_GetObjectItem") == "CJSONGetObjectItem"
    assert pascal("tree_parse") == "TreeParse"


                                                                               
def test_stateless_rpcs_need_no_session(so):
    srv = make_servicer(so, make_spec())
    assert srv.Imax({"a": 4, "b": 9}) == {"result": 9}
    assert srv.Sum({"arr": [3, 1, 4, 1, 5]}) == {"result": 14}
    assert srv.Divmod({"a": 17, "b": 5}) == {"q": 3, "r": 2}

def test_session_scoped_handles(so):
    srv = make_servicer(so, make_spec())
    s1 = srv.OpenSession({})["session_id"]
    s2 = srv.OpenSession({})["session_id"]
    r1 = srv.TreeParse({"session_id": s1, "v": 7})
    r2 = srv.TreeParse({"session_id": s2, "v": 9})
                                                                                 
    assert r1["handle"] == 1 and r2["handle"] == 1
    assert srv.TreeValue({"session_id": s1, "handle": 1}) == {"result": 7}
    assert srv.TreeValue({"session_id": s2, "handle": 1}) == {"result": 9}

def test_ownership_enforced_over_grpc(so):
    """The emitter has no ownership logic -- the CORE refuses the borrowed free."""
    srv = make_servicer(so, make_spec())
    sess = srv.OpenSession({})["session_id"]
    root = srv.TreeParse({"session_id": sess, "v": 21})
    kid = srv.TreeChild({"session_id": sess, "handle": root["handle"]})
    assert kid["borrowed"] is True
    with pytest.raises(PermissionError):                                       
        srv.TreeDelete({"session_id": sess, "handle": kid["handle"]})
    assert srv.TreeValue({"session_id": sess, "handle": kid["handle"]}) == {"result": 42}
    assert srv.TreeDelete({"session_id": sess, "handle": root["handle"]})["freed"] == root["handle"]

def test_close_session_reports_live_handles(so):
    srv = make_servicer(so, make_spec())
    sess = srv.OpenSession({})["session_id"]
    srv.TreeParse({"session_id": sess, "v": 1})
    assert srv.CloseSession({"session_id": sess})["released_handles"] >= 1
