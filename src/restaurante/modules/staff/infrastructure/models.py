"""ORM models of the Staff module.

Branch-scoped workforce tables. `employees` and `planned_shifts` carry both
`tenant_id` and `branch_id` (via `BranchScopedMixin`); `attendances` and
`commissions` are tenant-scoped only (they hang off an employee, which already
fixes the branch).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Time,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import (
    Base,
    BranchScopedMixin,
    TenantScopedMixin,
    TimestampMixin,
)


class EmployeeModel(Base, BranchScopedMixin):
    """A person employed at a branch, linked to a login user and a role."""

    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("persons.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
        index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    hired_at: Mapped[date] = mapped_column(
        Date, server_default=func.current_date(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PlannedShiftModel(Base, BranchScopedMixin, TimestampMixin):
    """A scheduled work shift for an employee on a given date."""

    __tablename__ = "planned_shifts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)


class AttendanceModel(Base, TenantScopedMixin, TimestampMixin):
    """Actual clock-in/out of an employee, optionally tied to a planned shift."""

    __tablename__ = "attendances"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    planned_shift_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("planned_shifts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    check_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    check_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CommissionModel(Base, TenantScopedMixin):
    """A commission/extra payment earned by an employee.

    `reference_id` is a loose bridge (no FK) to whatever business event produced
    the commission (e.g. an order), kept decoupled on purpose.
    """

    __tablename__ = "commissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
