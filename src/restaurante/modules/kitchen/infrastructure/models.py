"""ORM models of the Kitchen module (kitchen display system / KDS)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import (
    Base,
    BranchScopedMixin,
    TenantScopedMixin,
)


class KitchenStationModel(Base, BranchScopedMixin):
    __tablename__ = "kitchen_stations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProductStationModel(Base, TenantScopedMixin):
    """Bridge: which kitchen station(s) prepare a given product."""

    __tablename__ = "product_stations"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "kitchen_station_id",
            name="uq_product_stations_product_station",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kitchen_station_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("kitchen_stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Itemized task names the station owes this product ("Carne", "Tocineta ahumada").
    # Read-only detail on the KDS; status stays per station-ticket.
    tasks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class OrderItemStationModel(Base, BranchScopedMixin):
    """Per-order-item routing to a station with its KDS lifecycle state."""

    __tablename__ = "order_item_stations"
    __table_args__ = (
        # Routing idempotency is enforced by the database, not just the app-level
        # check-then-insert: concurrent routes of the same order converge on one ticket.
        UniqueConstraint(
            "order_item_id",
            "kitchen_station_id",
            name="uq_order_item_stations_item_station",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("order_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kitchen_station_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("kitchen_stations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    role: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Denormalized from the mapping's tasks at routing time; frozen for the ticket's life.
    tasks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
