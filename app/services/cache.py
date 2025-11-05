from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import Hashable, Optional, Sequence


class RetrievalCache:
    """Simple thread-safe LRU cache used to memoize retrieval results."""

    def __init__(self, max_entries: int = 128) -> None:
        self.max_entries = max_entries
        self._store: OrderedDict[Hashable, object] = OrderedDict()
        self._lock = Lock()

    def _make_key(self, role: str, question: str) -> Hashable:
        return (role.strip().lower(), question.strip())

    def _clone(self, value: object) -> object:
        if isinstance(value, list):
            return [dict(item) if isinstance(item, dict) else item for item in value]
        return value

    def get(self, role: str, question: str) -> Optional[object]:
        key = self._make_key(role, question)
        with self._lock:
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            cached = self._store[key]
            return self._clone(cached)

    def set(self, role: str, question: str, value: object) -> None:
        key = self._make_key(role, question)
        with self._lock:
            self._store[key] = self._clone(value)
            self._store.move_to_end(key)
            if len(self._store) > self.max_entries:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._store)
