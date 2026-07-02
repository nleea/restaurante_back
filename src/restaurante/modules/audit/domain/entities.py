"""Framework-free domain entity of the Audit query module.

Read model mirroring the cross-cutting `shared.audit.models.AuditLogModel`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AuditLogEntry:
    tenant_id: uuid.UUID
    action: str
    actor_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    ip: str | None = None
    detail: str | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
