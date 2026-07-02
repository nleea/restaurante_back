"""Framework-free domain entities of the Kitchen module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class KitchenStation:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    position: int = 0
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class ProductStation:
    tenant_id: uuid.UUID
    product_id: uuid.UUID
    kitchen_station_id: uuid.UUID
    role: str | None = None
    # Itemized task names this station owes the product (read-only detail on the KDS).
    tasks: list[str] = field(default_factory=list)
    id: uuid.UUID | None = None


@dataclass
class OrderItemStation:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_item_id: uuid.UUID
    kitchen_station_id: uuid.UUID
    status: str = "pending"
    role: str | None = None
    # Frozen copy of the mapping's tasks at fire time (config edits never rewrite tickets).
    tasks: list[str] = field(default_factory=list)
    ready_at: datetime | None = None
    entered_at: datetime | None = None
    id: uuid.UUID | None = None


@dataclass
class KitchenEvent:
    """A ticket change worth pushing to live kitchen screens (KDS boards)."""

    type: str  # "ticket_created" | "ticket_advanced"
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    station_id: uuid.UUID
    ticket_id: uuid.UUID
    status: str
    order_id: uuid.UUID | None = None
