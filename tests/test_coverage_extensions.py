"""
Regression tests for the coverage extensions (l2_handle_propagation).

These exist to pin the SAFETY side of a coverage change. Every test here asks
the same question in a different shape: did raising coverage grant any
permission the design previously withheld?

The answer must stay no. Coverage is allowed to rise because a contract became
EXPRESSIBLE; it is never allowed to rise because the gate got weaker.
"""
import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.spec.vocab import Role, Intent
from src.spec.schema import Evidenced, ParamSpec, FunctionSpec, LibrarySpec
from src.core.policy import check_exposable, SpecViolation
from src.core.handles import HandleTable, OwnershipError, StaleHandleError
from src.layers.l2_handle_propagation import (
    propagate_handle_types, promote_structural_out_handles,
    detect_caller_allocated_state, apply_caller_state_facts,
)


def _opaque(name, pointee=None, ctype="c_void_p", by_ref=True):
    p = ParamSpec(name, Role.OPAQUE, Evidenced(Intent.IN, [], 0.0, verified=False),
                  ctype, by_ref=by_ref)
    p.pointee = pointee
    return p


def _scalar(name, ctype="c_int"):
    return ParamSpec(name, Role.SCALAR, Evidenced(Intent.IN, ["type"], 1.0, verified=True),
                     ctype)


# ===========================================================================
# Pass 1: handle-type propagation
# ===========================================================================

def test_propagation_marks_known_handle_type():
    """The libpq case: PQconnectdb establishes PGconn as a handle type, so every
    other function taking PGconn* should inherit that instead of being refused."""
    spec = LibrarySpec("libpq", {
        "PQstatus": FunctionSpec("PQstatus", [_opaque("conn", "PGconn")], "c_int"),
        "PQerrorMessage": FunctionSpec("PQerrorMessage", [_opaque("conn", "PGconn")],
                                       "c_char_p"),
    })
    pointees = {"PQstatus": {"conn": "PGconn"}, "PQerrorMessage": {"conn": "PGconn"}}

    notes = propagate_handle_types(spec, {"PGconn"}, pointees)

    assert len(notes) == 2
    for fname in ("PQstatus", "PQerrorMessage"):
        p = spec.functions[fname].params[0]
        assert p.role is Role.HANDLE
        assert p.handle_type == "PGconn"
        check_exposable(spec.functions[fname])          # no longer refused


def test_propagation_ignores_unknown_types():
    """A struct pointer whose type the library never hands out stays refused.
    This is the whole guard: propagation is driven by evidence the library
    manages the type, not by the parameter merely being a struct pointer."""
    spec = LibrarySpec("x", {
        "f": FunctionSpec("f", [_opaque("cfg", "some_config_struct")], "c_int"),
    })
    notes = propagate_handle_types(spec, {"PGconn"}, {"f": {"cfg": "some_config_struct"}})

    assert notes == []
    assert spec.functions["f"].params[0].role is Role.OPAQUE
    with pytest.raises(SpecViolation):
        check_exposable(spec.functions["f"])


def test_propagation_skips_array_shaped_params():
    """png_set_PLTE(png, info, png_color *palette, int num_palette) passes an
    ARRAY, not a handle. Even if png_color is a type the library returns, the
    adjacent count parameter means we must not re-shape it as a handle id."""
    spec = LibrarySpec("libpng", {
        "png_set_PLTE": FunctionSpec("png_set_PLTE", [
            _opaque("png_ptr", "png_struct"),
            _opaque("palette", "png_color"),
            _scalar("num_palette"),
        ], "c_int"),
    })
    pointees = {"png_set_PLTE": {"png_ptr": "png_struct", "palette": "png_color"}}

    propagate_handle_types(spec, {"png_struct", "png_color"}, pointees)

    params = spec.functions["png_set_PLTE"].params
    assert params[0].role is Role.HANDLE, "the real handle should propagate"
    assert params[1].role is Role.OPAQUE, "the array must NOT become a handle"


