"""
Handle table with OWNERSHIP ENFORCEMENT and CASCADE INVALIDATION.

Drop-in replacement for src/core/handles.py. The existing API is unchanged
(put/get/is_owned/pop/__len__), so no caller breaks; three things are added.

WHY THIS EXISTS
---------------
The ownership check answers one direction of the liveness question: a BORROWED
handle must never be freed, because the library still owns it. The other
direction was unhandled, and the paper's own RQ3 transcript exhibits it:

    Parse                 -> 1            (owned root)
    GetObjectItem         -> 2            (borrowed interior node, points INTO 1)
    Delete(2)             -> REFUSED      (correct)
    Delete(1)             -> freed        (correct -- 1 is owned)
    <handle 2 now points into freed memory, and the table still serves it>

Any later call taking handle 2 is a use-after-free, and no ownership check can
catch it because the operation is a READ, not a free. The fix is to record where
a borrowed handle came from and invalidate the subtree when its owner dies.

WHAT CHANGED
------------
1. put(obj, owned, parent=None)   -- a borrowed handle records its owner.
2. pop() cascades                 -- destroying an owned handle invalidates every
                                     handle derived from it, transitively.
3. get() distinguishes            -- StaleHandleError (invalidated by an owner's
                                     destruction, with the owner named) vs a plain
                                     unknown id. StaleHandleError subclasses
                                     KeyError so existing `except KeyError` paths
                                     still work.

The invariant this maintains: the table never hands out a pointer the library has
already freed, in either direction.
"""

from __future__ import annotations

import itertools
import threading


class OwnershipError(Exception):
    """Raised when a borrowed handle is asked to be freed."""


class StaleHandleError(KeyError):
    """Raised when a handle was invalidated because its owner was destroyed.

    Subclasses KeyError so callers written against the previous HandleTable
    (`except KeyError`) keep working; new callers can catch this specifically to
    produce the better message.
    """


# How many invalidated ids to remember for good error messages. Beyond this the
# oldest are forgotten and become plain "unknown handle" errors -- a bounded
# quality-of-message cost, never a safety one.
_INVALIDATED_MEMORY = 4096


