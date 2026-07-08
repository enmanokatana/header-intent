"""Handle table: integer ids <-> opaque C pointers """
import itertools
import threading


class HandleTable:
    def __init__(self):
        self._items: dict[int, object] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def put(self, obj) -> int:
        with self._lock:
            hid = next(self._ids)
            self._items[hid] = obj
            return hid

    def get(self, hid: int):
        try:
            return self._items[hid]
        except KeyError:
            raise KeyError(f"unknown or freed handle: {hid}") from None

    def pop(self, hid: int):
        with self._lock:
            try:
                return self._items.pop(hid)
            except KeyError:
                raise KeyError(f"unknown or freed handle: {hid}") from None

    def __len__(self) -> int:
        return len(self._items)