"""
Multi-file processing (Stage 1): a real library is many .c files, not one
amalgamation. These tests verify the merge machinery that lets L2 analyses span
files -- the union of per-file facts, cross-file ownership call propagation, and
skip-and-report on files that fail to parse.

The engine analyses themselves are libclang-only (not runnable here), so these
tests target the merge/classify logic directly with lightweight fakes, plus the
real classify_ownership fixed point over a merged record set.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.layers.l2_ownership import classify_ownership, OwnRecord
from src.layers.libclang_engine import _merge_multi


class _FakeEngine:
    """Stands in for LibclangEngine: returns canned per-file records and can be
    told to raise on specific files to exercise skip-and-report."""
    def __init__(self, per_file, fail_on=()):
        self._per_file = per_file          # {path: {fname: record}}
        self._fail_on = set(fail_on)

    def some_records(self, path, clang_args=None, **kw):
        if path in self._fail_on:
            raise RuntimeError("simulated parse failure")
        return dict(self._per_file.get(path, {}))


def test_merge_unions_per_file_facts():
    eng = _FakeEngine({
        "a.c": {"foo": 1, "bar": 2},
        "b.c": {"baz": 3},
    })
    merged, skipped = _merge_multi(eng, "some_records", ["a.c", "b.c"], None)
    assert merged == {"foo": 1, "bar": 2, "baz": 3}
    assert skipped == []


def test_merge_skips_and_reports_a_failed_file():
    eng = _FakeEngine({
        "a.c": {"foo": 1},
        "b.c": {"bar": 2},
    }, fail_on=["b.c"])
    merged, skipped = _merge_multi(eng, "some_records", ["a.c", "b.c"], None)
    assert merged == {"foo": 1}                 # a.c survived
    assert len(skipped) == 1 and "b.c" in skipped[0]   # b.c reported, not fatal


def test_first_file_wins_on_collision():
    eng = _FakeEngine({
        "a.c": {"dup": "from_a"},
        "b.c": {"dup": "from_b"},
    })
    merged, _ = _merge_multi(eng, "some_records", ["a.c", "b.c"], None)
    assert merged["dup"] == "from_a"            # deterministic, caller-order


def test_cross_file_ownership_call_propagation():
    """THE core multi-file win: wrapper() in file A returns make() defined in
    file B. Per-file, A cannot resolve make; merged, the classify_ownership
    fixed point propagates make's alloc verdict to wrapper across files."""
    recA = {"wrapper": OwnRecord("wrapper", returns_pointer=True, origin="call:make")}
    recB = {"make": OwnRecord("make", returns_pointer=True, origin="alloc")}

    # A alone: wrapper is unresolved -> fail-safe borrowed (library)
    a_only = classify_ownership(dict(recA))
    assert a_only["wrapper"].owner == "library"

    # merged: propagation resolves wrapper to caller-owned
    merged = classify_ownership({**recA, **recB})
    assert merged["make"].owner == "caller"
    assert merged["wrapper"].owner == "caller"


def test_all_files_failing_yields_empty_not_crash():
    eng = _FakeEngine({"a.c": {"x": 1}}, fail_on=["a.c"])
    merged, skipped = _merge_multi(eng, "some_records", ["a.c"], None)
    assert merged == {}
    assert len(skipped) == 1
