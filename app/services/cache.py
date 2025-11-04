from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import Hashable, Optional


class RetrievalCache:
    """Simple thread-safe LRU cache used to memoize retrieval results."""

    def __init__(self, max_entries: int = 128) -> None:
        self.max_entries = max_entries
        self._store: OrderedDict[Hashable, object] = OrderedDict()
        self._lock = Lock()

    def _make_key(self, role: str, question: str) -> Hashable:
        return (role.strip().lower(), question.strip())

    def get(self, role: str, question: str) -> Optional[object]:
        key = self._make_key(role, question)
        with self._lock:
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            return self._store[key]

    def set(self, role: str, question: str, value: object) -> None:
        key = self._make_key(role, question)
        with self._lock:
            self._store[key] = value
            self._store.move_to_end(key)
            if len(self._store) > self.max_entries:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
