"""Ports (interfaces) of the Audit query module (read-only)."""

from __future__ import annotations

import uuid
from typing import Protocol

from restaurante.modules.audit.domain.entities import AuditLogEntry


class AuditQueryRepository(Protocol):
    async def list_entries(
        self,
        tenant_id: uuid.UUID,
        *,
        action: str | None = None,
        actor_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        limit: int,
        offset: int,
    ) -> list[AuditLogEntry]: ...

    async def get_entry(
        self, tenant_id: uuid.UUID, entry_id: uuid.UUID
    ) -> AuditLogEntry | None: ...