def test_propagation_does_not_invent_a_destructor():
    """A function that touches a handle but has no lifecycle evidence becomes
    'uses', never 'destroys'. Granting a release we cannot justify is the
    use-after-free direction, which is exactly what the fail-safe forbids."""
    spec = LibrarySpec("x", {
        "mystery_fn": FunctionSpec("mystery_fn", [_opaque("h", "Thing")], "c_int"),
    })
    propagate_handle_types(spec, {"Thing"}, {"mystery_fn": {"h": "Thing"}})

    assert spec.functions["mystery_fn"].lifecycle == "uses"
    assert spec.functions["mystery_fn"].lifecycle != "destroys"


def test_propagated_handle_still_rejects_fabricated_ids():
    """The runtime guarantee that makes propagation safe: a HANDLE parameter is
    an opaque id the caller cannot forge."""
    t = HandleTable()
    real = t.put(ctypes.c_void_p(0xDEAD), owned=True)

    assert t.get(real) is not None
    with pytest.raises(KeyError):
        t.get(999999)


# ===========================================================================
# Pass 2: structural out-handles are BORROWED
# ===========================================================================

def test_structural_out_handle_is_borrowed_not_owned():
    """THE safety property of pass 2. A structurally-recognized out-handle is
    usable but NOT owned, so a wrong guess leaks instead of double-freeing."""
    spec = LibrarySpec("libgit2", {
        "git_repository_open": FunctionSpec("git_repository_open", [
            _opaque("out", "git_repository"),
            ParamSpec("path", Role.STRING,
                      Evidenced(Intent.IN, ["type"], 1.0, verified=True), "c_char_p"),
        ], "c_int"),
    })
    candidates = {"git_repository_open": {"out": "git_repository"}}

    notes = promote_structural_out_handles(spec, {"git_repository"}, candidates, set())

    fn = spec.functions["git_repository_open"]
    assert fn.handle_out_param == "out"
    assert fn.lifecycle == "creates"
    assert fn.owner == "library", "structural recognition must NOT claim ownership"
    assert "owner=library" in notes[0]
    check_exposable(fn)


def test_confirmed_out_handle_keeps_caller_ownership():
    """A candidate already confirmed by allocation tracing must not be demoted
    by the structural pass -- confirmed evidence outranks structural evidence."""
    spec = LibrarySpec("sqlite", {
        "sqlite3_open": FunctionSpec("sqlite3_open", [
            ParamSpec("path", Role.STRING,
                      Evidenced(Intent.IN, ["type"], 1.0, verified=True), "c_char_p"),
            _opaque("ppDb", "sqlite3"),
        ], "c_int"),
    })
    fn = spec.functions["sqlite3_open"]
    fn.handle_out_param = "ppDb"          # already confirmed upstream
    fn.owner = "caller"
    fn.lifecycle = "creates"

    promote_structural_out_handles(spec, {"sqlite3"},
                                   {"sqlite3_open": {"ppDb": "sqlite3"}},
                                   {("sqlite3_open", "ppDb")})

    assert fn.owner == "caller", "a confirmed out-handle must keep caller ownership"


def test_borrowed_out_handle_cannot_be_freed_at_runtime():
    """End-to-end: the borrowed verdict from pass 2 is enforced by the same
    handle-table check that protects every other borrowed pointer."""
    t = HandleTable()
    hid = t.put(ctypes.c_void_p(0xBEEF), owned=False)   # as a structural out-handle lands

    with pytest.raises(OwnershipError) as e:
        t.pop(hid)
    assert "BORROWED" in str(e.value)


# ===========================================================================
# Pass 3: caller-allocated state
# ===========================================================================

