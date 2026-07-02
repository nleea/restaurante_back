"""Cache port: a small async key/value contract shared by the whole app.

Values are plain strings (callers serialize to JSON when needed). Concrete
backends (in-memory, Redis) implement this Protocol structurally.
"""

from __future__ import annotations

from typing import Protocol


class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def clear(self) -> None:
        """Remove every entry owned by this cache (scoped by key prefix)."""
        ...
