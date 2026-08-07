"""Ports (interfaces) of the Guest Profile module."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from restaurante.modules.guest_profile.domain.entities import GuestProfile


class GuestProfileRepository(Protocol):
    async def get_by_token(
        self, tenant_id: uuid.UUID, token: uuid.UUID
    ) -> GuestProfile | None: ...

    async def create(self, profile: GuestProfile) -> GuestProfile: ...

    async def update(
        self, tenant_id: uuid.UUID, token: uuid.UUID, fields: dict[str, Any]
    ) -> GuestProfile | None: ...

    async def link_user(
        self, tenant_id: uuid.UUID, token: uuid.UUID, user_id: uuid.UUID
    ) -> GuestProfile | None: ...
