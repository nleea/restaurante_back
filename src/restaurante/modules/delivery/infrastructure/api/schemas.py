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
    delivered_at: datetime | None = None
    created_at: datetime | None = None


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
