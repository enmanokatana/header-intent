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
from src.core.invoker import build_capabilities, HANDLE, ARRAY
from src.core.handles import HandleTable, OwnershipError
from src.core.policy import SpecViolation
from src.emit.mcp import mcp_return_type
from src.emit.python import bind_module, generate_source

REAL = r"""
#include <stdlib.h>
typedef struct node { int v; struct node *child; } node;
static node *mk(void) { node *n = malloc(sizeof(node)); n->child=0; n->v=0; return n; }
int imax(int a, int b) { return a > b ? a : b; }
void divmod_(int a, int b, int *q, int *r) { *q = a/b; *r = a%b; }
int str_len(const char *s) { int n=0; while(s[n]) n++; return n; }
int sum(const int *arr, int n) { int s=0; for(int i=0;i<n;i++) s+=arr[i]; return s; }
node *tree_parse(int v) { node *r = mk(); r->v=v; r->child=mk(); r->child->v=v*2; return r; }
node *tree_child(node *o) { return o->child; }
char *tree_render(node *o) { static char b[8]; b[0]='O'; b[1]='K'; b[2]=0; return b; }
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
int str_len(const char *s) { int n=0; while(s[n]) n++; return n; }
int sum(const int *arr, int n) { int s=0; for(int i=0;i<n;i++) s+=arr[i]; return s; }
node *tree_parse(int v) { node *root = mk(); return root; }
node *tree_child(node *o) { node *c = o->child; return c; }
char *tree_render(node *o) { return 0; }
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
    "str_len": {"argnames": ["s"], "argtypes": [ctypes.c_char_p],
                "restype": ctypes.c_int, "pointers": {}},
    "sum": {"argnames": ["arr", "n"], "argtypes": [ctypes.POINTER(ctypes.c_int), ctypes.c_int],
            "restype": ctypes.c_int, "pointers": {"arr": "out"}},
    "tree_parse": {"argnames": ["v"], "argtypes": [ctypes.c_int],
                   "restype": ctypes.c_void_p, "pointers": {}},
    "tree_child": {"argnames": ["o"], "argtypes": [ctypes.c_void_p],
                   "restype": ctypes.c_void_p, "pointers": {}},
    "tree_render": {"argnames": ["o"], "argtypes": [ctypes.c_void_p],
                    "restype": ctypes.c_char_p, "pointers": {}},
    "tree_value": {"argnames": ["o"], "argtypes": [ctypes.c_void_p],
                   "restype": ctypes.c_int, "pointers": {}},
    "tree_delete": {"argnames": ["o"], "argtypes": [ctypes.c_void_p],
                    "restype": None, "pointers": {}},
}


@pytest.fixture(scope="module")
def so(tmp_path_factory):
    d = tmp_path_factory.mktemp("core")
    src, lib = d / "r.c", d / "l.so"
    src.write_text(REAL)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(lib), str(src)], check=True)
    return str(lib)


def make_spec():
    s = spec_from_signatures("core", SIG)
    fuse_l2_into_spec(s, l2_intents(PP))
    apply_array_facts(s, analyze_arrays(PP))
    apply_handle_facts(s, analyze_handles(PP)[0])
    apply_ownership_facts(s, analyze_ownership(PP))
    return s


@pytest.fixture
def caps(so):
    c, _ = build_capabilities(ctypes.CDLL(so), make_spec(), HandleTable())
    return {x.name: x for x in c}


                                                                            
def test_outputs_are_typed(caps):
                                                                                 
    assert caps["tree_render"].outputs[0].py_type is str
    assert caps["tree_value"].outputs[0].py_type is int

def test_out_params_become_named_outputs(caps):
    assert [f.name for f in caps["divmod_"].outputs] == ["q", "r"]
    assert caps["divmod_"].returns_mapping is True

def test_array_length_hidden_from_inputs(caps):
    ins = caps["sum"].inputs
    assert [f.name for f in ins] == ["arr"] and ins[0].kind == ARRAY

def test_handle_fields_marked(caps):
    assert caps["tree_value"].inputs[0].kind == HANDLE

def test_ownership_metadata_on_capability(caps):
    assert caps["tree_parse"].owner == "caller"
    assert caps["tree_child"].owner == "library"


                                                                             
def test_mcp_return_type_from_outputs(caps):
    assert mcp_return_type(caps["tree_render"]) is str                      
    assert mcp_return_type(caps["tree_value"]) is int
    assert mcp_return_type(caps["divmod_"]) is dict


                                                                            
def test_python_emitter_all_idioms(so):
    m = bind_module(so, make_spec(), "demo")
    assert m.imax(a=4, b=9) == 9
    assert m.divmod_(a=17, b=5) == {"q": 3, "r": 2}
    assert m.str_len(s="hello") == 5
    assert m.sum(arr=[3, 1, 4, 1, 5]) == 14
    root = m.tree_parse(v=21)
    assert m.tree_render(handle=root["handle"]) == "OK"

def test_ownership_enforced_in_a_protocol_free_emitter(so):
    """The Python emitter knows nothing about ownership -- the CORE refuses."""
    m = bind_module(so, make_spec(), "demo")
    root = m.tree_parse(v=21)
    kid = m.tree_child(handle=root["handle"])
    assert kid["borrowed"] is True
    with pytest.raises(OwnershipError):
        m.tree_delete(handle=kid["handle"])
    assert m.tree_value(handle=kid["handle"]) == 42                                   
    assert m.tree_delete(handle=root["handle"])["freed"] == root["handle"]


                                                                             
def test_generated_source_is_valid_python(so):
    src = generate_source(make_spec(), so)
    compile(src, "generated.py", "exec")
    assert "def imax(a: int, b: int) -> int:" in src
    assert "def sum(arr: list) -> int:" in src                              
    assert "owner: library" in src                                                  


                                                                              
def test_lifecycle_path_enforces_policy_too():
    """Regression: check_exposable() was only wired into the array/plain builders.
    A handle-lifecycle function (creates/borrows/uses/destroys) with an OPAQUE
    param -- e.g. cJSON_PrintPreallocated's non-const char* write buffer --
    skipped the fail-safe entirely and leaked into generated output (seen live
    as a bogus `int64 buffer` field in a real .proto). The safety point is the
    core; it must not depend on which builder a function happens to route through.
    """
    from src.spec.vocab import Role
    from src.core.invoker import build_capability
    from src.core.policy import SpecViolation

    SRC = """typedef unsigned long size_t;
