"""In-memory TTL cache used for the structural indexes and optional price caching."""

from __future__ import annotations

import time
from collections.abc import Callable, Hashable


class TTLCache[T]:
    """Key-value cache with time-based expiry.

    ``ttl=None`` means entries never expire. The clock is injectable for
    tests. Entry values may be any type; a stored ``None`` is indistinguishable
    from a miss (this package only caches model objects, never None).
    """

    def __init__(self, ttl: float | None, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl
        self._clock = clock
        self._entries: dict[Hashable, tuple[T, float]] = {}

    def get(self, key: Hashable) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, deadline = entry
        if self._ttl is not None and self._clock() >= deadline:
            del self._entries[key]
            return None
        return value

    def set(self, key: Hashable, value: T) -> None:
        deadline = float("inf") if self._ttl is None else self._clock() + self._ttl
        self._entries[key] = (value, deadline)

    def clear(self) -> None:
        self._entries.clear()
