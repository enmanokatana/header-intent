"""
Regression test for cascade invalidation.  (fix F21)

Pins the hole the paper's own RQ3 transcript exhibits: a borrowed interior handle
survives the destruction of the owned root that backs it, and the handle table keeps
serving it. The ownership check cannot catch the follow-up use because that use is a
READ, not a free.

Follows the methodology the paper already argues for: compiled against a real object
with `gcc -shared -fPIC`, driven through the real generated binding, not a mock.
"""
import ctypes
import subprocess
import sys
import textwrap

import pytest

from src.core.handles import HandleTable, OwnershipError, StaleHandleError

C_SRC = r"""
#include <stdlib.h>
#include <string.h>

typedef struct Node { struct Node *child; int value; } Node;

Node *node_parse(const char *s) {
    Node *root = (Node *)malloc(sizeof(Node));
    root->child = (Node *)malloc(sizeof(Node));
    root->child->child = 0;
    root->child->value = (int)strlen(s);
    root->value = 0;
    return root;                       /* owner: caller */
}

Node *node_get_child(Node *n) { return n->child; }   /* owner: library (borrowed) */

int node_value(Node *n) { return n->value; }

void node_delete(Node *n) {            /* frees the whole tree */
    if (!n) return;
    if (n->child) free(n->child);
    free(n);
}
"""


@pytest.fixture(scope="module")
def so(tmp_path_factory):
    d = tmp_path_factory.mktemp("cascade")
    c, lib = d / "node.c", d / "libnode.so"
    c.write_text(C_SRC)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(lib), str(c)], check=True)
    return str(lib)


# --------------------------------------------------------------------------
# 1. The table-level property, independent of any library.
# --------------------------------------------------------------------------

def test_borrowed_free_still_refused():
    t = HandleTable()
    root = t.put(object(), owned=True)
    child = t.put(object(), owned=False, parent=root)
    with pytest.raises(OwnershipError):
        t.pop(child)


def test_destroying_owner_invalidates_children():
    t = HandleTable()
    root = t.put(object(), owned=True)
    child = t.put(object(), owned=False, parent=root)
    grand = t.put(object(), owned=False, parent=child)

    _, dead = t.pop_cascade(root)
    assert set(dead) == {child, grand}
    with pytest.raises(StaleHandleError) as e:
        t.get(child)
    assert f"owner (handle {root})" in str(e.value)


def test_unrelated_roots_survive():
    t = HandleTable()
    a, b = t.put(object(), owned=True), t.put(object(), owned=True)
    ka = t.put(object(), owned=False, parent=a)
    kb = t.put(object(), owned=False, parent=b)
    t.pop_cascade(a)
    assert not t.is_live(ka)
    assert t.is_live(b) and t.is_live(kb)


def test_stale_handle_is_a_keyerror_for_legacy_callers():
    """StaleHandleError must remain catchable by pre-existing `except KeyError`."""
    t = HandleTable()
    root = t.put(object(), owned=True)
    child = t.put(object(), owned=False, parent=root)
    t.pop_cascade(root)
    with pytest.raises(KeyError):
        t.get(child)


# --------------------------------------------------------------------------
# 2. The end-to-end property, against a real compiled object.
#    Without the fix, the last call reads freed memory: ASAN flags it, and without
#    ASAN it returns garbage or segfaults nondeterministically -- which is exactly
#    why the check must exist rather than relying on a test to notice.
# --------------------------------------------------------------------------

def test_use_after_owner_destroyed_is_refused_not_read(so):
    lib = ctypes.CDLL(so)
    lib.node_parse.argtypes = [ctypes.c_char_p]
    lib.node_parse.restype = ctypes.c_void_p
    lib.node_get_child.argtypes = [ctypes.c_void_p]
    lib.node_get_child.restype = ctypes.c_void_p
    lib.node_value.argtypes = [ctypes.c_void_p]
    lib.node_value.restype = ctypes.c_int
    lib.node_delete.argtypes = [ctypes.c_void_p]
    lib.node_delete.restype = None

    t = HandleTable()
    root = t.put(lib.node_parse(b"hello"), owned=True)
    child = t.put(lib.node_get_child(t.get(root)), owned=False, parent=root)

    lib.node_delete(t.get(root))
    _, dead = t.pop_cascade(root)
    assert child in dead

    # The binding must refuse rather than hand the freed pointer back to C.
    with pytest.raises(StaleHandleError):
        lib.node_value(t.get(child))


def test_ownership_check_still_runs_before_the_c_call(so):
    """Cascade invalidation must not have softened the pre-call check (the defect
    that produced a real `double free detected` abort in an earlier design)."""
    lib = ctypes.CDLL(so)
    lib.node_parse.argtypes = [ctypes.c_char_p]
    lib.node_parse.restype = ctypes.c_void_p
    lib.node_get_child.argtypes = [ctypes.c_void_p]
    lib.node_get_child.restype = ctypes.c_void_p

    t = HandleTable()
    root = t.put(lib.node_parse(b"hi"), owned=True)
    child = t.put(lib.node_get_child(t.get(root)), owned=False, parent=root)

    with pytest.raises(OwnershipError):
        t.pop(child)          # must raise BEFORE anything reaches node_delete
    assert t.is_live(child) and t.is_live(root)


if __name__ == "__main__":
    print(textwrap.dedent("""
        Run with:  pytest -q tests/test_cascade_invalidation.py
        Under ASAN: CFLAGS='-fsanitize=address' and LD_PRELOAD the asan runtime to
        show that the pre-fix behaviour is a genuine heap-use-after-free rather than
        a merely theoretical one -- worth one sentence in the paper.
    """))
    sys.exit(0)
