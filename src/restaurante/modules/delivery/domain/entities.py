"""Framework-free domain entities of the Delivery module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class DeliveryRoute:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    zones: list[str] = field(default_factory=list)
    # Ring color on the coverage map (hex); None falls back to the frontend palette.
    color: str | None = None
    # Ring band order around the business (0 = innermost).
    position: int = 0
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class DeliverySetting:
    """Per-branch coverage-map config; null coordinates = pin not placed yet."""

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    ring_step_km: Decimal = Decimal("1.0")
    id: uuid.UUID | None = None


@dataclass
class DeliveryRouteDriver:
    tenant_id: uuid.UUID
    delivery_route_id: uuid.UUID
    employee_id: uuid.UUID
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class DeliveryRun:
    tenant_id: uuid.UUID
    delivery_route_id: uuid.UUID
    employee_id: uuid.UUID
    status: str = "preparing"
    departed_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: uuid.UUID | None = None


@dataclass
class OrderDelivery:
    tenant_id: uuid.UUID
    order_id: uuid.UUID
    address_text: str
    delivery_route_id: uuid.UUID | None = None
    delivery_run_id: uuid.UUID | None = None
    neighborhood: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    delivery_status: str = "pending"
    route_position: int | None = None
    delivered_at: datetime | None = None
    id: uuid.UUID | None = None
