"""Framework-free domain entities for the Cash module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class CashSession:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    opened_by_employee_id: uuid.UUID
    opening_amount: Decimal
    status: str = "open"
    id: uuid.UUID | None = None
    opened_at: datetime | None = None
    closed_by_employee_id: uuid.UUID | None = None
    counted_amount: Decimal | None = None
    expected_amount: Decimal | None = None
    difference: Decimal | None = None
    closed_at: datetime | None = None


@dataclass
class CashMovement:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    cash_session_id: uuid.UUID
    type: str
    concept: str
    amount: Decimal
    method: str
    id: uuid.UUID | None = None
    reference_id: uuid.UUID | None = None
