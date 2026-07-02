"""Unit tests for the in-memory cache backend."""

from __future__ import annotations

from restaurante.shared.cache.memory import InMemoryCache


async def test_set_get_delete() -> None:
    cache = InMemoryCache()
    assert await cache.get("k") is None

    await cache.set("k", "v")
    assert await cache.get("k") == "v"

    await cache.delete("k")
    assert await cache.get("k") is None


async def test_overwrite_and_clear() -> None:
    cache = InMemoryCache()
    await cache.set("a", "1")
    await cache.set("a", "2")
    assert await cache.get("a") == "2"

    await cache.set("b", "3")
    await cache.clear()
    assert await cache.get("a") is None
    assert await cache.get("b") is None


async def test_expired_entry_is_evicted() -> None:
    cache = InMemoryCache()
    # ttl_seconds=0 means "no TTL" by design; force an already-expired entry by
    # writing directly with a past expiry to exercise the lazy-eviction path.
    cache._store["k"] = ("v", 0.0)  # expires_at in the monotonic past
    assert await cache.get("k") is None
