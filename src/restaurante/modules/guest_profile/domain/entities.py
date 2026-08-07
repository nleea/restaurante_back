"""Domain entity of the Guest Profile module (framework-free dataclass).

Required identity fields come first; ``id`` and server-defaulted timestamps come
last with defaults so the application layer can build an entity before it is
persisted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class GuestProfile:
    """An anonymous storefront customer's saved contact data.

    Identified only by ``token`` (the opaque value stored in the ``guest_token``
    cookie). ``user_id`` stays ``None`` until the guest logs in and the profile
    is claimed/linked to a real account.
    """

    tenant_id: uuid.UUID
    token: uuid.UUID
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    user_id: uuid.UUID | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
