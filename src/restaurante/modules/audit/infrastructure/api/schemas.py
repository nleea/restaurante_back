"""Pydantic schemas for the Audit query API (read-only)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogEntryResponse(BaseModel):
    id: uuid.UUID
    action: str
    actor_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    ip: str | None = None
    detail: str | None = None
    created_at: datetime | None = None