void *malloc(size_t); void free(void *);
typedef struct node{int v;}node;
node *mk(int v){node*n=malloc(sizeof(node));n->v=v;return n;}
int print_prealloc(node*item,char*buffer,int length){return 1;}
void del(node*n){free(n);}
"""
    RSRC = ("#include <stdlib.h>\ntypedef struct node{int v;}node;\n"
            "node*mk(int v){node*n=malloc(sizeof(node));n->v=v;return n;}\n"
            "int print_prealloc(node*item,char*buffer,int length){return 1;}\n"
            "void del(node*n){free(n);}\n")
    d = Path(__file__).resolve().parent / "_tmp_lifecycle_policy"
    d.mkdir(exist_ok=True)
    (d / "r.c").write_text(RSRC)
    so = d / "l.so"
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(so), str(d / "r.c")], check=True)

    SIG = {
        "mk": {"argnames": ["v"], "argtypes": [ctypes.c_int],
               "restype": ctypes.c_void_p, "pointers": {}},
        "print_prealloc": {"argnames": ["item", "buffer", "length"],
                           "argtypes": [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int],
                           "restype": ctypes.c_int, "pointers": {}},
        "del": {"argnames": ["n"], "argtypes": [ctypes.c_void_p],
               "restype": None, "pointers": {}},
    }
    s = spec_from_signatures("t", SIG)
    apply_handle_facts(s, analyze_handles(SRC)[0])
    apply_ownership_facts(s, analyze_ownership(SRC))
                                                                         
                                                               
    for pr in s.functions["print_prealloc"].params:
        if pr.name == "buffer":
            pr.role = Role.OPAQUE
            pr.intent.confidence = 0.0
            pr.intent.verified = False

    lib = ctypes.CDLL(str(so))
    with pytest.raises(SpecViolation):
        build_capability(lib, s.functions["print_prealloc"], HandleTable())