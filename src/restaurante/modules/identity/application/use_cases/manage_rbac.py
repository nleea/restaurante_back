"""Application service for dynamic RBAC management.

Wraps the `RbacRepository` with domain validation and accepts permission *codes*
(friendlier for the API) instead of raw ids. Keeps the API layer thin.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from restaurante.modules.identity.domain.entities import (
    Permission,
    PermissionEffect,
    Role,
    User,
    UserPermissionOverride,
)
from restaurante.modules.identity.domain.ports import (
    PermissionCache,
    RbacRepository,
)
from restaurante.shared.domain.errors import NotFoundError


@dataclass
class UserAccess:
    """Snapshot of what a user can do: roles, effective codes and overrides."""

    roles: list[Role]
    effective_codes: list[str]
    overrides: list[UserPermissionOverride]


class RbacService:
    def __init__(self, repo: RbacRepository, cache: PermissionCache) -> None:
        self._repo = repo
        self._cache = cache

    async def _invalidate_role_members(self, role_id: uuid.UUID) -> None:
        for tenant_id, user_id in await self._repo.get_role_members(role_id):
            await self._cache.invalidate_user(tenant_id, user_id)

    async def _permission_id_by_code(self, code: str) -> uuid.UUID:
        for permission in await self._repo.list_permissions():
            if permission.code == code:
                return permission.id
        raise NotFoundError(f"Permiso desconocido: {code}")

    async def _require_role(self, tenant_id: uuid.UUID, role_id: uuid.UUID) -> Role:
        role = await self._repo.get_role(tenant_id, role_id)
        if role is None:
            raise NotFoundError(f"Rol no encontrado: {role_id}")
        return role

    # --- Catalog / roles ---------------------------------------------------
    async def list_permissions(self) -> list[Permission]:
        return await self._repo.list_permissions()

    async def list_roles(self, tenant_id: uuid.UUID) -> list[Role]:
        return await self._repo.list_roles(tenant_id)

    async def list_tenant_users(self, tenant_id: uuid.UUID) -> list[User]:
        return await self._repo.list_tenant_users(tenant_id)

    async def create_role(
        self, tenant_id: uuid.UUID, name: str, description: str | None
    ) -> Role:
        return await self._repo.create_role(tenant_id, name, description)

    # --- Role <-> permissions ---------------------------------------------
    async def get_role_permission_codes(
        self, tenant_id: uuid.UUID, role_id: uuid.UUID
    ) -> list[str]:
        await self._require_role(tenant_id, role_id)
        return sorted(await self._repo.get_role_permission_codes(role_id))

    async def set_role_permissions(
        self, tenant_id: uuid.UUID, role_id: uuid.UUID, codes: list[str]
    ) -> list[str]:
        await self._require_role(tenant_id, role_id)
        ids = [await self._permission_id_by_code(c) for c in codes]
        await self._repo.set_role_permissions(role_id, ids)
        await self._invalidate_role_members(role_id)
        return sorted(set(codes))

    async def add_role_permission(
        self, tenant_id: uuid.UUID, role_id: uuid.UUID, code: str
    ) -> None:
        await self._require_role(tenant_id, role_id)
        await self._repo.add_role_permission(
            role_id, await self._permission_id_by_code(code)
        )
        await self._invalidate_role_members(role_id)

    async def remove_role_permission(
        self, tenant_id: uuid.UUID, role_id: uuid.UUID, code: str
    ) -> None:
        await self._require_role(tenant_id, role_id)
        await self._repo.remove_role_permission(
            role_id, await self._permission_id_by_code(code)
        )
        await self._invalidate_role_members(role_id)

    # --- User access -------------------------------------------------------
    async def get_user_access(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> UserAccess:
        roles = await self._repo.get_user_roles(tenant_id, user_id)
        effective = await self._repo.effective_permission_codes(tenant_id, user_id)
        overrides = await self._repo.get_user_overrides(tenant_id, user_id)
        return UserAccess(
            roles=roles,
            effective_codes=sorted(effective),
            overrides=overrides,
        )

    async def assign_user_role(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID
    ) -> None:
        await self._require_role(tenant_id, role_id)
        await self._repo.assign_user_role(tenant_id, user_id, role_id)
        await self._cache.invalidate_user(tenant_id, user_id)

    async def revoke_user_role(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID
    ) -> None:
        await self._repo.revoke_user_role(tenant_id, user_id, role_id)
        await self._cache.invalidate_user(tenant_id, user_id)

    async def set_user_override(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        code: str,
        effect: PermissionEffect,
    ) -> None:
        await self._repo.set_user_override(
            tenant_id, user_id, await self._permission_id_by_code(code), effect
        )
        await self._cache.invalidate_user(tenant_id, user_id)

    async def remove_user_override(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, code: str
    ) -> None:
        await self._repo.remove_user_override(
            tenant_id, user_id, await self._permission_id_by_code(code)
        )
        await self._cache.invalidate_user(tenant_id, user_id)
