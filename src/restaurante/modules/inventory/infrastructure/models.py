"""ORM models of the Inventory module.

Both tables are branch-scoped (`BranchScopedMixin` adds `tenant_id` + `branch_id`
and enables the automatic tenancy filter).

`ingredient_id`/`employee_id` reference tables owned by other modules, so the
foreign keys are declared by table name (string). `reference_id` is a loose
bridge (e.g. to an order/movement source) and intentionally carries no FK.
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
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import Base, BranchScopedMixin, TimestampMixin


class InventoryStockModel(Base, BranchScopedMixin):
    """Current on-hand quantity of an ingredient at a branch."""

    __tablename__ = "inventory_stocks"
    __table_args__ = (
        UniqueConstraint(
            "ingredient_id",
            "branch_id",
            name="uq_inventory_stocks_ingredient_branch",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ingredients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    current_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), default=0, nullable=False
    )
    min_stock: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), default=0, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class InventoryMovementModel(Base, BranchScopedMixin, TimestampMixin):
    """Audit log of every change applied to an ingredient's stock."""

    __tablename__ = "inventory_movements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ingredients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
