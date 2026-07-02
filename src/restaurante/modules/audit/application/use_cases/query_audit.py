"""Application service for the Audit query module (read-only).

Lists and retrieves audit-log entries for the current tenant. Clamps pagination
to a safe maximum; performs no writes (the log is append-only and system-authored).
"""

from __future__ import annotations

import uuid

from restaurante.modules.audit.domain.entities import AuditLogEntry
from restaurante.modules.audit.domain.ports import AuditQueryRepository
from restaurante.shared.domain.errors import NotFoundError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class AuditQueryService:
    def __init__(self, repo: AuditQueryRepository) -> None:
        self._repo = repo

    async def list_entries(
        self,
        tenant_id: uuid.UUID,
        *,
        action: str | None = None,
        actor_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        branch_id: uuid.UUID | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        safe_limit = max(1, min(limit, MAX_LIMIT))
        safe_offset = max(0, offset)
        return await self._repo.list_entries(
            tenant_id,
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            branch_id=branch_id,
            limit=safe_limit,
            offset=safe_offset,
        )

    async def get_entry(
        self, tenant_id: uuid.UUID, entry_id: uuid.UUID
    ) -> AuditLogEntry:
        entry = await self._repo.get_entry(tenant_id, entry_id)
        if entry is None:
            raise NotFoundError(f"Entrada de auditoría no encontrada: {entry_id}")
        return entry
