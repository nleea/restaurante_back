"""Pydantic schemas for the Orders API."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# --- Responses --------------------------------------------------------------


class DiningTableResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    number: str
    capacity: int
    status: str
    is_active: bool


class OrderResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    channel: str
    employee_id: uuid.UUID
    status: str
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    kitchen_state: str = "none"
    dining_table_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    whatsapp_contact_id: uuid.UUID | None = None
    closed_at: datetime | None = None


class OrderItemResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    product_variant_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    line_subtotal: Decimal
    status: str


class OrderItemAddonResponse(BaseModel):
    id: uuid.UUID
    order_item_id: uuid.UUID
    addon_id: uuid.UUID
    applied_price: Decimal


class CancellationResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    order_item_id: uuid.UUID | None = None
    reason: str
    requires_authorization: bool
    requested_by_employee_id: uuid.UUID
    authorized_by_employee_id: uuid.UUID | None = None
    status: str


class ReceiptPrintResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    employee_id: uuid.UUID
    is_reprint: bool


# --- Requests ---------------------------------------------------------------


class CreateDiningTableRequest(BaseModel):
    branch_id: uuid.UUID
    number: str = Field(min_length=1, max_length=20)
    capacity: int = Field(default=4, gt=0)


class UpdateDiningTableRequest(BaseModel):
    number: str | None = Field(default=None, min_length=1, max_length=20)
    capacity: int | None = Field(default=None, gt=0)
    status: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class OpenOrderRequest(BaseModel):
    branch_id: uuid.UUID
    channel: Literal["dine_in", "takeaway", "delivery"]
    employee_id: uuid.UUID
    dining_table_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    whatsapp_contact_id: uuid.UUID | None = None


class AddItemRequest(BaseModel):
    product_variant_id: uuid.UUID
    quantity: int = Field(default=1, gt=0)
    unit_price: Decimal = Field(ge=0)


class UpdateItemQuantityRequest(BaseModel):
    quantity: int = Field(gt=0)


class AttachAddonRequest(BaseModel):
    addon_id: uuid.UUID
    applied_price: Decimal = Field(ge=0)


class SetDiscountRequest(BaseModel):
    discount: Decimal = Field(ge=0)


class CancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)
    requested_by_employee_id: uuid.UUID
    requires_authorization: bool = False
    authorized_by_employee_id: uuid.UUID | None = None


class RecordReceiptRequest(BaseModel):
    employee_id: uuid.UUID


class RegisterPaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = Field(min_length=1, max_length=30)
    employee_id: uuid.UUID
    diner_reference: str | None = Field(default=None, max_length=50)


class OrderPaymentResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    branch_id: uuid.UUID
    cash_session_id: uuid.UUID
    amount: Decimal
    method: str
    employee_id: uuid.UUID
    diner_reference: str | None = None
