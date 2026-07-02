"""App-wide cache layer: a `Cache` port with pluggable backends.

`get_cache()` returns a process-wide singleton chosen by `settings.cache_backend`
(`memory` by default, `redis` in production). Any module can depend on the
`Cache` port for its own caching needs.
"""

from __future__ import annotations

from functools import lru_cache

from restaurante.shared.cache.base import Cache
from restaurante.shared.cache.memory import InMemoryCache
from restaurante.shared.config import get_settings

__all__ = ["Cache", "get_cache"]


@lru_cache
def get_cache() -> Cache:
    settings = get_settings()
    if settings.cache_backend == "redis":
        # Imported here so the redis dependency is only required when selected.
        from restaurante.shared.cache.redis import RedisCache

        return RedisCache(settings.redis_url)
    return InMemoryCache()
