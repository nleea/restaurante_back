"""Pydantic schemas for the Cash API."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# --- Responses --------------------------------------------------------------


class CashSessionResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    opened_by_employee_id: uuid.UUID
    opening_amount: Decimal
    status: str
    opened_at: datetime | None = None
    closed_by_employee_id: uuid.UUID | None = None
    counted_amount: Decimal | None = None
    expected_amount: Decimal | None = None
    difference: Decimal | None = None
    closed_at: datetime | None = None


class CashMovementResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    cash_session_id: uuid.UUID
    type: str
    concept: str
    amount: Decimal
    method: str
    reference_id: uuid.UUID | None = None


# --- Requests ---------------------------------------------------------------


class OpenSessionRequest(BaseModel):
    branch_id: uuid.UUID
    opened_by_employee_id: uuid.UUID
    opening_amount: Decimal = Field(ge=0)


class CloseSessionRequest(BaseModel):
    closed_by_employee_id: uuid.UUID
    counted_amount: Decimal = Field(ge=0)


class RegisterMovementRequest(BaseModel):
    type: Literal["in", "out"]
    concept: str = Field(min_length=1, max_length=50)
    amount: Decimal = Field(gt=0)
    method: str = Field(min_length=1, max_length=30)
    reference_id: uuid.UUID | None = None
