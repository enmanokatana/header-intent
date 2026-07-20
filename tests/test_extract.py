"""
L0 extractor tests. The type-mapping logic is tested against a mock clang
interface (no libclang needed) so the canonical-typedef resolution -- the
cJSON_bool crash fix -- is covered everywhere. A live libclang test runs where
libclang is installed.
"""
import ctypes
import enum
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# --- mock-clang unit tests (always run) -----------------------------------
class _TK(enum.Enum):
    VOID = 1; BOOL = 2; CHAR_S = 3; CHAR_U = 4; SCHAR = 5; UCHAR = 6
    USHORT = 7; SHORT = 8; UINT = 9; INT = 10; ULONG = 11; LONG = 12
    ULONGLONG = 13; LONGLONG = 14; FLOAT = 15; DOUBLE = 16; LONGDOUBLE = 17
    POINTER = 18; ENUM = 19; RECORD = 20; CONSTANTARRAY = 21
    FUNCTIONPROTO = 22; FUNCTIONNOPROTO = 23


class _T:
    def __init__(self, kind, canonical=None, pointee=None, const=False, spelling=""):
        self.kind = kind; self._c = canonical; self._p = pointee
        self._const = const; self.spelling = spelling
    def get_canonical(self): return self._c if self._c is not None else self
    def get_pointee(self): return self._p
    def is_const_qualified(self): return self._const


@pytest.fixture
def ex():
    import src.models.extract as ex
    # save real state, patch to mock, restore afterward so nothing leaks
    saved = (ex.cindex, ex._HAVE)
    ex.cindex = types.SimpleNamespace(TypeKind=_TK)
    ex._HAVE = True
    try:
        yield ex
    finally:
        ex.cindex, ex._HAVE = saved


def test_typedef_resolved_canonically(ex):
    # typedef int cJSON_bool  -- the crash case: canonical is INT
    int_t = _T(_TK.INT)
    cjson_bool = _T(_TK.INT, canonical=int_t, spelling="cJSON_bool")
    assert ex._map_type(cjson_bool) is ctypes.c_int


def test_const_char_ptr_is_string(ex):
    p = _T(_TK.POINTER, pointee=_T(_TK.CHAR_S, canonical=_T(_TK.CHAR_S), const=True))
    p._c = p
    assert ex._map_type(p) is ctypes.c_char_p


def test_scalar_ptr(ex):
    p = _T(_TK.POINTER, pointee=_T(_TK.INT, canonical=_T(_TK.INT)))
    p._c = p
    assert ex._map_type(p).__name__ == "LP_c_int"


def test_struct_ptr_is_void_p(ex):
    p = _T(_TK.POINTER, pointee=_T(_TK.RECORD, canonical=_T(_TK.RECORD)))
    p._c = p
    assert ex._map_type(p) is ctypes.c_void_p


def test_out_classification(ex):
    dbl = _T(_TK.POINTER, pointee=_T(_TK.DOUBLE, canonical=_T(_TK.DOUBLE), const=False))
    dbl._c = dbl
    cchar = _T(_TK.POINTER, pointee=_T(_TK.CHAR_S, canonical=_T(_TK.CHAR_S), const=True))
    cchar._c = cchar
    assert ex._pointer_is_out(dbl) is True
    assert ex._pointer_is_out(cchar) is False


# --- live libclang test (skips if absent) ---------------------------------
def test_live_extract_resolves_typedef(tmp_path):
    pytest.importorskip("clang.cindex")
    import importlib
    import src.models.extract as ex
    importlib.reload(ex)          # undo any leaked mock patch from earlier tests
    from src.models.extract import extract_signatures
    h = tmp_path / "x.h"
    h.write_text("""
        typedef int my_bool;
        my_bool is_ok(const char *s, int n);
        double scale(double *v, double k);
    """)
    sigs, skipped = extract_signatures(str(h))
    assert "is_ok" in sigs
    # my_bool resolved to c_int (return + not skipped)
    assert sigs["is_ok"]["restype"] is ctypes.c_int
    assert sigs["is_ok"]["argtypes"][0] is ctypes.c_char_p
    assert sigs["scale"]["pointers"] == {"v": "out"}    # non-const double* -> out