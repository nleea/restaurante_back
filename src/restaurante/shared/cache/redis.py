"""Redis cache backend (distributed). Use in multi-instance deployments.

`redis` is imported lazily (via importlib) so this module imports — and the rest
of the app and the test suite (which use the in-memory backend) keep working —
even when the `redis` package is not installed. The client is typed as `Any`
for the same reason; install `redis` to actually use this backend.
"""

from __future__ import annotations

import importlib
from typing import Any


class RedisCache:
    """Implements the `Cache` port over `redis.asyncio`.

    Keys are namespaced with `prefix` so `clear()` only removes this app's keys
    (via SCAN), never the whole database.
    """

    def __init__(self, url: str, prefix: str = "restaurante:") -> None:
        redis_asyncio = importlib.import_module("redis.asyncio")
        self._client: Any = redis_asyncio.from_url(url, decode_responses=True)
        self._prefix = prefix

    def _k(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> str | None:
        value = await self._client.get(self._k(key))
        return value if value is None else str(value)

    async def set(
        self, key: str, value: str, ttl_seconds: int | None = None
    ) -> None:
        await self._client.set(self._k(key), value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._client.delete(self._k(key))

    async def clear(self) -> None:
        async for raw_key in self._client.scan_iter(match=f"{self._prefix}*"):
            await self._client.delete(raw_key)
