"""Provision a tenant user with an inline person (and an optional initial role).

This is the missing piece that lets a client create the `user_id`/`person_id` that
`POST /staff/employees` expects. Person + user are created atomically; the optional
role is assigned through `RbacService` so the permission cache is invalidated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from restaurante.modules.identity.application.use_cases.manage_rbac import RbacService
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyUserRepository,
)
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.security.password import Argon2PasswordHasher


@dataclass(frozen=True)
class ProvisionedUser:
    id: uuid.UUID
    email: str
    name: str
    is_active: bool
    person_id: uuid.UUID


class ProvisionUserUseCase:
    def __init__(
        self,
        users: SqlAlchemyUserRepository,
        hasher: Argon2PasswordHasher,
        rbac: RbacService,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._rbac = rbac

    async def execute(
        self,
        tenant_id: uuid.UUID,
        *,
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        document_number: str | None = None,
        phone: str | None = None,
        role_id: uuid.UUID | None = None,
    ) -> ProvisionedUser:
        if await self._users.get_by_email(tenant_id, email) is not None:
            raise ConflictError("Ese correo ya está registrado para este negocio.")

        hashed = self._hasher.hash(password)
        user_id, person_id = await self._users.create_with_person(
            tenant_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            hashed_password=hashed,
            document_number=document_number,
            phone=phone,
        )

        # Optional initial role: routed through RbacService so the role is validated
        # and the permission cache is invalidated (a raw insert would leave it stale).
        if role_id is not None:
            await self._rbac.assign_user_role(tenant_id, user_id, role_id)

        return ProvisionedUser(
            id=user_id,
            email=email,
            name=f"{first_name} {last_name}",
            is_active=True,
            person_id=person_id,
        )
