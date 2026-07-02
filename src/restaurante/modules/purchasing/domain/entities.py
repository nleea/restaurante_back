"""Framework-free domain entities of the Purchasing module.

Plain dataclasses mirroring the ORM tables, free of any SQLAlchemy dependency.
Each carries `tenant_id` (and `branch_id` for branch-scoped entities). Required
business fields come first; `id`, server-defaulted timestamps and other optional
fields come last.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class Supplier:
    tenant_id: uuid.UUID
    name: str
    is_active: bool = True
    tax_id: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class SupplierIngredient:
    tenant_id: uuid.UUID
    supplier_id: uuid.UUID
    ingredient_id: uuid.UUID
    reference_price: Decimal
    unit_of_measure_id: uuid.UUID
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class PurchaseRequest:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    requested_by_employee_id: uuid.UUID
    status: str = "pending"
    reason: str | None = None
    approved_by_employee_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PurchaseRequestItem:
    tenant_id: uuid.UUID
    purchase_request_id: uuid.UUID
    ingredient_id: uuid.UUID
    requested_quantity: Decimal
    unit_of_measure_id: uuid.UUID
    id: uuid.UUID | None = None


@dataclass
class PurchaseOrder:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    purchase_request_id: uuid.UUID
    supplier_id: uuid.UUID
    status: str = "created"
    payment_status: str = "pending"
    total: Decimal = Decimal(0)
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PurchaseOrderItem:
    tenant_id: uuid.UUID
    purchase_order_id: uuid.UUID
    ingredient_id: uuid.UUID
    ordered_quantity: Decimal
    unit_price: Decimal
    unit_of_measure_id: uuid.UUID
    received_quantity: Decimal = Decimal(0)
    id: uuid.UUID | None = None


@dataclass
class PurchasePayment:
    tenant_id: uuid.UUID
    purchase_order_id: uuid.UUID
    amount: Decimal
    method: str
    employee_id: uuid.UUID
    id: uuid.UUID | None = None
    paid_at: datetime | None = None
