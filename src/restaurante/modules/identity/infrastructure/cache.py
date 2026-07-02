"""Permission cache adapter: maps the `PermissionCache` port onto a `Cache`.

Stores the effective permission codes of each (tenant, user) as a JSON list with
a TTL backstop. Correctness comes from explicit invalidation (see RbacService);
the TTL only bounds the impact of a missed invalidation.
"""

from __future__ import annotations

import json
import uuid

from restaurante.shared.cache.base import Cache


class RbacPermissionCache:
    """Implements `PermissionCache` over the app-wide `Cache`."""

    def __init__(self, cache: Cache, ttl_seconds: int) -> None:
        self._cache = cache
        self._ttl = ttl_seconds

    @staticmethod
    def _key(tenant_id: uuid.UUID, user_id: uuid.UUID) -> str:
        return f"rbac:perms:{tenant_id}:{user_id}"

    async def get_codes(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> frozenset[str] | None:
        raw = await self._cache.get(self._key(tenant_id, user_id))
        if raw is None:
            return None
        return frozenset(json.loads(raw))

    async def set_codes(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, codes: frozenset[str]
    ) -> None:
        await self._cache.set(
            self._key(tenant_id, user_id),
            json.dumps(sorted(codes)),
            ttl_seconds=self._ttl,
        )

    async def invalidate_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        await self._cache.delete(self._key(tenant_id, user_id))
