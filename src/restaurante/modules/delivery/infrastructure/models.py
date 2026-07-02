"""ORM models of the Delivery module (own fleet, no external apps)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import (
    Base,
    BranchScopedMixin,
    TenantScopedMixin,
    TimestampMixin,
)


class DeliveryRouteModel(Base, BranchScopedMixin):
    __tablename__ = "delivery_routes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Zone names the route covers (display/chips, not geo shapes). JSON string array.
    zones: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Ring color on the coverage map (hex); null falls back to the frontend palette.
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # Ring band order around the business: band = [position·step, (position+1)·step] km.
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DeliverySettingModel(Base, BranchScopedMixin):
    """Per-branch delivery map config: business location (ring center) + uniform band width.

    Coordinates are nullable — a branch without them is in the "place your pin" onboarding
    state and the coverage map draws no rings.
    """

    __tablename__ = "delivery_settings"
    __table_args__ = (
        UniqueConstraint("branch_id", name="uq_delivery_settings_branch"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    ring_step_km: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("1.0"), nullable=False
    )


class DeliveryRouteDriverModel(Base, TenantScopedMixin):
    """Bridge: which employees (drivers) serve a given delivery route."""

    __tablename__ = "delivery_route_drivers"
    __table_args__ = (
        UniqueConstraint(
            "delivery_route_id",
            "employee_id",
            name="uq_delivery_route_drivers_route_employee",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    delivery_route_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("delivery_routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DeliveryRunModel(Base, TenantScopedMixin, TimestampMixin):
    """A dispatch run: a driver leaving with a batch of orders for a route."""

    __tablename__ = "delivery_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    delivery_route_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("delivery_routes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="preparing", nullable=False)
    departed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OrderDeliveryModel(Base, TenantScopedMixin):
    """Per-order delivery record: address, geo and explicit delivery status."""

    __tablename__ = "order_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    delivery_route_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("delivery_routes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    delivery_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("delivery_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    address_text: Mapped[str] = mapped_column(String(255), nullable=False)
    neighborhood: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    delivery_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    route_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
