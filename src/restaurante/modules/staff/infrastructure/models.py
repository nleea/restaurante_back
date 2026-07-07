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
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Time,
    UniqueConstraint,
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


class ShiftTemplateModel(Base, BranchScopedMixin, TimestampMixin):
    """Recurring weekly pattern per employee — authors the generated shifts."""

    __tablename__ = "shift_templates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    # 0=Sun..6=Sat; JSON so it is portable across Postgres and the sqlite test DB.
    weekdays: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Horizon watermark: shifts materialized up to this date.
    generated_through: Mapped[date | None] = mapped_column(Date, nullable=True)


class PlannedShiftModel(Base, BranchScopedMixin, TimestampMixin):
    """A scheduled work shift for an employee on a given date.

    `status` and `origin` fold day-off / coverage / manual exceptions onto the
    shift itself. A `(tenant, employee, date)` slot is unique — coverage creates
    a row for a *different* employee, so it never collides.
    """

    __tablename__ = "planned_shifts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "employee_id", "shift_date", name="uq_planned_shift_slot"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), server_default="scheduled", nullable=False
    )
    origin: Mapped[str] = mapped_column(
        String(16), server_default="manual", nullable=False
    )
    covered_by_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)


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


class TimeOffRequestModel(Base, BranchScopedMixin, TimestampMixin):
    """A day-off request with its own approve/reject lifecycle."""

    __tablename__ = "time_off_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), server_default="pending", nullable=False
    )
    # The admin user who decided; loose reference (no FK) like `commissions`.
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)


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
