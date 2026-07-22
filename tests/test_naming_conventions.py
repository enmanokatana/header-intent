
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.layers.l2_ownership import _is_alloc_name, _tokenize_ident
from src.layers.l2_handles import _is_dealloc_name


def test_tokenizer_splits_both_conventions():
    assert _tokenize_ident("sqlite3MallocZero") == ["sqlite3", "malloc", "zero"]
    assert _tokenize_ident("sqlite3_malloc") == ["sqlite3", "malloc"]

def test_alloc_recognizes_camelcase():
    """THE bug: sqlite3's actual internal allocator has no underscores at all."""
    assert _is_alloc_name("sqlite3MallocZero")
    assert _is_alloc_name("sqlite3DbMallocRaw")

def test_alloc_still_recognizes_snake_case():
    """Must not regress cJSON's convention."""
    assert _is_alloc_name("sqlite3_malloc")
    assert _is_alloc_name("allocate")          

def test_alloc_rejects_substring_false_positive():
    """'deallocate' must not look like it contains the allocator word 'allocate'."""
    assert not _is_alloc_name("deallocate")
    assert not _is_alloc_name("unallocated")

def test_alloc_rejects_unrelated_camelcase():
    assert not _is_alloc_name("openDatabase")
    assert not _is_alloc_name("sqlite3_free")

def test_dealloc_recognizes_camelcase():
    """Same convention gap, for the deallocator side (sqlite3_close's internal
    free is sqlite3DbFree)."""
    assert _is_dealloc_name("sqlite3DbFree")
    assert _is_dealloc_name("sqlite3VdbeFreeCursor")

def test_dealloc_still_recognizes_snake_case():
    assert _is_dealloc_name("sqlite3_free")
    assert _is_dealloc_name("cJSON_Delete")
    assert _is_dealloc_name("free")
