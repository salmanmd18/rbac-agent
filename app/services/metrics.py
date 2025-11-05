from __future__ import annotations

from collections import defaultdict
from threading import Lock
from typing import Dict


class MetricsTracker:
    """Thread-safe tracker for basic usage analytics."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._per_role: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0})
        self._grand_total = 0

    def record(self, role: str, mode: str) -> None:
        normalized_role = role.strip().lower()
        normalized_mode = mode.strip().lower()
        with self._lock:
            role_entry = self._per_role[normalized_role]
            role_entry["total"] = role_entry.get("total", 0) + 1
            mode_key = f"mode:{normalized_mode}"
            role_entry[mode_key] = role_entry.get(mode_key, 0) + 1
            self._grand_total += 1

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            per_role_copy = {
                role: dict(counts)
                for role, counts in self._per_role.items()
            }
            return {
                "grand_total": self._grand_total,
                "per_role": per_role_copy,
            }

    def reset(self) -> None:
        with self._lock:
            self._per_role.clear()
            self._grand_total = 0
