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
    notes: str | None = None
    incident: bool = False
    incident_note: str | None = None


class CashMovementResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    cash_session_id: uuid.UUID
    type: str
    concept: str
    amount: Decimal
    method: str
    category: str
    reference_id: uuid.UUID | None = None
    # La cuenta de mesa que produjo el movimiento, si la hubo. Cobrar una mesa deja un
    # movimiento por comanda; esto es lo que deja al feed decir que fueron UN solo cobro.
    table_bill_id: uuid.UUID | None = None
    created_at: datetime


class CashSummaryChannelLine(BaseModel):
    channel: str
    amount: Decimal
    tickets: int


class CashSummaryPaymentLine(BaseModel):
    method: str
    amount: Decimal


class CashShiftSummaryResponse(BaseModel):
    cash_session_id: uuid.UUID
    status: str
    sales_total: Decimal
    tickets: int
    avg_ticket: Decimal
    channels: list[CashSummaryChannelLine]
    payments: list[CashSummaryPaymentLine]
    withdrawals: Decimal
    expected_cash: Decimal


class ShiftPendingSummaryResponse(BaseModel):
    """Advisory pre-close view: unresolved work in a session (never blocks a close)."""

    cash_session_id: uuid.UUID
    uncollected_count: int
    uncollected_total: Decimal
    undelivered_count: int


# --- Requests ---------------------------------------------------------------


class OpenSessionRequest(BaseModel):
    branch_id: uuid.UUID
    opened_by_employee_id: uuid.UUID
    opening_amount: Decimal = Field(ge=0)


class CloseSessionRequest(BaseModel):
    closed_by_employee_id: uuid.UUID
    counted_amount: Decimal = Field(ge=0)
    notes: str | None = None
    incident: bool = False
    incident_note: str | None = None


class RegisterMovementRequest(BaseModel):
    type: Literal["in", "out"]
    concept: str = Field(min_length=1, max_length=50)
    amount: Decimal = Field(gt=0)
    method: str = Field(min_length=1, max_length=30)
    category: Literal["entry", "withdrawal", "expense", "sale", "other"] = "other"
    reference_id: uuid.UUID | None = None
