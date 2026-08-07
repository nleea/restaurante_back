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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import (
    Base,
    BranchScopedMixin,
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
    __table_args__ = (UniqueConstraint("branch_id", name="uq_delivery_settings_branch"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    ring_step_km: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("1.0"), nullable=False
    )


class DeliveryTariffBandModel(Base, BranchScopedMixin):
    """One ordered price band; together a branch's rows are its active tariff plan."""

    __tablename__ = "delivery_tariff_bands"
    __table_args__ = (
        UniqueConstraint("branch_id", "position", name="uq_delivery_tariff_band_position"),
        UniqueConstraint("branch_id", "max_distance_km", name="uq_delivery_tariff_band_max"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    max_distance_km: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class DeliveryRouteDriverModel(Base, BranchScopedMixin):
    """Bridge: which employees (drivers) serve a given delivery route.

    `branch_id` is implied by the route and denormalised here for the project's
    branch-scoping rule; it is always derived from the route, never supplied.
    """

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


class DeliveryRunModel(Base, BranchScopedMixin, TimestampMixin):
    """A dispatch run: a driver leaving with a batch of orders for a route.

    `branch_id` is derived from the route the run serves.
    """

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
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeliveryRunPositionModel(Base, BranchScopedMixin):
    """An append-only GPS fix on a run's live trail (driver's captured position).

    `branch_id` is derived from the run. Rows are pruned when the run finishes — the trail is
    operational (tied to the active run), never historical.
    """

    __tablename__ = "delivery_run_positions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    delivery_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("delivery_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OrderDeliveryModel(Base, BranchScopedMixin, TimestampMixin):
    """Per-order delivery record: address, geo and explicit delivery status.

    `branch_id` is derived from the order. Not from the route: a pending delivery has no
    route yet — the route is set *by* assignment — so the order is the only path.
    """

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
    delivery_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    route_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Failure reason (fixed reason, optionally "reason — comment"); set only when a
    # delivery is marked not_delivered. Kept separate from `notes` (address/handling).
    not_delivered_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quote_status: Mapped[str] = mapped_column(
        String(24), default="pending_quote", server_default="pending_quote", nullable=False
    )
    quote_raw_distance_km: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    quote_buffer_km: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    quote_distance_km: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    quote_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    quoted_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    quoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quote_failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class DeliveryPaymentRequestModel(Base, BranchScopedMixin):
    __tablename__ = "delivery_payment_requests"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_delivery_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("order_deliveries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    quote_distance_km: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    quoted_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Did the link ever reach the customer? Separate from `status` above, which is about whether
    # the link is still usable. See `entities.EMISSION_*`.
    emission_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False
    )
    emitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    emission_failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
