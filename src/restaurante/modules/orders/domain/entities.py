"""Framework-free domain entities of the Orders module.

Plain dataclasses mirroring the ORM tables (no SQLAlchemy imports). Required
fields come first; optional ones (with `| None = None` defaults) come last.
Every entity carries `tenant_id` (and `branch_id` for branch-scoped tables).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class DiningTable:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    number: str
    capacity: int = 4
    status: str = "free"
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class Order:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    channel: str
    employee_id: uuid.UUID
    status: str = "open"
    subtotal: Decimal = Decimal(0)
    discount: Decimal = Decimal(0)
    total: Decimal = Decimal(0)
    kitchen_state: str = "none"
    id: uuid.UUID | None = None
    dining_table_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    whatsapp_contact_id: uuid.UUID | None = None
    closed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class OrderItem:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_id: uuid.UUID
    product_variant_id: uuid.UUID
    unit_price: Decimal
    line_subtotal: Decimal
    quantity: int = 1
    status: str = "pending"
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class OrderItemAddon:
    tenant_id: uuid.UUID
    order_item_id: uuid.UUID
    addon_id: uuid.UUID
    applied_price: Decimal
    id: uuid.UUID | None = None


@dataclass
class OrderPayment:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_id: uuid.UUID
    cash_session_id: uuid.UUID
    amount: Decimal
    method: str
    employee_id: uuid.UUID
    id: uuid.UUID | None = None
    diner_reference: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Cancellation:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_id: uuid.UUID
    reason: str
    requires_authorization: bool
    requested_by_employee_id: uuid.UUID
    status: str = "approved"
    id: uuid.UUID | None = None
    order_item_id: uuid.UUID | None = None
    authorized_by_employee_id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ReceiptPrint:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_id: uuid.UUID
    employee_id: uuid.UUID
    is_reprint: bool = False
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
