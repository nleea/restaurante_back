"""In-memory cache backend (per process). Default for dev and tests.

Not shared across workers/instances, so in a multi-instance deployment use the
Redis backend instead. Expiry is evaluated lazily on read.
"""

from __future__ import annotations

import time


class InMemoryCache:
    """Implements the `Cache` port with a plain dict and lazy expiry."""

    def __init__(self) -> None:
        # value -> (payload, expires_at_monotonic | None)
        self._store: dict[str, tuple[str, float | None]] = {}

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(
        self, key: str, value: str, ttl_seconds: int | None = None
    ) -> None:
        expires_at = time.monotonic() + ttl_seconds if ttl_seconds else None
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()
