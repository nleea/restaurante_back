"""Framework-free domain entities of the messaging module.

Plain dataclasses mirroring the ORM models, with no SQLAlchemy dependency.
Required fields come first; optional fields (defaulting to ``None``) come last.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class WhatsAppContact:
    id: uuid.UUID
    tenant_id: uuid.UUID
    phone: str
    created_at: datetime
    updated_at: datetime
    name: str | None = None
    address: str | None = None


@dataclass
class WhatsAppConversation:
    id: uuid.UUID
    tenant_id: uuid.UUID
    whatsapp_contact_id: uuid.UUID
    status: str
    started_at: datetime
    employee_id: uuid.UUID | None = None
    closed_at: datetime | None = None


@dataclass
class WhatsAppMessage:
    id: uuid.UUID
    tenant_id: uuid.UUID
    whatsapp_conversation_id: uuid.UUID
    sender_type: str
    content: str
    sent_at: datetime
    employee_id: uuid.UUID | None = None