def test_caller_state_without_size_is_refused_by_policy():
    """Belt and braces: even if a CALLER_STATE role reached the policy without
    dimensions, the gate refuses rather than allocating zero bytes."""
    p = ParamSpec("strm", Role.CALLER_STATE,
                  Evidenced(Intent.INOUT, ["caller_state"], 0.8, verified=False),
                  "c_void_p", by_ref=True)
    p.handle_type = "z_stream"
    p.state_size = None
    fn = FunctionSpec("deflate", [p], "c_int")

    with pytest.raises(SpecViolation) as e:
        check_exposable(fn)
    assert "size is unknown" in str(e.value)


# ===========================================================================
# The gate itself must be unchanged
# ===========================================================================

def test_genuinely_opaque_params_are_still_refused():
    """Callbacks and writable buffers -- the things that SHOULD be refused --
    must be refused exactly as before. If this test ever passes a function,
    the extensions crossed the line."""
    cb = FunctionSpec("sqlite3_exec", [
        _opaque("db", "sqlite3"),
        ParamSpec("sql", Role.STRING, Evidenced(Intent.IN, ["type"], 1.0, True), "c_char_p"),
        _opaque("callback", None),          # function pointer: no pointee struct
    ], "c_int")

    with pytest.raises(SpecViolation):
        check_exposable(cb)


def test_propagation_cannot_rescue_a_callback():
    """A function pointer has no struct pointee, so propagation never sees it."""
    spec = LibrarySpec("x", {
        "f": FunctionSpec("f", [_opaque("cb", None)], "c_int"),
    })
    propagate_handle_types(spec, {"Anything"}, {"f": {}})
    assert spec.functions["f"].params[0].role is Role.OPAQUE


def test_raw_voidp_return_rule_untouched():
    """Rule 1 of check_exposable must still fire for unmanaged void* returns."""
    fn = FunctionSpec("cJSON_malloc", [_scalar("size", "c_ulong")], "c_void_p")
    with pytest.raises(SpecViolation):
        check_exposable(fn)


def test_uncertain_destroys_still_refused():
    """The abstention added for lifecycle forwarding must survive these changes."""
    fn = FunctionSpec("png_read_row", [_opaque("png_ptr", "png_struct")], None)
    fn.lifecycle = "uncertain_destroys"
    fn.handle_type = "png_struct"
    with pytest.raises(SpecViolation):
        check_exposable(fn)


# ===========================================================================
# End-to-end against a real compiled object
# ===========================================================================

C_SRC = r"""
#include <stdlib.h>
#include <string.h>

typedef struct counter_state { int count; int limit; char pad[64]; } counter_state;

int counter_init(counter_state *s, int limit) {
    if (!s) return -1;
    s->count = 0; s->limit = limit;
    return 0;
}
int counter_bump(counter_state *s) {
    if (!s || s->count >= s->limit) return -1;
    return ++s->count;
}
int counter_end(counter_state *s) { if (!s) return -1; s->limit = 0; return 0; }
"""


@pytest.fixture(scope="module")
def counter_so(tmp_path_factory):
    d = tmp_path_factory.mktemp("callerstate")
    c, lib = d / "counter.c", d / "libcounter.so"
    c.write_text(C_SRC)
    subprocess.run(["gcc", "-shared", "-fPIC", "-o", str(lib), str(c)], check=True)
    return str(lib)


def test_caller_allocated_state_roundtrip(counter_so):
    """The binding allocates the struct, the library initializes and mutates it,
    and the binding never touches a field. Proves the size/alignment contract is
    sufficient without modelling layout."""
    lib = ctypes.CDLL(counter_so)
    for name in ("counter_init", "counter_bump", "counter_end"):
        getattr(lib, name).restype = ctypes.c_int
    lib.counter_init.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.counter_bump.argtypes = [ctypes.c_void_p]
    lib.counter_end.argtypes = [ctypes.c_void_p]

    size, align = 72, 8          # what clang would report for counter_state
    raw = (ctypes.c_char * (size + align))()
    addr = ctypes.addressof(raw)
    aligned = addr + ((-addr) % align)
    assert aligned % align == 0
    ctypes.memset(aligned, 0, size)

    t = HandleTable()
    hid = t.put((ctypes.c_void_p(aligned), raw), owned=True)
    ptr = t.get(hid)[0]

    assert lib.counter_init(ptr, 3) == 0
    assert lib.counter_bump(ptr) == 1
    assert lib.counter_bump(ptr) == 2
    assert lib.counter_bump(ptr) == 3
    assert lib.counter_bump(ptr) == -1          # limit enforced by the library
    assert lib.counter_end(ptr) == 0

    # The binding owns this memory, so releasing it is legitimate and safe.
    t.pop(hid)
    assert len(t) == 0


