"""Pydantic schemas for the Purchasing API."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# --- Responses --------------------------------------------------------------


class SupplierResponse(BaseModel):
    id: uuid.UUID
    name: str
    tax_id: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    is_active: bool


class SupplierIngredientResponse(BaseModel):
    id: uuid.UUID
    supplier_id: uuid.UUID
    ingredient_id: uuid.UUID
    reference_price: Decimal
    unit_of_measure_id: uuid.UUID
    is_active: bool


class PurchaseRequestResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    requested_by_employee_id: uuid.UUID
    status: str
    reason: str | None = None
    approved_by_employee_id: uuid.UUID | None = None
    resolved_at: datetime | None = None


class PurchaseRequestItemResponse(BaseModel):
    id: uuid.UUID
    purchase_request_id: uuid.UUID
    ingredient_id: uuid.UUID
    requested_quantity: Decimal
    unit_of_measure_id: uuid.UUID


class PurchaseOrderResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    purchase_request_id: uuid.UUID
    supplier_id: uuid.UUID
    status: str
    payment_status: str
    total: Decimal


class PurchaseOrderItemResponse(BaseModel):
    id: uuid.UUID
    purchase_order_id: uuid.UUID
    ingredient_id: uuid.UUID
    ordered_quantity: Decimal
    received_quantity: Decimal
    unit_price: Decimal
    unit_of_measure_id: uuid.UUID


class PurchasePaymentResponse(BaseModel):
    id: uuid.UUID
    purchase_order_id: uuid.UUID
    amount: Decimal
    method: str
    employee_id: uuid.UUID


# --- Requests ---------------------------------------------------------------


class CreateSupplierRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    tax_id: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=150)
    address: str | None = Field(default=None, max_length=255)


class UpdateSupplierRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    tax_id: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=150)
    address: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class AttachSupplierIngredientRequest(BaseModel):
    ingredient_id: uuid.UUID
    reference_price: Decimal = Field(ge=0)
    unit_of_measure_id: uuid.UUID


class RequestItemInput(BaseModel):
    ingredient_id: uuid.UUID
    requested_quantity: Decimal = Field(gt=0)
    unit_of_measure_id: uuid.UUID


class CreateRequestRequest(BaseModel):
    branch_id: uuid.UUID
    requested_by_employee_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=255)
    items: list[RequestItemInput] = Field(min_length=1)


class ResolveRequestRequest(BaseModel):
    employee_id: uuid.UUID


class OrderItemInput(BaseModel):
    ingredient_id: uuid.UUID
    ordered_quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    unit_of_measure_id: uuid.UUID


class CreateOrderRequest(BaseModel):
    purchase_request_id: uuid.UUID
    supplier_id: uuid.UUID
    items: list[OrderItemInput] = Field(min_length=1)


class ReceiptItemInput(BaseModel):
    order_item_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class ReceiveRequest(BaseModel):
    received_by_employee_id: uuid.UUID
    items: list[ReceiptItemInput] = Field(min_length=1)


class RegisterPaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = Field(min_length=1, max_length=30)
    employee_id: uuid.UUID
