"""Framework-free domain entities of the Orders module.

Plain dataclasses mirroring the ORM tables (no SQLAlchemy imports). Required
fields come first; optional ones (with `| None = None` defaults) come last.
Every entity carries `tenant_id` (and `branch_id` for branch-scoped tables).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class DiningTable:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    number: str
    capacity: int = 4
    status: str = "free"
    is_active: bool = True
    id: uuid.UUID | None = None


@dataclass
class Order:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    channel: str
    employee_id: uuid.UUID
    status: str = "open"
    subtotal: Decimal = Decimal(0)
    discount: Decimal = Decimal(0)
    # Frozen delivery quote. Zero until a delivery is priced (and always zero for non-delivery).
    delivery_fee: Decimal = Decimal(0)
    total: Decimal = Decimal(0)
    kitchen_state: str = "none"
    # Chosen payment method recorded as an intent (nullable; not a received payment).
    payment_method: str | None = None
    id: uuid.UUID | None = None
    dining_table_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    whatsapp_contact_id: uuid.UUID | None = None
    # The cash session open when the order was created — its operating shift. Stamped once at
    # creation; deliveries/kitchen tickets inherit it via the order. Null on pre-boundary rows.
    cash_session_id: uuid.UUID | None = None
    closed_at: datetime | None = None
    # El token con el que el cliente abre su propio pedido para editarlo. Nulo = sin enlace,
    # que es el estado de todo lo anterior a este cambio y de todo lo que no se pide por la
    # carta pública.
    edit_token: str | None = None
    edit_token_expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class OrderItem:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_id: uuid.UUID
    product_variant_id: uuid.UUID
    unit_price: Decimal
    line_subtotal: Decimal
    quantity: int = 1
    status: str = "pending"
    notes: str | None = None
    # Derived read-only flag: the item has ≥1 kitchen ticket (routed / "en cocina").
    sent: bool = False
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class OrderItemAddon:
    tenant_id: uuid.UUID
    order_item_id: uuid.UUID
    addon_id: uuid.UUID
    applied_price: Decimal
    id: uuid.UUID | None = None


@dataclass
class OrderPayment:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_id: uuid.UUID
    cash_session_id: uuid.UUID
    amount: Decimal
    method: str
    employee_id: uuid.UUID
    id: uuid.UUID | None = None
    diner_reference: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class OrderRefund:
    """Plata que le debemos al cliente por un pedido prepagado que no se entregó."""

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_id: uuid.UUID
    amount: Decimal
    # El método por el que ENTRÓ, que es por el que tiene que salir.
    method: str
    status: str = "pending"
    id: uuid.UUID | None = None
    resolved_by_employee_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Enriquecido para la lista del cajero; no es columna.
    customer_name: str | None = None


#: Estados de una declaración de pago. `pending` es el único que espera a una persona.
CLAIM_PENDING = "pending"
CLAIM_ACCEPTED = "accepted"
CLAIM_REJECTED = "rejected"


@dataclass
class OrderPaymentClaim:
    """Lo que el cliente dice haber pagado. Una afirmación, no un pago.

    Vive aparte de `OrderPayment` a propósito: nada de lo que hay aquí suma al total pagado, ni
    abre la cocina, ni cambia el estado del pedido. Sólo la verificación de una persona mueve
    dinero.
    """

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_id: uuid.UUID
    amount: Decimal
    method: str
    status: str = "pending"
    proof_url: str | None = None
    rejection_reason: str | None = None
    id: uuid.UUID | None = None
    resolved_by_employee_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Cancellation:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_id: uuid.UUID
    reason: str
    requires_authorization: bool
    requested_by_employee_id: uuid.UUID
    status: str = "approved"
    id: uuid.UUID | None = None
    order_item_id: uuid.UUID | None = None
    authorized_by_employee_id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ReceiptPrint:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    order_id: uuid.UUID
    employee_id: uuid.UUID
    is_reprint: bool = False
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