class HandleTable:
    def __init__(self):
        self._items: dict[int, object] = {}
        self._owned: dict[int, bool] = {}
        self._parent: dict[int, int] = {}          # child hid -> parent hid
        self._children: dict[int, set[int]] = {}   # parent hid -> child hids
        self._invalidated: dict[int, int] = {}     # hid -> owner hid that killed it
        self._invalidated_order: list[int] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ put

    def put(self, obj, owned: bool = True, parent: int | None = None) -> int:
        """Register a handle.

        `parent` is the handle this one was derived from, and is what makes
        cascade invalidation possible. Supply it whenever the C pointer points
        INTO an object the table already holds -- i.e. for every `borrows`
        capability, where the parent is the handle input the call was made on.
        A None parent means the handle is a root.
        """
        with self._lock:
            hid = next(self._ids)
            self._items[hid] = obj
            self._owned[hid] = owned
            if parent is not None and parent in self._items:
                self._parent[hid] = parent
                self._children.setdefault(parent, set()).add(hid)
            return hid

    # ------------------------------------------------------------------ get

    def get(self, hid: int):
        if hid in self._items:
            return self._items[hid]
        owner = self._invalidated.get(hid)
        if owner is not None:
            raise StaleHandleError(
                f"handle {hid} was invalidated when its owner (handle {owner}) was "
                f"destroyed; the memory it pointed into has been freed. Re-derive it "
                f"from a live handle."
            )
        raise KeyError(f"unknown or freed handle: {hid}")

    def is_owned(self, hid: int) -> bool:
        self.get(hid)                      # raises for unknown / stale
        return self._owned.get(hid, False)

    def is_live(self, hid: int) -> bool:
        return hid in self._items

    def parent_of(self, hid: int) -> int | None:
        return self._parent.get(hid)

    def children_of(self, hid: int) -> set[int]:
        return set(self._children.get(hid, ()))

    # ------------------------------------------------------------------ pop

    def pop(self, hid: int):
        """Remove an OWNED handle. Refuses borrowed ones (would double-free).

        Backwards compatible: returns the stored object. Use pop_cascade() when
        the caller wants to report which derived handles were invalidated.
        """
        obj, _ = self.pop_cascade(hid)
        return obj

    def pop_cascade(self, hid: int) -> tuple[object, list[int]]:
        """Remove an owned handle and invalidate everything derived from it.

        Returns (object, invalidated_child_ids). The children are invalidated
        rather than merely dropped, so a later call on one of them produces a
        StaleHandleError naming the owner instead of a bare 'unknown handle'.
        """
        with self._lock:
            if hid not in self._items:
                owner = self._invalidated.get(hid)
                if owner is not None:
                    raise StaleHandleError(
                        f"handle {hid} was already invalidated when its owner "
                        f"(handle {owner}) was destroyed."
                    )
                raise KeyError(f"unknown or freed handle: {hid}")
            if not self._owned.get(hid, False):
                raise OwnershipError(
                    f"handle {hid} is BORROWED (owned by the library, e.g. an item "
                    f"inside a parsed tree); freeing it would double-free. Delete the "
                    f"owner instead."
                )

            # Collect the whole subtree before mutating anything.
            doomed: list[int] = []
            stack = list(self._children.get(hid, ()))
            while stack:
                child = stack.pop()
                if child in doomed:
                    continue
                doomed.append(child)
                stack.extend(self._children.get(child, ()))

            for child in doomed:
                self._items.pop(child, None)
                self._owned.pop(child, None)
                p = self._parent.pop(child, None)
                if p is not None:
                    self._children.get(p, set()).discard(child)
                self._children.pop(child, None)
                self._remember_invalidated(child, hid)

            self._children.pop(hid, None)
            p = self._parent.pop(hid, None)
            if p is not None:
                self._children.get(p, set()).discard(hid)
            self._owned.pop(hid, None)
            return self._items.pop(hid), doomed

    def _remember_invalidated(self, hid: int, owner: int) -> None:
        self._invalidated[hid] = owner
        self._invalidated_order.append(hid)
        while len(self._invalidated_order) > _INVALIDATED_MEMORY:
            self._invalidated.pop(self._invalidated_order.pop(0), None)

    # ---------------------------------------------------------------- stats

    def __len__(self) -> int:
        return len(self._items)

    def stats(self) -> dict:
        return {
            "live": len(self._items),
            "owned": sum(1 for v in self._owned.values() if v),
            "borrowed": sum(1 for v in self._owned.values() if not v),
            "tracked_parents": len(self._parent),
            "remembered_invalidations": len(self._invalidated),
        }


# --------------------------------------------------------------------------
# Self-test: reproduces the paper's RQ3 transcript and asserts the hole is shut.
# Run standalone: python3 handles.py
# --------------------------------------------------------------------------
if __name__ == "__main__":
    t = HandleTable()

    root = t.put("cJSON* root", owned=True)                 # Parse       -> 1
    child = t.put("cJSON* item", owned=False, parent=root)  # GetObjectItem -> 2

    try:
        t.pop(child)
        raise AssertionError("borrowed free was NOT refused")
    except OwnershipError as e:
        assert "BORROWED" in str(e)

    obj, invalidated = t.pop_cascade(root)                  # Delete(root)
    assert obj == "cJSON* root"
    assert invalidated == [child], invalidated
    assert len(t) == 0, t.stats()

    try:
        t.get(child)
        raise AssertionError("stale child was still served -- use-after-free")
    except StaleHandleError as e:
        assert f"owner (handle {root})" in str(e), str(e)

    # deep chains
    t2 = HandleTable()
    a = t2.put("root", owned=True)
    b = t2.put("child", owned=False, parent=a)
    c = t2.put("grandchild", owned=False, parent=b)
    _, dead = t2.pop_cascade(a)
    assert set(dead) == {b, c}, dead
    assert len(t2) == 0

    # an unrelated root is untouched
    t3 = HandleTable()
    r1 = t3.put("r1", owned=True)
    r2 = t3.put("r2", owned=True)
    k1 = t3.put("k1", owned=False, parent=r1)
    t3.pop_cascade(r1)
    assert t3.is_live(r2) and not t3.is_live(k1)

    # legacy callers still work
    t4 = HandleTable()
    h = t4.put("x", owned=True)
    assert t4.get(h) == "x" and t4.is_owned(h) and t4.pop(h) == "x"
    try:
        t4.get(h)
        raise AssertionError("freed handle still served")
    except KeyError:
        pass

    print("cascade invalidation: all checks passed")