# ===========================================================================
# Pass 3 guards -- one test per guard.
#
# Every fixture starts from a struct that DOES become caller state (the
# z_stream shape) and perturbs exactly one property. Each test asserts the
# note its own guard emits, so it can only pass if THAT guard refused the
# type -- not because an earlier guard happened to catch it first.
#
# Replaces four tests that had drifted: they called the detector without
# out_handle_candidates (TypeError before any assertion ran), three passed an
# empty handle set so guard 0 short-circuited them, and the zlib fixture had
# no `local` flag so guard 3 would have refused it as a system type.
# ===========================================================================

_ZFNS = ("deflateInit2_", "deflate", "deflateEnd")
_ZSIZE = {"z_stream": {"size": 112, "align": 8, "local": True}}
_OTHER = {"gzFile_s"}   # zlib's real library-managed handle; not z_stream


def _zlib(fns=_ZFNS, extra=None):
    """z_stream-shaped spec. `extra` maps a function name to its params."""
    funcs = {f: FunctionSpec(f, [_opaque("strm", "z_stream")], "c_int")
             for f in fns}
    pointees = {f: {"strm": "z_stream"} for f in fns}
    for fname, params in (extra or {}).items():
        funcs[fname] = FunctionSpec(fname, params, "c_int")
        pointees[fname] = {p.name: "z_stream" for p in params
                           if p.role is Role.OPAQUE}
    return LibrarySpec("zlib", funcs), pointees


def _detect(spec, pointees, sizes=None, handle_types=None, out=None):
    return detect_caller_allocated_state(
        spec, pointees,
        _ZSIZE if sizes is None else sizes,
        _OTHER if handle_types is None else handle_types,
        {} if out is None else out)


def _notes_about(notes, struct):
    return [n for n in notes if n.startswith(f"{struct}:")]


def test_baseline_zlib_shape_is_caller_state():
    spec, pointees = _zlib()
    facts, notes = _detect(spec, pointees)
    assert "z_stream" in facts, notes
    f = facts["z_stream"]
    assert (f.size, f.init_fn, f.end_fn) == (112, "deflateInit2_", "deflateEnd")
    apply_caller_state_facts(spec, facts, pointees)
    for fn in spec.functions.values():
        assert fn.params[0].role is Role.CALLER_STATE
        check_exposable(fn)


def test_guard0_empty_handle_types_disables_the_pass():
    spec, pointees = _zlib()
    facts, notes = _detect(spec, pointees, handle_types=set())
    assert facts == {}
    assert any("caller-state detection skipped" in n for n in notes)


def test_library_returned_type_is_skipped_silently():
    """The handle-type check is the only guard that emits no note, so silence
    about z_stream proves it -- and not a later guard -- refused the type."""
    spec, pointees = _zlib()
    facts, notes = _detect(spec, pointees, handle_types={"z_stream", "gzFile_s"})
    assert "z_stream" not in facts
    assert _notes_about(notes, "z_stream") == []


def test_guard1_out_parameter_type_is_library_allocated():
    spec, pointees = _zlib()
    facts, notes = _detect(spec, pointees, out={"zopen": {"out": "z_stream"}})
    assert "z_stream" not in facts
    assert any("T** out-parameter" in n for n in _notes_about(notes, "z_stream"))


