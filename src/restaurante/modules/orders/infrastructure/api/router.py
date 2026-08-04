"""Orders API: dining tables + order lifecycle (operational core).

RBAC: reads `orders.read`; opening/adding items `orders.create`; modifying open
orders (items, addons, discount, close, receipts) `orders.update`; cancellations
`orders.cancel`. Payments and inventory deduction are out of scope.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse

from restaurante.modules.identity.infrastructure.api.deps import require_permission
from restaurante.modules.orders.infrastructure.api.deps import (
    EventStreamDep,
    OrderServiceDep,
    PaymentServiceDep,
    TenantDep,
)
from restaurante.modules.orders.infrastructure.api.schemas import (
    AddItemRequest,
    AssignCustomerRequest,
    AttachAddonRequest,
    CancelRefundRequest,
    CancelRequest,
    ConfirmRefundRequest,
    CreateDiningTableRequest,
    DiningTableResponse,
    OpenOrderRequest,
    OrderItemAddonResponse,
    OrderItemResponse,
    OrderPaymentResponse,
    OrderResponse,
    PaymentClaimResponse,
    ReceiptPrintResponse,
    RecordReceiptRequest,
    RefundResponse,
    RegisterPaymentRequest,
    RejectPaymentClaimRequest,
    SetDiscountRequest,
    SetItemNotesRequest,
    UpdateDiningTableRequest,
    UpdateItemQuantityRequest,
    VerifyPaymentRequest,
)
from restaurante.shared.realtime.deps import event_stream_response

router = APIRouter(prefix="/orders", tags=["orders"])
# Propio prefijo: una devolución pertenece a la sucursal y al turno, no a la ruta de un
# pedido — el cajero las lista todas juntas, no pedido por pedido.
refunds_router = APIRouter(prefix="/refunds", tags=["orders"])

_READ = Depends(require_permission("orders.read"))
_CREATE = Depends(require_permission("orders.create"))
_UPDATE = Depends(require_permission("orders.update"))
_CANCEL = Depends(require_permission("orders.cancel"))
_PAY = Depends(require_permission("orders.pay"))
_FINANCE = Depends(require_permission("finance.manage"))
_NO_CONTENT = status.HTTP_204_NO_CONTENT


# --- Live board (SSE) ---------------------------------------------------------
@router.get("/events", dependencies=[_READ])
async def stream_events(
    branch_id: uuid.UUID, stream: EventStreamDep, tenant_id: TenantDep
) -> StreamingResponse:
    """Server-sent events with the branch's Salón changes (heartbeat every ~15 s).

    Orders (created/updated/items/closed/cancelled) and dining-table status changes all
    announce here. Degrades to heartbeats-only when the broker is down, so clients keep the
    connection and fall back to polling for data freshness.
    """
    return event_stream_response(stream, "orders", tenant_id, branch_id)


# --- Dining tables ----------------------------------------------------------
@router.post(
    "/tables", response_model=DiningTableResponse, status_code=201, dependencies=[_CREATE]
)
async def create_table(
    payload: CreateDiningTableRequest, service: OrderServiceDep, tenant_id: TenantDep
) -> DiningTableResponse:
    table = await service.create_dining_table(
        tenant_id, payload.branch_id, payload.number, payload.capacity
    )
    return DiningTableResponse.model_validate(table, from_attributes=True)


@router.get(
    "/tables", response_model=list[DiningTableResponse], dependencies=[_READ]
)
async def list_tables(
    branch_id: uuid.UUID, service: OrderServiceDep, tenant_id: TenantDep
) -> list[DiningTableResponse]:
    tables = await service.list_dining_tables(tenant_id, branch_id)
    return [DiningTableResponse.model_validate(t, from_attributes=True) for t in tables]


@router.patch(
    "/tables/{table_id}", response_model=DiningTableResponse, dependencies=[_UPDATE]
)
async def update_table(
    table_id: uuid.UUID,
    payload: UpdateDiningTableRequest,
    service: OrderServiceDep,
    tenant_id: TenantDep,
) -> DiningTableResponse:
    table = await service.update_dining_table(
        tenant_id, table_id, payload.model_dump(exclude_unset=True)
    )
    return DiningTableResponse.model_validate(table, from_attributes=True)


# --- Orders -----------------------------------------------------------------
@router.post("", response_model=OrderResponse, status_code=201, dependencies=[_CREATE])
async def open_order(
    payload: OpenOrderRequest, service: OrderServiceDep, tenant_id: TenantDep
) -> OrderResponse:
    order = await service.open_order(
        tenant_id,
        payload.branch_id,
        payload.channel,
        payload.employee_id,
        payload.dining_table_id,
        payload.customer_id,
        payload.whatsapp_contact_id,
    )
    return OrderResponse.model_validate(order, from_attributes=True)


@router.get("", response_model=list[OrderResponse], dependencies=[_READ])
async def list_orders(
    service: OrderServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    dining_table_id: uuid.UUID | None = None,
    open_session_only: bool = False,
) -> list[OrderResponse]:
    # `open_session_only=true` is the live salón scope: only the branch's open cash session.
    orders = await service.list_orders(
        tenant_id,
        branch_id=branch_id,
        status=status_filter,
        dining_table_id=dining_table_id,
        open_session_only=open_session_only,
    )
    return [OrderResponse.model_validate(o, from_attributes=True) for o in orders]


@router.get("/{order_id}", response_model=OrderResponse, dependencies=[_READ])
async def get_order(
    order_id: uuid.UUID, service: OrderServiceDep, tenant_id: TenantDep
) -> OrderResponse:
    order = await service.get_order(tenant_id, order_id)
    return OrderResponse.model_validate(order, from_attributes=True)


@router.get(
    "/{order_id}/items",
    response_model=list[OrderItemResponse],
    dependencies=[_READ],
)
async def list_order_items(
    order_id: uuid.UUID, service: OrderServiceDep, tenant_id: TenantDep
) -> list[OrderItemResponse]:
    items = await service.get_order_items(tenant_id, order_id)
    return [OrderItemResponse.model_validate(i, from_attributes=True) for i in items]


@router.post(
    "/{order_id}/cancel", response_model=OrderResponse, dependencies=[_CANCEL]
)
async def cancel_order(
    order_id: uuid.UUID,
    payload: CancelRequest,
    service: OrderServiceDep,
    tenant_id: TenantDep,
) -> OrderResponse:
    order = await service.cancel_order(
        tenant_id,
        order_id,
        payload.reason,
        payload.requested_by_employee_id,
        payload.requires_authorization,
        payload.authorized_by_employee_id,
    )
    return OrderResponse.model_validate(order, from_attributes=True)


@router.post("/{order_id}/close", response_model=OrderResponse, dependencies=[_UPDATE])
async def close_order(
    order_id: uuid.UUID, service: OrderServiceDep, tenant_id: TenantDep
) -> OrderResponse:
    order = await service.close_order(tenant_id, order_id)
    return OrderResponse.model_validate(order, from_attributes=True)


@router.put("/{order_id}/discount", response_model=OrderResponse, dependencies=[_UPDATE])
async def set_discount(
    order_id: uuid.UUID,
    payload: SetDiscountRequest,
    service: OrderServiceDep,
    tenant_id: TenantDep,
) -> OrderResponse:
    order = await service.set_discount(tenant_id, order_id, payload.discount)
    return OrderResponse.model_validate(order, from_attributes=True)


@router.post("/{order_id}/customer", response_model=OrderResponse, dependencies=[_UPDATE])
async def assign_customer(
    order_id: uuid.UUID,
    payload: AssignCustomerRequest,
    service: OrderServiceDep,
    tenant_id: TenantDep,
) -> OrderResponse:
    """Attach a registered customer to an open order (enables fiado at close)."""
    order = await service.assign_customer(tenant_id, order_id, payload.customer_id)
    return OrderResponse.model_validate(order, from_attributes=True)


@router.post(
    "/{order_id}/receipts",
    response_model=ReceiptPrintResponse,
    status_code=201,
    dependencies=[_UPDATE],
)
async def record_receipt(
    order_id: uuid.UUID,
    payload: RecordReceiptRequest,
    service: OrderServiceDep,
    tenant_id: TenantDep,
) -> ReceiptPrintResponse:
    receipt = await service.record_receipt_print(
        tenant_id, order_id, payload.employee_id
    )
    return ReceiptPrintResponse.model_validate(receipt, from_attributes=True)


# --- Payments (orders ↔ cash) -----------------------------------------------
@router.post(
    "/{order_id}/payments",
    response_model=OrderPaymentResponse,
    status_code=201,
    dependencies=[_PAY],
)
async def register_payment(
    order_id: uuid.UUID,
    payload: RegisterPaymentRequest,
    service: PaymentServiceDep,
    tenant_id: TenantDep,
) -> OrderPaymentResponse:
    payment = await service.register_payment(
        tenant_id,
        order_id,
        payload.amount,
        payload.method,
        payload.employee_id,
        payload.diner_reference,
    )
    return OrderPaymentResponse.model_validate(payment, from_attributes=True)


# --- Devoluciones -----------------------------------------------------------
@refunds_router.get("", response_model=list[RefundResponse], dependencies=[_FINANCE])
async def list_refunds(
    branch_id: uuid.UUID,
    service: PaymentServiceDep,
    tenant_id: TenantDep,
    status_filter: str | None = "pending",
) -> list[RefundResponse]:
    refunds = await service.list_refunds(tenant_id, branch_id, status=status_filter)
    return [RefundResponse.model_validate(r, from_attributes=True) for r in refunds]


@refunds_router.post(
    "/{refund_id}/confirm", response_model=RefundResponse, dependencies=[_FINANCE]
)
async def confirm_refund(
    refund_id: uuid.UUID,
    payload: ConfirmRefundRequest,
    service: PaymentServiceDep,
    tenant_id: TenantDep,
) -> RefundResponse:
    """La plata se devolvió: registra la salida de caja con el método original.

    Requiere `finance.manage`: autorizar una devolución es una decisión de plata, no una
    operación de caja.
    """
    refund = await service.confirm_refund(tenant_id, refund_id, payload.employee_id)
    return RefundResponse.model_validate(refund, from_attributes=True)


@refunds_router.post(
    "/{refund_id}/cancel", response_model=RefundResponse, dependencies=[_FINANCE]
)
async def cancel_refund(
    refund_id: uuid.UUID,
    payload: CancelRefundRequest,
    service: PaymentServiceDep,
    tenant_id: TenantDep,
) -> RefundResponse:
    """No se devuelve, se arregló de otra forma. Exige motivo y no mueve un peso."""
    refund = await service.cancel_refund(
        tenant_id, refund_id, payload.employee_id, payload.reason
    )
    return RefundResponse.model_validate(refund, from_attributes=True)


# --- Comprobantes que manda el cliente --------------------------------------
@router.get(
    "/{order_id}/payment-claims",
    response_model=list[PaymentClaimResponse],
    dependencies=[_PAY],
)
async def list_payment_claims(
    order_id: uuid.UUID,
    service: PaymentServiceDep,
    tenant_id: TenantDep,
) -> list[PaymentClaimResponse]:
    """Lo que el cliente dice haber pagado, para que una persona lo mire.

    Bajo `orders.pay` y no `orders.read`: es la pantalla desde la que se decide cobrar, y
    quien no puede cobrar no tiene por qué ver comprobantes bancarios de nadie.
    """
    claims = await service.list_payment_claims(tenant_id, order_id)
    return [
        PaymentClaimResponse.model_validate(c, from_attributes=True) for c in claims
    ]


@router.post(
    "/{order_id}/payment-claims/{claim_id}/reject",
    response_model=PaymentClaimResponse,
    dependencies=[_PAY],
)
async def reject_payment_claim(
    order_id: uuid.UUID,
    claim_id: uuid.UUID,
    payload: RejectPaymentClaimRequest,
    service: PaymentServiceDep,
    tenant_id: TenantDep,
) -> PaymentClaimResponse:
    """El comprobante no sirve. Exige motivo y no mueve un peso.

    Aceptar no tiene endpoint propio a propósito: aceptar ES verificar el pago, y son el mismo
    momento ("llegó, que lo cocinen"). Separarlos crearía el pedido aceptado que nadie cocina.
    """
    claim = await service.reject_payment_claim(
        tenant_id, order_id, claim_id, payload.reason, payload.employee_id
    )
    return PaymentClaimResponse.model_validate(claim, from_attributes=True)


@router.post(
    "/{order_id}/verify-payment",
    response_model=OrderResponse,
    dependencies=[_PAY],
)
async def verify_payment(
    order_id: uuid.UUID,
    payload: VerifyPaymentRequest,
    service: PaymentServiceDep,
    tenant_id: TenantDep,
) -> OrderResponse:
    """Dar por bueno un pago prepagado y mandar el pedido a cocina, en un gesto.

    Requiere `orders.pay`: verificar ES registrar un cobro, solo que mirando un comprobante
    en vez de recibiendo la plata.
    """
    order = await service.verify_payment(tenant_id, order_id, payload.employee_id)
    return OrderResponse.model_validate(order, from_attributes=True)


@router.get(
    "/{order_id}/payments",
    response_model=list[OrderPaymentResponse],
    dependencies=[_READ],
)
async def list_payments(
    order_id: uuid.UUID, service: PaymentServiceDep, tenant_id: TenantDep
) -> list[OrderPaymentResponse]:
    payments = await service.list_payments(tenant_id, order_id)
    return [
        OrderPaymentResponse.model_validate(p, from_attributes=True) for p in payments
    ]


# --- Items ------------------------------------------------------------------
@router.post(
    "/{order_id}/items",
    response_model=OrderItemResponse,
    status_code=201,
    dependencies=[_CREATE],
)
async def add_item(
    order_id: uuid.UUID,
    payload: AddItemRequest,
    service: OrderServiceDep,
    tenant_id: TenantDep,
) -> OrderItemResponse:
    item = await service.add_item(
        tenant_id,
        order_id,
        payload.product_variant_id,
        payload.quantity,
        payload.unit_price,
        payload.notes,
    )
    return OrderItemResponse.model_validate(item, from_attributes=True)


@router.patch(
    "/items/{item_id}", response_model=OrderItemResponse, dependencies=[_UPDATE]
)
async def update_item_quantity(
    item_id: uuid.UUID,
    payload: UpdateItemQuantityRequest,
    service: OrderServiceDep,
    tenant_id: TenantDep,
) -> OrderItemResponse:
    item = await service.update_item_quantity(tenant_id, item_id, payload.quantity)
    return OrderItemResponse.model_validate(item, from_attributes=True)


@router.put(
    "/items/{item_id}/notes", response_model=OrderItemResponse, dependencies=[_UPDATE]
)
async def set_item_notes(
    item_id: uuid.UUID,
    payload: SetItemNotesRequest,
    service: OrderServiceDep,
    tenant_id: TenantDep,
) -> OrderItemResponse:
    item = await service.set_item_notes(tenant_id, item_id, payload.notes)
    return OrderItemResponse.model_validate(item, from_attributes=True)


@router.delete("/items/{item_id}", status_code=_NO_CONTENT, dependencies=[_UPDATE])
async def remove_item(
    item_id: uuid.UUID, service: OrderServiceDep, tenant_id: TenantDep
) -> Response:
    await service.remove_item(tenant_id, item_id)
    return Response(status_code=_NO_CONTENT)


@router.post(
    "/items/{item_id}/cancel", status_code=_NO_CONTENT, dependencies=[_CANCEL]
)
async def cancel_item(
    item_id: uuid.UUID,
    payload: CancelRequest,
    service: OrderServiceDep,
    tenant_id: TenantDep,
) -> Response:
    await service.cancel_item(
        tenant_id,
        item_id,
        payload.reason,
        payload.requested_by_employee_id,
        payload.requires_authorization,
        payload.authorized_by_employee_id,
    )
    return Response(status_code=_NO_CONTENT)


# --- Item addons ------------------------------------------------------------
@router.post(
    "/items/{item_id}/addons",
    response_model=OrderItemAddonResponse,
    status_code=201,
    dependencies=[_UPDATE],
)
async def attach_addon(
    item_id: uuid.UUID,
    payload: AttachAddonRequest,
    service: OrderServiceDep,
    tenant_id: TenantDep,
) -> OrderItemAddonResponse:
    addon = await service.attach_addon(
        tenant_id, item_id, payload.addon_id, payload.applied_price
    )
    return OrderItemAddonResponse.model_validate(addon, from_attributes=True)


@router.get(
    "/items/{item_id}/addons",
    response_model=list[OrderItemAddonResponse],
    dependencies=[_READ],
)
async def list_item_addons(
    item_id: uuid.UUID, service: OrderServiceDep, tenant_id: TenantDep
) -> list[OrderItemAddonResponse]:
    addons = await service.list_item_addons(tenant_id, item_id)
    return [
        OrderItemAddonResponse.model_validate(a, from_attributes=True) for a in addons
    ]


@router.delete(
    "/items/{item_id}/addons/{item_addon_id}",
    status_code=_NO_CONTENT,
    dependencies=[_UPDATE],
)
async def detach_addon(
    item_id: uuid.UUID,
    item_addon_id: uuid.UUID,
    service: OrderServiceDep,
    tenant_id: TenantDep,
) -> Response:
    await service.detach_addon(tenant_id, item_id, item_addon_id)
    return Response(status_code=_NO_CONTENT)
