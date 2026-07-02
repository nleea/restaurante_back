"""Framework-free domain entities of the Staff module.

Plain dataclasses mirroring the ORM models, with no SQLAlchemy dependency.
Each dataclass carries `tenant_id` (and `branch_id` for branch-scoped tables).
Required business fields come first; `id` and server-defaulted fields are
optional so the application layer can build an entity before persistence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal


@dataclass
class Employee:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    person_id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    is_active: bool = True
    id: uuid.UUID | None = None
    hired_at: date | None = None


@dataclass
class PlannedShift:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    employee_id: uuid.UUID
    shift_date: date
    start_time: time
    end_time: time
    id: uuid.UUID | None = None


@dataclass
class Attendance:
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    check_in_at: datetime
    planned_shift_id: uuid.UUID | None = None
    check_out_at: datetime | None = None
    id: uuid.UUID | None = None


@dataclass
class Commission:
    tenant_id: uuid.UUID
    employee_id: uuid.UUID
    type: str
    amount: Decimal
    occurred_at: datetime | None = None
    reference_id: uuid.UUID | None = None
    id: uuid.UUID | None = None
