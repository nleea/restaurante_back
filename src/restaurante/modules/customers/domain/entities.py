"""Domain entities of the Customers module (framework-free dataclasses).

Required business fields come first; `id`, server-defaulted timestamps and stats
come last with defaults so the application layer can build an entity before
persistence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class Customer:
    """A tenant's customer: a person, optionally linked to a login user.

    The person's identity fields (name/document/phone/email) are denormalised
    onto reads so a client can display and search customers without a separate
    person lookup; they stay ``None`` until populated from the backing person.
    """

    tenant_id: uuid.UUID
    person_id: uuid.UUID
    user_id: uuid.UUID | None = None
    is_active: bool = True
    total_spent: Decimal = Decimal(0)
    order_count: int = 0
    last_purchase_at: datetime | None = None
    id: uuid.UUID | None = None
    registered_at: datetime | None = None
    # Denormalised person identity (read-only; sourced from the backing person).
    first_name: str | None = None
    last_name: str | None = None
    document_number: str | None = None
    phone: str | None = None
    email: str | None = None


@dataclass
class CustomerPreference:
    """A free-form key/value preference attached to a customer."""

    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    key: str
    value: str
    id: uuid.UUID | None = None


@dataclass
class CustomerCredit:
    """Store credit (fiado) owed by a customer."""

    tenant_id: uuid.UUID
    customer_id: uuid.UUID
    total_amount: Decimal
    payment_status: str = "pending"
    reference_id: uuid.UUID | None = None
    id: uuid.UUID | None = None


@dataclass
class CustomerCreditPayment:
    """A payment that settles part or all of a customer credit."""

    tenant_id: uuid.UUID
    customer_credit_id: uuid.UUID
    amount: Decimal
    method: str
    employee_id: uuid.UUID
    id: uuid.UUID | None = None
    paid_at: datetime | None = None
