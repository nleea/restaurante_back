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
    delivery_fee: Decimal
    total: Decimal
    kitchen_state: str = "none"
    payment_method: str | None = None
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
    notes: str | None = None
    # True once the item has been routed to the kitchen (has ≥1 ticket) — pending until then.
    sent: bool = False


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
    notes: str | None = Field(default=None, max_length=255)


class UpdateItemQuantityRequest(BaseModel):
    quantity: int = Field(gt=0)


class SetItemNotesRequest(BaseModel):
    # Explicit null clears the note (the waiter emptied the field).
    notes: str | None = Field(default=None, max_length=255)


class AttachAddonRequest(BaseModel):
    addon_id: uuid.UUID
    applied_price: Decimal = Field(ge=0)


class SetDiscountRequest(BaseModel):
    discount: Decimal = Field(ge=0)


class AssignCustomerRequest(BaseModel):
    customer_id: uuid.UUID


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


class RejectPaymentClaimRequest(BaseModel):
    """El motivo es obligatorio: es lo único que el cliente va a leer.

    "No nos sirve" no le dice si mandar otra foto, corregir la cifra o llamar.
    """

    employee_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=255)


class PaymentClaimResponse(BaseModel):
    """Un comprobante mandado por el cliente. Nunca es un pago: mira `OrderPaymentResponse`."""

    id: uuid.UUID
    order_id: uuid.UUID
    amount: Decimal
    method: str
    proof_url: str | None = None
    status: str
    rejection_reason: str | None = None
    resolved_by_employee_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime | None = None


class VerifyPaymentRequest(BaseModel):
    """No lleva monto ni método: el saldo pendiente y el método salen del propio pedido.

    Verificar no es cobrar una cifra que alguien teclea — es confirmar que llegó lo que el
    pedido decía que iba a llegar. Dejar teclear el monto abriría la puerta a que el
    comprobante y el cobro registrado no coincidan.
    """

    employee_id: uuid.UUID


class RefundResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    branch_id: uuid.UUID
    amount: Decimal
    method: str
    status: str
    resolved_by_employee_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    reason: str | None = None
    created_at: datetime | None = None


class ConfirmRefundRequest(BaseModel):
    employee_id: uuid.UUID


class CancelRefundRequest(BaseModel):
    employee_id: uuid.UUID
    # Obligatorio: decidir NO devolver un dinero cobrado tiene que dejar por qué.
    reason: str = Field(min_length=1, max_length=255)


class OrderPaymentResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    branch_id: uuid.UUID
    cash_session_id: uuid.UUID
    amount: Decimal
    method: str
    employee_id: uuid.UUID
    diner_reference: str | None = None
