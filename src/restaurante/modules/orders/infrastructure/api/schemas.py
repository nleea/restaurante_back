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
    # El código impreso en el QR de la mesa. Se devuelve para poder imprimirlo; no se acepta al
    # crear ni al actualizar, porque lo acuña el sistema y no cambia nunca.
    code: str | None = None
    capacity: int
    status: str
    is_active: bool


class TableQrResponse(BaseModel):
    """El QR de una mesa y —a la vista— la dirección que codifica.

    La URL viaja al lado del dibujo a propósito: quien va a mandar esto a imprimir tiene que
    poder leer a dónde apunta sin escanearlo.
    """

    url: str
    svg: str


class TableBillMemberResponse(BaseModel):
    """Un miembro de la cuenta, con lo que el cajero necesita para señalarlo y cobrarlo."""

    order_id: uuid.UUID
    # La etiqueta corta que el mostrador dice en voz alta. Con dos "Ana" en la mesa, es lo que
    # desempata.
    order_label: str
    diner_name: str | None = None
    total: Decimal
    paid: Decimal
    outstanding: Decimal


class TableBillResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    dining_table_id: uuid.UUID
    status: str
    # Cero mientras está abierta: la cuenta NO congela importe, se estampa al liquidar.
    total: Decimal
    members: list[TableBillMemberResponse]
    #: Lo que falta por cubrir AHORA. Cero = se puede liquidar.
    outstanding: Decimal
    closed_at: datetime | None = None


class BillReceiptLine(BaseModel):
    name: str
    quantity: int
    line_subtotal: Decimal


class BillReceiptMember(BaseModel):
    order_id: uuid.UUID
    order_label: str
    diner_name: str | None = None
    total: Decimal
    lines: list[BillReceiptLine]


class BillReceiptResponse(BaseModel):
    """Todo lo que se imprime en la tirilla de una mesa.

    Llega junto desde el servidor y no se compone en el navegador: un papel que se le entrega
    al cliente no puede depender de que el front acierte a juntar seis llamadas.
    """

    bill_id: uuid.UUID
    business_name: str
    #: El NIT. Nulo cuando el negocio no lo ha configurado todavía.
    tax_id: str | None = None
    business_address: str | None = None
    branch_name: str
    table_number: str
    total: Decimal
    methods: list[str]
    members: list[BillReceiptMember]
    closed_at: datetime | None = None
    # La frase la pone el FRONT, no el servidor: es copia de cara al cliente y vive con el
    # resto de los textos. Lo que el servidor garantiza es que aquí no hay CUFE ni resolución,
    # que es lo que convertiría esto en un documento fiscal.
    is_fiscal_invoice: bool = False


class OpenTableBillRequest(BaseModel):
    dining_table_id: uuid.UUID
    employee_id: uuid.UUID
    # Omitido = TODAS las comandas abiertas de la mesa, que es el caso común. Una lista es
    # cobrar por separado, que no es otro camino: es esta misma cuenta con menos miembros.
    order_ids: list[uuid.UUID] | None = None


class BillPaymentEntry(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = Field(min_length=1, max_length=30)


class ChargeTableBillRequest(BaseModel):
    # Varios porque una mesa paga con lo que tenga: parte tarjeta, parte efectivo.
    payments: list[BillPaymentEntry] = Field(min_length=1)
    employee_id: uuid.UUID


class RecordBillReceiptRequest(BaseModel):
    employee_id: uuid.UUID


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
    # Quién pidió y por dónde. `diner_name` sólo lo traen las comandas de mesa por QR; `origin`
    # lo traen todas, y vale `staff` en todo lo que abrió una persona del negocio.
    diner_name: str | None = None
    origin: str = "staff"
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
    # Exactamente uno de los dos: la impresión es de una comanda suelta o de la cuenta de una
    # mesa. Lo garantiza un CHECK en la base además del caso de uso.
    id: uuid.UUID
    order_id: uuid.UUID | None = None
    table_bill_id: uuid.UUID | None = None
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
