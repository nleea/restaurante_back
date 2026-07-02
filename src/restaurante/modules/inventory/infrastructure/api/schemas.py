"""Pydantic schemas for the Inventory API."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# --- Responses --------------------------------------------------------------


class StockResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    ingredient_id: uuid.UUID
    current_quantity: Decimal
    min_stock: Decimal
    updated_at: datetime | None = None


class MovementResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    ingredient_id: uuid.UUID
    type: str
    reason: str
    quantity: Decimal
    employee_id: uuid.UUID
    reference_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime | None = None


# --- Requests ---------------------------------------------------------------


class SetMinStockRequest(BaseModel):
    ingredient_id: uuid.UUID
    min_stock: Decimal = Field(ge=0)


class RegisterMovementRequest(BaseModel):
    ingredient_id: uuid.UUID
    employee_id: uuid.UUID
    type: Literal["in", "out"]
    quantity: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=50)
    reference_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=255)


class RecountRequest(BaseModel):
    ingredient_id: uuid.UUID
    employee_id: uuid.UUID
    counted_quantity: Decimal = Field(ge=0)
    reason: str = Field(default="count", min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=255)
