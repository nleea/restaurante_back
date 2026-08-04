"""Framework-free domain entities of the Delivery module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

# The emission vocabulary lives in the shared customer-channel port, not here: delivery writes
# these down, messaging produces them, and neither module should have to import the other.
from restaurante.shared.customer_channel.ports import EMISSION_PENDING

# --- Estados de una entrega ---------------------------------------------------------------
# Viven en el DOMINIO y no en el servicio porque no son sólo de delivery: la caja no puede
# cerrar con entregas sin resolver y el histórico de sesión las separa igual. Antes esta lista
# estaba copiada en tres sitios, y añadir un estado sin tocar los tres dejaba el bloqueo puesto
# con un síntoma idéntico al bug que se estaba arreglando.
DELIVERY_PENDING = "pending"
DELIVERY_ASSIGNED = "assigned"
DELIVERY_IN_TRANSIT = "in_transit"
DELIVERY_DELIVERED = "delivered"
DELIVERY_NOT_DELIVERED = "not_delivered"
# Su comanda se canceló y nunca salió del local. Estado propio y NO un `not_delivered` con otro
# nombre: `not_delivered` alimenta las cifras de entregas fallidas, y contar ahí una cancelación
# inventa un fracaso que no ocurrió — nadie salió a entregar nada.
DELIVERY_CANCELLED = "cancelled"

#: Una entrega resuelta: ya tiene desenlace y no le pide nada a nadie. **La** definición.
#: Todo lo que pregunte "¿está resuelta?" deriva de aquí — el guard de cierre de caja, el
#: resumen de pendientes y el histórico de sesión incluidos.
DELIVERY_TERMINAL_STATUSES: tuple[str, ...] = (
    DELIVERY_DELIVERED,
    DELIVERY_NOT_DELIVERED,
    DELIVERY_CANCELLED,
)

#: Lo contrario, derivado y no escrito a mano: sigue debiendo un desenlace. Esto es lo que
#: bloquea el cierre de una sesión de caja.
DELIVERY_UNRESOLVED_STATUSES: tuple[str, ...] = (
    DELIVERY_PENDING,
    DELIVERY_ASSIGNED,
    DELIVERY_IN_TRANSIT,
)


@dataclass
class DeliveryRoute:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    zones: list[str] = field(default_factory=list)
    # Ring color on the coverage map (hex); None falls back to the frontend palette.
    color: str | None = None
    # Ring band order around the business (0 = innermost).
    position: int = 0
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class DeliverySetting:
    """Per-branch coverage-map config; null coordinates = pin not placed yet."""

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    ring_step_km: Decimal = Decimal("1.0")
    id: uuid.UUID | None = None


@dataclass
class DeliveryTariffBand:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    max_distance_km: Decimal
    fee: Decimal
    position: int
    id: uuid.UUID | None = None


@dataclass
class DeliveryRouteDriver:
    tenant_id: uuid.UUID
    # Implied by the route; denormalised for branch scoping, always derived from it.
    branch_id: uuid.UUID
    delivery_route_id: uuid.UUID
    employee_id: uuid.UUID
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class DeliveryRun:
    tenant_id: uuid.UUID
    # Derived from the route the run serves.
    branch_id: uuid.UUID
    delivery_route_id: uuid.UUID
    employee_id: uuid.UUID
    status: str = "preparing"
    departed_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: uuid.UUID | None = None


@dataclass
class RunPosition:
    """One timestamped GPS fix on a run's append-only position trail.

    Captured by the owning driver while the run is active; the whole ordered set is the
    trail and the most recent `recorded_at` is the driver's current position. Pruned when
    the run finishes.
    """

    tenant_id: uuid.UUID
    # Derived from the run the position belongs to; carried for branch scoping.
    branch_id: uuid.UUID
    delivery_run_id: uuid.UUID
    latitude: Decimal
    longitude: Decimal
    recorded_at: datetime | None = None
    id: uuid.UUID | None = None


@dataclass
class ActiveRunTrail:
    """An active run's driver trail for the dispatcher read: who, and the ordered path.

    `trail` is ordered by `recorded_at` (oldest first); its last element is the current
    position. Simplified with Douglas–Peucker before it leaves the service.
    """

    run_id: uuid.UUID
    employee_id: uuid.UUID
    trail: list[RunPosition] = field(default_factory=list)


@dataclass
class GeoResult:
    """An approximate location resolved from a written address by the geocoder."""

    latitude: Decimal
    longitude: Decimal
    neighborhood: str | None = None
    display_name: str = ""


@dataclass(frozen=True)
class DistanceEstimate:
    """Distance used by a delivery quote, with enough context to audit it later."""

    raw_km: Decimal
    buffer_km: Decimal
    adjusted_km: Decimal
    method: str


@dataclass(frozen=True)
class PaymentRequestLine:
    """One line as the CUSTOMER reads it on the payment page — with its money.

    Deliberately not `OrderLine`: that one is the driver's, and carries no prices on purpose
    (nobody negotiates at the doorstep). Here the price is the whole point — the customer is
    being asked to pay a number, and a number they cannot break down is a number they argue
    about.
    """

    name: str
    quantity: int
    line_subtotal: Decimal


@dataclass(frozen=True)
class PaymentRequestView:
    """Everything the payment page shows: the order, its money, and where it is going.

    Assembled server-side because every figure here is authoritative. The page must never add
    anything up itself — a total computed in a browser is a total that can disagree with the
    one the restaurant will collect.
    """

    order_id: uuid.UUID
    order_code: str
    lines: list[PaymentRequestLine]
    subtotal: Decimal
    discount: Decimal
    delivery_fee: Decimal
    total: Decimal
    # Lo que falta por pagar AHORA. Normalmente el total; menos si ya se abonó algo.
    amount_due: Decimal
    quote_distance_km: Decimal
    status: str
    expires_at: datetime
    address_text: str | None = None
    payment_method: str | None = None


@dataclass
class DeliveryPaymentRequest:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_id: uuid.UUID
    order_delivery_id: uuid.UUID
    token_hash: str
    quote_distance_km: Decimal
    quoted_fee: Decimal
    expires_at: datetime
    status: str = "pending"
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    # Whether the customer was ever handed this link. `pending` only survives a crash between
    # creating the request and recording its emission — the emitter writes one of the others
    # in the same pass, because the raw token dies with it.
    emission_status: str = EMISSION_PENDING
    emitted_at: datetime | None = None
    emission_failure_reason: str | None = None
    # Transient: returned only to the emitter; never persisted. This is the ONLY moment the
    # link is readable — only `token_hash` reaches the database — which is why emission happens
    # inside the creating pass and recovery means re-issuing, never resending.
    raw_token: str | None = None


@dataclass
class OrderDelivery:
    tenant_id: uuid.UUID
    # Derived from the order. Not from the route: a pending delivery has no route yet.
    branch_id: uuid.UUID
    order_id: uuid.UUID
    address_text: str
    delivery_route_id: uuid.UUID | None = None
    delivery_run_id: uuid.UUID | None = None
    neighborhood: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    delivery_status: str = "pending"
    route_position: int | None = None
    notes: str | None = None
    # Why a delivery failed, persisted only on a `not_delivered` outcome. Stored as the
    # fixed reason, optionally joined to a free-text comment as "reason — comment".
    not_delivered_reason: str | None = None
    delivered_at: datetime | None = None
    quote_status: str = "pending_quote"
    quote_raw_distance_km: Decimal | None = None
    quote_buffer_km: Decimal | None = None
    quote_distance_km: Decimal | None = None
    quote_method: str | None = None
    quoted_fee: Decimal | None = None
    quoted_at: datetime | None = None
    quote_failure_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: uuid.UUID | None = None
    # NOT a column: read from the order every time. A delivery may only be assigned once its
    # order is cooked, and storing that here would be the same fact in two places — a delivery
    # marked "waiting for the kitchen" after the kitchen finished is exactly the bug this
    # guards against, reintroduced by another door. `None` means "not looked up".
    kitchen_state: str | None = None


@dataclass
class OrderLine:
    """One line of an order, as the driver needs it at the doorstep (no prices)."""

    name: str
    quantity: int


@dataclass
class OrderSummary:
    """Read-only projection of an order for the driver's enriched stop.

    Built by a batched read across the orders module; carries no write coupling and
    introduces no new FK. `code` is a short, human-glanceable label derived from the
    order id (orders have no dedicated code column).
    """

    order_id: uuid.UUID
    code: str
    total: Decimal
    paid: bool
    items: list[OrderLine] = field(default_factory=list)
    customer_name: str | None = None
    customer_phone: str | None = None
    payment_method: str | None = None