def test_guard2_destructor_by_lifecycle():
    spec, pointees = _zlib()
    d = FunctionSpec("zfinish", [_opaque("s", "z_stream")], None)
    d.lifecycle, d.handle_type = "destroys", "z_stream"
    spec.functions["zfinish"] = d          # in the spec, NOT in pointees
    facts, notes = _detect(spec, pointees)
    assert "z_stream" not in facts
    assert any("exposes a destructor" in n for n in _notes_about(notes, "z_stream"))


def test_guard2_destructor_by_name_survives_failed_lifecycle():
    """The lexical half: git_signature_free taking git_signature* is enough
    evidence even when lifecycle analysis produced nothing."""
    spec, pointees = _zlib()
    pointees["z_stream_free"] = {"s": "z_stream"}   # name only, no lifecycle
    facts, notes = _detect(spec, pointees)
    assert "z_stream" not in facts
    assert any("exposes a destructor" in n for n in _notes_about(notes, "z_stream"))


def test_no_size_is_refused_not_guessed():
    spec, pointees = _zlib()
    facts, notes = _detect(spec, pointees, sizes={})
    assert facts == {}
    assert any("no size from clang" in n for n in _notes_about(notes, "z_stream"))
    apply_caller_state_facts(spec, facts, pointees)
    assert spec.functions["deflate"].params[0].role is Role.OPAQUE
    with pytest.raises(SpecViolation):
        check_exposable(spec.functions["deflate"])


def test_guard3_missing_locality_flag_is_treated_as_foreign():
    """FILE, struct tm, sockaddr are allocated by libc. A MISSING flag must
    count as foreign: that is what stops the binding forging a FILE."""
    spec, pointees = _zlib()
    facts, notes = _detect(spec, pointees,
                           sizes={"z_stream": {"size": 112, "align": 8}})
    assert "z_stream" not in facts
    assert any("not declared by this library" in n
               for n in _notes_about(notes, "z_stream"))


def test_guard4_no_initializer_is_refused():
    spec, pointees = _zlib(fns=("deflate", "deflateBound"))
    facts, notes = _detect(spec, pointees)
    assert "z_stream" not in facts
    assert any("no initializing function" in n
               for n in _notes_about(notes, "z_stream"))


# ---------------------------------------------------------------------------
# Array guard, as used by apply_caller_state_facts. Here it is a SAFETY guard:
# allocating one 112-byte z_stream where the library indexes an array is a
# buffer overflow, not a coverage gap.
# ---------------------------------------------------------------------------

def _array_case(params):
    spec, pointees = _zlib(extra={"zbatch": params})
    facts, _ = _detect(spec, pointees)
    assert "z_stream" in facts
    notes = apply_caller_state_facts(spec, facts, pointees)
    arr = next(p for p in spec.functions["zbatch"].params if p.name == "arr")
    return arr.role, notes


def test_array_guard_count_after_pointer():
    role, notes = _array_case([_opaque("arr", "z_stream"), _scalar("count")])
    assert role is Role.OPAQUE
    assert any("count parameter" in n for n in notes)


def test_array_guard_count_before_pointer():
    """PQsetResultAttrs(res, numAttributes, attDescs): the count comes first.
    A forward-only guard binds one struct where an array is indexed."""
    role, _ = _array_case([_scalar("count"), _opaque("arr", "z_stream")])
    assert role is Role.OPAQUE


def test_array_guard_camelcase_count():
    """numAttributes: a snake_case regex never sees the word `num`."""
    role, _ = _array_case([_opaque("arr", "z_stream"), _scalar("numItems")])
    assert role is Role.OPAQUE


@pytest.mark.parametrize("names", [
    ("bit_depth", "before"),   # bits per sample, not an element count
    ("flush", "after"),        # deflate's own flush flag
])
def test_array_guard_does_not_over_fire(names):
    name, side = names
    params = ([_scalar(name), _opaque("arr", "z_stream")] if side == "before"
              else [_opaque("arr", "z_stream"), _scalar(name)])
    role, _ = _array_case(params)
    assert role is Role.CALLER_STATE
