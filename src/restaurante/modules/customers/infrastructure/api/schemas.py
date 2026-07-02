"""Pydantic schemas for the Customers API."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# --- Responses --------------------------------------------------------------


class CustomerResponse(BaseModel):
    id: uuid.UUID
    person_id: uuid.UUID
    user_id: uuid.UUID | None = None
    total_spent: Decimal
    order_count: int
    last_purchase_at: datetime | None = None
    is_active: bool
    # Person identity, denormalised onto the read so clients need no person lookup.
    first_name: str | None = None
    last_name: str | None = None
    document_number: str | None = None
    phone: str | None = None
    email: str | None = None


class PreferenceResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    key: str
    value: str


class CreditResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    total_amount: Decimal
    payment_status: str
    reference_id: uuid.UUID | None = None


class CreditPaymentResponse(BaseModel):
    id: uuid.UUID
    customer_credit_id: uuid.UUID
    amount: Decimal
    method: str
    employee_id: uuid.UUID


# --- Requests ---------------------------------------------------------------


class CreateCustomerRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    document_number: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=150)
    user_id: uuid.UUID | None = None


class UpdateCustomerRequest(BaseModel):
    user_id: uuid.UUID | None = None
    is_active: bool | None = None


class SetPreferenceRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=255)


class CreateCreditRequest(BaseModel):
    total_amount: Decimal = Field(gt=0)
    reference_id: uuid.UUID | None = None


class CreditPaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = Field(min_length=1, max_length=30)
    employee_id: uuid.UUID
