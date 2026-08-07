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
    # El código impreso en la calcomanía del QR (ver `domain/table_code.py`). Nulo sólo mientras
    # la mesa no se ha guardado: lo acuña el repositorio al crearla, y no cambia nunca más —ni
    # siquiera si renumeran el salón, porque el número es del negocio y el código es del papel.
    code: str | None = None


@dataclass
class TableBill:
    """La cuenta de una mesa: agrupa comandas para cobrarlas en un gesto.

    NO es una primitiva de dinero. No guarda saldo y no afirma nada sobre pagos: la única
    verdad de si una comanda está pagada sigue siendo `order_payments`. Un agrupador no puede
    desincronizarse de nada porque no afirma nada.

    `total` se estampa al liquidar, no al abrir: entre abrir la cuenta y cobrar, un comensal
    puede pedir un café.
    """

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    dining_table_id: uuid.UUID
    opened_by_employee_id: uuid.UUID
    status: str = "open"
    total: Decimal = Decimal(0)
    id: uuid.UUID | None = None
    closed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    # De dónde vino la comanda: `staff`, `web` o `qr`. `channel` no alcanza — un `dine_in` que
    # abre el mesero y uno que abre el cliente escaneando el QR de su mesa son idénticos por
    # canal y por empleado. Se fija al crear y no se edita: describe cómo nació el pedido, y
    # reescribirlo después haría que el Salón y los reportes mintieran sobre el pasado.
    origin: str = "staff"
    id: uuid.UUID | None = None
    dining_table_id: uuid.UUID | None = None
    # El nombre de pila de quien pidió por el QR. No es un cliente: no crea `customers` ni exige
    # teléfono. Existe para que el cajero pueda señalar la comanda de Luis al partir la cuenta.
    diner_name: str | None = None
    customer_id: uuid.UUID | None = None
    # La cuenta de mesa que la cobró (o la está cobrando). Se conserva tras liquidar como
    # rastro de qué cobro la cerró.
    table_bill_id: uuid.UUID | None = None
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
    # Exactamente uno de `order_id` / `table_bill_id`: una impresión es de UNA comanda suelta
    # o de la cuenta de una mesa. Lo garantiza un CHECK en la base además del caso de uso.
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    employee_id: uuid.UUID
    order_id: uuid.UUID | None = None
    table_bill_id: uuid.UUID | None = None
    is_reprint: bool = False
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
