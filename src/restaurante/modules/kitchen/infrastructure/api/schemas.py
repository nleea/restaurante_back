"""Pydantic schemas for the Kitchen API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

# One itemized station task ("Carne de hamburguesa"); lists are bounded so a docket
# component stays glanceable. The service trims and drops empties.
TaskName = Annotated[str, Field(min_length=1, max_length=60)]
TaskList = Annotated[list[TaskName], Field(max_length=10)]

# --- Responses --------------------------------------------------------------


class KitchenStationResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    position: int
    is_active: bool


class ProductStationResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    kitchen_station_id: uuid.UUID
    role: str | None = None
    tasks: list[str] = Field(default_factory=list)


class TicketResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    order_item_id: uuid.UUID
    kitchen_station_id: uuid.UUID
    status: str
    role: str | None = None
    tasks: list[str] = Field(default_factory=list)
    entered_at: datetime | None = None
    ready_at: datetime | None = None


# --- Requests ---------------------------------------------------------------


class CreateStationRequest(BaseModel):
    branch_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    position: int = Field(default=0, ge=0)


class UpdateStationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    position: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class AttachProductStationRequest(BaseModel):
    product_id: uuid.UUID
    kitchen_station_id: uuid.UUID
    role: str | None = Field(default=None, max_length=60)
    tasks: TaskList = Field(default_factory=list)


class UpdateProductStationRequest(BaseModel):
    role: str | None = Field(default=None, max_length=60)
    tasks: TaskList | None = None
