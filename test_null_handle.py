"""
Reusing a C library's own test suite as a correctness oracle (paper section 5)
requires the binding to express inputs those tests actually use. cJSON's
cjson_functions_shouldnt_crash_with_null_pointers passes a literal C NULL where
a cJSON* handle is expected, to verify defensive NULL-handling:

    TEST_ASSERT_NULL(cJSON_GetObjectItem(NULL, "test"));
    TEST_ASSERT_NULL(cJSON_GetArrayItem(NULL, 0));
    TEST_ASSERT_FALSE(cJSON_HasObjectItem(NULL, "test"));

The handle table originally rejected a None handle with
"unknown or freed handle: None" before ever calling C, so none of these tests
could run. The fix forwards a None handle as a C NULL pointer.

The safety boundary this must NOT cross: an ARBITRARY UNREGISTERED INTEGER is
still rejected. Forwarding None (the one universal "no object" sentinel) is
safe and necessary; forwarding a fabricated integer would let a caller conjure
a pointer, defeating the handle table entirely.
"""
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ferrule.spec.vocab import Role, Intent
from ferrule.spec.schema import FunctionSpec, ParamSpec, Evidenced, LibrarySpec
from ferrule.core.invoker import build_capabilities
from ferrule.core.handles import HandleTable

REAL_C = r"""
#include <stdlib.h>
typedef struct cJSON { struct cJSON *next; int type; char *valuestring; } cJSON;
cJSON *cJSON_GetObjectItem(const cJSON *object, const char *string) {
    if (object == NULL || string == NULL) return NULL;
    return NULL;
}
int cJSON_HasObjectItem(const cJSON *object, const char *string) {
    if (object == NULL || string == NULL) return 0;
    return 0;
}
cJSON *cJSON_CreateObject(void) { cJSON *o = calloc(1,sizeof(cJSON)); return o; }
void cJSON_Delete(cJSON *o) { free(o); }
"""


def _P(name, role, ctype):
    return ParamSpec(name, role, Evidenced(Intent.IN, ["type"], 1.0, verified=True), ctype)


def _build(so):
    getobj = FunctionSpec("cJSON_GetObjectItem",
                          [_P("object", Role.HANDLE, "c_void_p"), _P("string", Role.STRING, "c_char_p")],
                          restype=None, lifecycle="borrows", handle_type="cJSON")
    hasobj = FunctionSpec("cJSON_HasObjectItem",
                          [_P("object", Role.HANDLE, "c_void_p"), _P("string", Role.STRING, "c_char_p")],
                          restype="c_int", lifecycle="uses", handle_type="cJSON")
    create = FunctionSpec("cJSON_CreateObject", [], restype=None,
                          lifecycle="creates", handle_type="cJSON", owner="caller")
    delete = FunctionSpec("cJSON_Delete", [_P("object", Role.HANDLE, "c_void_p")],
                          restype=None, lifecycle="destroys", handle_type="cJSON")
    spec = LibrarySpec(library="cjson",
                       functions={f.name: f for f in [getobj, hasobj, create, delete]})
    lib = ctypes.CDLL(so)
    caps, _ = build_capabilities(lib, spec, HandleTable())
    return {c.name: c for c in caps}


@pytest.fixture(scope="module")
def caps(tmp_path_factory):
    d = tmp_path_factory.mktemp("null_handle")
    src, lib = d / "r.c", d / "l.so"
    src.write_text(REAL_C)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(lib), str(src)], check=True)
    return _build(str(lib))


def test_none_handle_forwards_as_c_null_on_borrows(caps):
    """cJSON_GetObjectItem(NULL, "test") must reach C and come back NULL."""
    r = caps["cJSON_GetObjectItem"].invoke(handle=None, string="test")
    assert r == {"handle": None}

def test_none_handle_forwards_as_c_null_on_uses(caps):
    """cJSON_HasObjectItem(NULL, "test") must reach C and come back false (0)."""
    r = caps["cJSON_HasObjectItem"].invoke(handle=None, string="test")
    assert r == 0

def test_none_handle_on_destructor_is_a_noop_not_an_error(caps):
    """cJSON_Delete(NULL) is a documented no-op; a None handle must not raise
    an ownership error or a missing-handle error."""
    r = caps["cJSON_Delete"].invoke(handle=None)
    # forwarded as NULL; freed count is 0 since nothing real was freed
    assert r.get("freed") in (0, None)

def test_arbitrary_unregistered_integer_still_rejected(caps):
    """THE safety boundary: None is forwarded, but a fabricated integer handle
    that was never issued by the table must still be rejected -- otherwise the
    handle table provides no protection at all."""
    with pytest.raises(KeyError):
        caps["cJSON_GetObjectItem"].invoke(handle=999999, string="test")
