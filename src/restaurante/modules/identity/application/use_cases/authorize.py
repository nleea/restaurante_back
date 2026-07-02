"""Authorization use case: enforce that a user holds a required permission."""

from __future__ import annotations

import uuid

from restaurante.modules.identity.domain.ports import (
    PermissionCache,
    PermissionResolver,
)
from restaurante.shared.domain.errors import AuthorizationError


class CachedPermissionResolver:
    """Read-through cache over a `PermissionResolver`.

    Implements `PermissionResolver` itself, so it is a drop-in for the enforcement
    layer. On a miss it delegates to `inner` and stores the result; invalidation
    is handled elsewhere (RbacService) so revoking a permission is seen at once.
    """

    def __init__(self, inner: PermissionResolver, cache: PermissionCache) -> None:
        self._inner = inner
        self._cache = cache

    async def effective_permission_codes(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> frozenset[str]:
        cached = await self._cache.get_codes(tenant_id, user_id)
        if cached is not None:
            return cached
        codes = await self._inner.effective_permission_codes(tenant_id, user_id)
        await self._cache.set_codes(tenant_id, user_id, codes)
        return codes


class AuthorizationService:
    """Resolves effective permissions and enforces a single required code.

    Reads from the DB (via the resolver) on every check, so granting or revoking
    a permission takes effect on the next request.
    """

    def __init__(self, resolver: PermissionResolver) -> None:
        self._resolver = resolver

    async def effective_codes(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> frozenset[str]:
        return await self._resolver.effective_permission_codes(tenant_id, user_id)

    async def ensure(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, code: str
    ) -> None:
        codes = await self._resolver.effective_permission_codes(tenant_id, user_id)
        if code not in codes:
            raise AuthorizationError(f"Falta el permiso requerido: {code}")
