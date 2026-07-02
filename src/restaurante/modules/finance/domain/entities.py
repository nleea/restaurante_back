"""Framework-free domain entities for the Finance module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class ExpenseCategory:
    tenant_id: uuid.UUID
    name: str
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class Expense:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    expense_category_id: uuid.UUID
    description: str
    amount: Decimal
    employee_id: uuid.UUID
    incurred_at: datetime | None = None
    id: uuid.UUID | None = None
