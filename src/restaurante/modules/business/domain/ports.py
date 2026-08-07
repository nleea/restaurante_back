"""Ports (interfaces) of the Business module."""

from __future__ import annotations

import uuid
from typing import Protocol

from restaurante.modules.business.domain.entities import (
    BusinessProfile,
    OperatingHours,
)


class BusinessRepository(Protocol):
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    async def list_hours(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[OperatingHours]: ...

    async def replace_hours(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, hours: list[OperatingHours]
    ) -> list[OperatingHours]: ...

    async def primary_branch_id(self, tenant_id: uuid.UUID) -> uuid.UUID | None: ...

    async def get_profile(self, tenant_id: uuid.UUID) -> BusinessProfile: ...

    async def update_tenant_identity(
        self,
        tenant_id: uuid.UUID,
        *,
        name: str,
        tax_id: str | None,
        email: str | None,
        phone: str | None,
    ) -> None: ...

    async def update_branch_details(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        address: str | None,
        phone: str | None,
        name: str | None = None,
    ) -> bool: ...
