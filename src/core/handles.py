
import itertools
import threading


class OwnershipError(Exception):
    """Raised when a borrowed handle is asked to be freed."""


class HandleTable:
    def __init__(self):
        self._items: dict[int, object] = {}
        self._owned: dict[int, bool] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def put(self, obj, owned: bool = True) -> int:
        with self._lock:
            hid = next(self._ids)
            self._items[hid] = obj
            self._owned[hid] = owned
            return hid

    def get(self, hid: int):
        try:
            return self._items[hid]
        except KeyError:
            raise KeyError(f"unknown or freed handle: {hid}") from None

    def is_owned(self, hid: int) -> bool:
        self.get(hid)                                        
        return self._owned.get(hid, False)

    def pop(self, hid: int):
        """Remove an OWNED handle. Refuses borrowed ones (would double-free)."""
        with self._lock:
            if hid not in self._items:
                raise KeyError(f"unknown or freed handle: {hid}")
            if not self._owned.get(hid, False):
                raise OwnershipError(
                    f"handle {hid} is BORROWED (owned by the library, e.g. an item "
                    f"inside a parsed tree); freeing it would double-free. Delete the "
                    f"owner instead."
                )
            self._owned.pop(hid, None)
            return self._items.pop(hid)

    def __len__(self) -> int:
        return len(self._items)
