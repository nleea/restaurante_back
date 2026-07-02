"""ORM models of the Cash module.

`cash_sessions` (branch-scoped) holds the open/close lifecycle of a cash register;
`cash_movements` (branch-scoped + timestamped) records individual cash entries that
belong to a session. The `employee_id` FKs target a table owned by another module,
so they are referenced by string ("employees.id"). `reference_id` is a loose bridge
to another entity (e.g. an order or expense) and intentionally has NO FK constraint.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import Base, BranchScopedMixin, TimestampMixin


class CashSessionModel(Base, BranchScopedMixin):
    __tablename__ = "cash_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opened_by_employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    closed_by_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    opening_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    counted_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    expected_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    difference: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CashMovementModel(Base, BranchScopedMixin, TimestampMixin):
    __tablename__ = "cash_movements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cash_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cash_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    concept: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    # Loose bridge to another entity (order, expense, ...). No FK on purpose.
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
