"""Ports (interfaces) of the identity module.

Define the contracts the application layer needs. Concrete adapters
(SQLAlchemy, Argon2, JWT) implement them structurally via Protocol.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from restaurante.modules.identity.domain.entities import (
    Permission,
    PermissionEffect,
    Role,
    User,
    UserPermissionOverride,
)


class UserRepository(Protocol):
    async def get_by_email(
        self, tenant_id: uuid.UUID, email: str
    ) -> User | None: ...

    async def get_by_id(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> User | None: ...


class PasswordHasher(Protocol):
    def hash(self, plain: str) -> str: ...

    def verify(self, plain: str, hashed: str) -> bool: ...


class TokenService(Protocol):
    def create_access_token(
        self, subject: uuid.UUID, tenant_id: uuid.UUID
    ) -> str: ...

    def create_refresh_token(
        self, subject: uuid.UUID, tenant_id: uuid.UUID
    ) -> str: ...

    def decode(self, token: str) -> dict[str, Any]: ...


class PermissionResolver(Protocol):
    """Read-only port used by the enforcement layer (require_permission)."""

    async def effective_permission_codes(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> frozenset[str]: ...


class PermissionCache(Protocol):
    """Cache of effective permission codes per (tenant, user)."""

    async def get_codes(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> frozenset[str] | None: ...

    async def set_codes(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, codes: frozenset[str]
    ) -> None: ...

    async def invalidate_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> None: ...


class RbacRepository(PermissionResolver, Protocol):
    """Resolution + dynamic management of roles, permissions and assignments."""

    # Catalog / roles -------------------------------------------------------
    async def list_permissions(self) -> list[Permission]: ...

    async def list_roles(self, tenant_id: uuid.UUID) -> list[Role]: ...

    async def get_role(
        self, tenant_id: uuid.UUID, role_id: uuid.UUID
    ) -> Role | None: ...

    async def create_role(
        self, tenant_id: uuid.UUID, name: str, description: str | None
    ) -> Role: ...

    # Role <-> permissions --------------------------------------------------
    async def get_role_permission_codes(self, role_id: uuid.UUID) -> set[str]: ...

    async def add_role_permission(
        self, role_id: uuid.UUID, permission_id: uuid.UUID
    ) -> None: ...

    async def remove_role_permission(
        self, role_id: uuid.UUID, permission_id: uuid.UUID
    ) -> None: ...

    async def set_role_permissions(
        self, role_id: uuid.UUID, permission_ids: list[uuid.UUID]
    ) -> None: ...

    # Users -----------------------------------------------------------------
    async def list_tenant_users(self, tenant_id: uuid.UUID) -> list[User]: ...

    # User <-> roles --------------------------------------------------------
    async def get_user_roles(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Role]: ...

    async def get_role_members(
        self, role_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, uuid.UUID]]: ...

    async def assign_user_role(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID
    ) -> None: ...

    async def revoke_user_role(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, role_id: uuid.UUID
    ) -> None: ...

    # User overrides --------------------------------------------------------
    async def get_user_overrides(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[UserPermissionOverride]: ...

    async def set_user_override(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        permission_id: uuid.UUID,
        effect: PermissionEffect,
    ) -> None: ...

    async def remove_user_override(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, permission_id: uuid.UUID
    ) -> None: ...
