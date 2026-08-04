"""Pydantic schemas for the Delivery API."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

# A covered-zone name; lists are bounded so route cards stay glanceable.
ZoneName = Annotated[str, Field(min_length=1, max_length=60)]
ZoneList = Annotated[list[ZoneName], Field(max_length=20)]

# --- Responses --------------------------------------------------------------


class RouteResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    zones: list[str] = Field(default_factory=list)
    color: str | None = None
    position: int
    is_active: bool


class RouteDriverResponse(BaseModel):
    id: uuid.UUID
    delivery_route_id: uuid.UUID
    employee_id: uuid.UUID
    is_active: bool
    # Derived at read time: on_route (active run) | available | inactive.
    status: str


class DeliverySettingsResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    ring_step_km: Decimal


class TariffBandResponse(BaseModel):
    id: uuid.UUID
    max_distance_km: Decimal
    fee: Decimal
    position: int


class PaymentRequestResponse(BaseModel):
    order_id: uuid.UUID
    quote_distance_km: Decimal
    quoted_fee: Decimal
    status: str
    expires_at: datetime


class PaymentRequestLineResponse(BaseModel):
    name: str
    quantity: int
    line_subtotal: Decimal


class PaymentRequestViewResponse(BaseModel):
    """Todo lo que la página de pago pinta. Cada cifra viene del servidor.

    Ninguna la suma el navegador: un total calculado en el cliente es un total que puede
    discrepar del que el restaurante va a cobrar, y esa discrepancia se descubre en la puerta.
    """

    order_id: uuid.UUID
    order_code: str
    lines: list[PaymentRequestLineResponse]
    subtotal: Decimal
    discount: Decimal
    delivery_fee: Decimal
    total: Decimal
    amount_due: Decimal
    quote_distance_km: Decimal
    status: str
    expires_at: datetime
    address_text: str | None = None
    payment_method: str | None = None


class PaymentRequestEmissionResponse(BaseModel):
    """Lo que ve el DESPACHADOR tras reemitir, no el cliente.

    Sin token ni URL a propósito: el enlace se manda por WhatsApp y no vuelve por el API.
    Devolverlo aquí lo dejaría en el historial del navegador y en los logs de un empleado, y
    convertiría una pantalla de sólo-despacho en una forma de cobrarle a un cliente por fuera.
    """

    order_id: uuid.UUID
    quoted_fee: Decimal
    expires_at: datetime
    emission_status: str
    emission_failure_reason: str | None = None


class SelectPaymentMethodRequest(BaseModel):
    payment_method: str = Field(min_length=1, max_length=30)


class DeclarePaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = Field(min_length=1, max_length=30)


class TariffBandInput(BaseModel):
    max_distance_km: Decimal = Field(gt=0)
    fee: Decimal = Field(ge=0)


class ReplaceTariffBandsRequest(BaseModel):
    bands: list[TariffBandInput] = Field(min_length=1, max_length=20)


class RunResponse(BaseModel):
    id: uuid.UUID
    delivery_route_id: uuid.UUID
    employee_id: uuid.UUID
    status: str
    departed_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


class DeliveryResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    delivery_route_id: uuid.UUID | None = None
    delivery_run_id: uuid.UUID | None = None
    address_text: str
    neighborhood: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    delivery_status: str
    route_position: int | None = None
    notes: str | None = None
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
    # Derived from the order, not stored on the delivery. Dispatch uses it to show a delivery
    # as blocked with its reason instead of letting the assign fail on the server.
    kitchen_state: str | None = None
    # Whether the customer ever got their payment link. Lives on `delivery_payment_requests`,
    # joined in for the board: a quoted delivery whose message never went out is invisible
    # otherwise, and it is exactly the row someone has to chase.
    emission_status: str | None = None
    emission_failure_reason: str | None = None


# --- Driver self-service (enriched) -----------------------------------------


class OrderLineResponse(BaseModel):
    name: str
    quantity: int


class DriverStopResponse(BaseModel):
    """One stop on the driver's run: the delivery record enriched with its order summary."""

    # Delivery record
    id: uuid.UUID
    order_id: uuid.UUID
    address_text: str
    neighborhood: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    delivery_status: str
    route_position: int | None = None
    notes: str | None = None
    not_delivered_reason: str | None = None
    delivered_at: datetime | None = None
    # Order summary (read-only projection; null when the order could not be read)
    order_code: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    total: Decimal | None = None
    payment_method: str | None = None
    paid: bool | None = None
    items: list[OrderLineResponse] = Field(default_factory=list)


class MyRunResponse(BaseModel):
    id: uuid.UUID
    delivery_route_id: uuid.UUID
    employee_id: uuid.UUID
    status: str
    departed_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    stops: list[DriverStopResponse] = Field(default_factory=list)


# --- Requests ---------------------------------------------------------------


class CreateRouteRequest(BaseModel):
    branch_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    zones: ZoneList = Field(default_factory=list)
    color: str | None = Field(default=None, max_length=7, pattern=r"^#[0-9A-Fa-f]{6}$")


class UpdateRouteRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    zones: ZoneList | None = None
    color: str | None = Field(default=None, max_length=7, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_active: bool | None = None


class UpdateDeliverySettingsRequest(BaseModel):
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    ring_step_km: Decimal | None = Field(default=None)


class AttachRouteDriverRequest(BaseModel):
    employee_id: uuid.UUID


class CreateDeliveryRequest(BaseModel):
    order_id: uuid.UUID
    address_text: str = Field(min_length=1, max_length=255)
    neighborhood: str | None = Field(default=None, max_length=100)
    latitude: Decimal | None = None
    longitude: Decimal | None = None


class UpdateDeliveryAddressRequest(BaseModel):
    address_text: str | None = Field(default=None, min_length=1, max_length=255)
    neighborhood: str | None = Field(default=None, max_length=100)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    notes: str | None = Field(default=None, max_length=500)


class CreateRunRequest(BaseModel):
    delivery_route_id: uuid.UUID
    employee_id: uuid.UUID


class AssignDeliveryRequest(BaseModel):
    delivery_run_id: uuid.UUID


class MarkDeliveredRequest(BaseModel):
    delivered: bool
    # A failure reason (fixed list) + optional free-text comment; recorded only when
    # `delivered` is false. Optional so the dispatcher's existing calls keep working.
    reason: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=400)


class OpenMyRunRequest(BaseModel):
    # Required only when the driver actively drives more than one route.
    delivery_route_id: uuid.UUID | None = None


# --- Live driver positions --------------------------------------------------


class RunLocationRequest(BaseModel):
    """A single GPS fix pushed by the driver for their own active run."""

    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)


class RunPositionResponse(BaseModel):
    """The appended fix echoed back to the driver."""

    run_id: uuid.UUID
    latitude: Decimal
    longitude: Decimal
    recorded_at: datetime


class TrailPointResponse(BaseModel):
    latitude: Decimal
    longitude: Decimal
    recorded_at: datetime


class ActiveDriverPositionResponse(BaseModel):
    """One active run's live driver position + simplified trail for the coverage map."""

    run_id: uuid.UUID
    employee_id: uuid.UUID
    # Current position = the trail's most recent point.
    latitude: Decimal
    longitude: Decimal
    recorded_at: datetime
    trail: list[TrailPointResponse] = Field(default_factory=list)
