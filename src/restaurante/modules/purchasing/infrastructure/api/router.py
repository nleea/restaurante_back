"""Purchasing API: procure-to-pay (suppliers, requests, orders, receipt, payments).

RBAC: reads `purchasing.read`; configuration/creation/receipt/payments
`purchasing.manage`; approve/reject requests `purchasing.approve`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response

from restaurante.modules.identity.infrastructure.api.deps import require_permission
from restaurante.modules.purchasing.infrastructure.api.deps import (
    PurchasingServiceDep,
    TenantDep,
)
from restaurante.modules.purchasing.infrastructure.api.schemas import (
    AttachSupplierIngredientRequest,
    CreateOrderRequest,
    CreateRequestRequest,
    CreateSupplierRequest,
    PurchaseOrderItemResponse,
    PurchaseOrderResponse,
    PurchasePaymentResponse,
    PurchaseRequestItemResponse,
    PurchaseRequestResponse,
    ReceiveRequest,
    RegisterPaymentRequest,
    ResolveRequestRequest,
    SupplierIngredientResponse,
    SupplierResponse,
    UpdateSupplierRequest,
)

router = APIRouter(prefix="/purchasing", tags=["purchasing"])

_READ = Depends(require_permission("purchasing.read"))
_MANAGE = Depends(require_permission("purchasing.manage"))
_APPROVE = Depends(require_permission("purchasing.approve"))


# --- Suppliers --------------------------------------------------------------
@router.post(
    "/suppliers", response_model=SupplierResponse, status_code=201, dependencies=[_MANAGE]
)
async def create_supplier(
    payload: CreateSupplierRequest, service: PurchasingServiceDep, tenant_id: TenantDep
) -> SupplierResponse:
    supplier = await service.create_supplier(
        tenant_id,
        payload.name,
        payload.tax_id,
        payload.phone,
        payload.email,
        payload.address,
    )
    return SupplierResponse.model_validate(supplier, from_attributes=True)


@router.get("/suppliers", response_model=list[SupplierResponse], dependencies=[_READ])
async def list_suppliers(
    service: PurchasingServiceDep, tenant_id: TenantDep, active: bool | None = None
) -> list[SupplierResponse]:
    suppliers = await service.list_suppliers(tenant_id, active=active)
    return [SupplierResponse.model_validate(s, from_attributes=True) for s in suppliers]


@router.patch(
    "/suppliers/{supplier_id}", response_model=SupplierResponse, dependencies=[_MANAGE]
)
async def update_supplier(
    supplier_id: uuid.UUID,
    payload: UpdateSupplierRequest,
    service: PurchasingServiceDep,
    tenant_id: TenantDep,
) -> SupplierResponse:
    supplier = await service.update_supplier(
        tenant_id, supplier_id, payload.model_dump(exclude_unset=True)
    )
    return SupplierResponse.model_validate(supplier, from_attributes=True)


# --- Supplier ingredients ---------------------------------------------------
@router.post(
    "/suppliers/{supplier_id}/ingredients",
    response_model=SupplierIngredientResponse,
    status_code=201,
    dependencies=[_MANAGE],
)
async def attach_supplier_ingredient(
    supplier_id: uuid.UUID,
    payload: AttachSupplierIngredientRequest,
    service: PurchasingServiceDep,
    tenant_id: TenantDep,
) -> SupplierIngredientResponse:
    mapping = await service.attach_supplier_ingredient(
        tenant_id,
        supplier_id,
        payload.ingredient_id,
        payload.reference_price,
        payload.unit_of_measure_id,
    )
    return SupplierIngredientResponse.model_validate(mapping, from_attributes=True)


@router.get(
    "/suppliers/{supplier_id}/ingredients",
    response_model=list[SupplierIngredientResponse],
    dependencies=[_READ],
)
async def list_supplier_ingredients(
    supplier_id: uuid.UUID, service: PurchasingServiceDep, tenant_id: TenantDep
) -> list[SupplierIngredientResponse]:
    items = await service.list_supplier_ingredients(tenant_id, supplier_id)
    return [
        SupplierIngredientResponse.model_validate(i, from_attributes=True)
        for i in items
    ]


@router.delete(
    "/suppliers/{supplier_id}/ingredients/{ingredient_id}",
    status_code=204,
    dependencies=[_MANAGE],
)
async def detach_supplier_ingredient(
    supplier_id: uuid.UUID,
    ingredient_id: uuid.UUID,
    service: PurchasingServiceDep,
    tenant_id: TenantDep,
) -> Response:
    await service.detach_supplier_ingredient(tenant_id, supplier_id, ingredient_id)
    return Response(status_code=204)


# --- Purchase requests ------------------------------------------------------
@router.post(
    "/requests",
    response_model=PurchaseRequestResponse,
    status_code=201,
    dependencies=[_MANAGE],
)
async def create_request(
    payload: CreateRequestRequest, service: PurchasingServiceDep, tenant_id: TenantDep
) -> PurchaseRequestResponse:
    request = await service.create_request(
        tenant_id,
        payload.branch_id,
        payload.requested_by_employee_id,
        [i.model_dump() for i in payload.items],
        payload.reason,
    )
    return PurchaseRequestResponse.model_validate(request, from_attributes=True)


@router.get(
    "/requests", response_model=list[PurchaseRequestResponse], dependencies=[_READ]
)
async def list_requests(
    service: PurchasingServiceDep, tenant_id: TenantDep, status_filter: str | None = None
) -> list[PurchaseRequestResponse]:
    requests = await service.list_requests(tenant_id, status=status_filter)
    return [
        PurchaseRequestResponse.model_validate(r, from_attributes=True)
        for r in requests
    ]


@router.get(
    "/requests/{request_id}/items",
    response_model=list[PurchaseRequestItemResponse],
    dependencies=[_READ],
)
async def list_request_items(
    request_id: uuid.UUID, service: PurchasingServiceDep, tenant_id: TenantDep
) -> list[PurchaseRequestItemResponse]:
    items = await service.list_request_items(tenant_id, request_id)
    return [
        PurchaseRequestItemResponse.model_validate(i, from_attributes=True)
        for i in items
    ]


@router.post(
    "/requests/{request_id}/approve",
    response_model=PurchaseRequestResponse,
    dependencies=[_APPROVE],
)
async def approve_request(
    request_id: uuid.UUID,
    payload: ResolveRequestRequest,
    service: PurchasingServiceDep,
    tenant_id: TenantDep,
) -> PurchaseRequestResponse:
    request = await service.approve_request(tenant_id, request_id, payload.employee_id)
    return PurchaseRequestResponse.model_validate(request, from_attributes=True)


@router.post(
    "/requests/{request_id}/reject",
    response_model=PurchaseRequestResponse,
    dependencies=[_APPROVE],
)
async def reject_request(
    request_id: uuid.UUID,
    payload: ResolveRequestRequest,
    service: PurchasingServiceDep,
    tenant_id: TenantDep,
) -> PurchaseRequestResponse:
    request = await service.reject_request(tenant_id, request_id, payload.employee_id)
    return PurchaseRequestResponse.model_validate(request, from_attributes=True)


# --- Purchase orders --------------------------------------------------------
@router.post(
    "/orders",
    response_model=PurchaseOrderResponse,
    status_code=201,
    dependencies=[_MANAGE],
)
async def create_order(
    payload: CreateOrderRequest, service: PurchasingServiceDep, tenant_id: TenantDep
) -> PurchaseOrderResponse:
    order = await service.create_order(
        tenant_id,
        payload.purchase_request_id,
        payload.supplier_id,
        [i.model_dump() for i in payload.items],
    )
    return PurchaseOrderResponse.model_validate(order, from_attributes=True)


@router.get(
    "/orders", response_model=list[PurchaseOrderResponse], dependencies=[_READ]
)
async def list_orders(
    service: PurchasingServiceDep, tenant_id: TenantDep, status_filter: str | None = None
) -> list[PurchaseOrderResponse]:
    orders = await service.list_orders(tenant_id, status=status_filter)
    return [PurchaseOrderResponse.model_validate(o, from_attributes=True) for o in orders]


@router.get(
    "/orders/{order_id}/items",
    response_model=list[PurchaseOrderItemResponse],
    dependencies=[_READ],
)
async def list_order_items(
    order_id: uuid.UUID, service: PurchasingServiceDep, tenant_id: TenantDep
) -> list[PurchaseOrderItemResponse]:
    items = await service.list_order_items(tenant_id, order_id)
    return [
        PurchaseOrderItemResponse.model_validate(i, from_attributes=True) for i in items
    ]


@router.post(
    "/orders/{order_id}/receive",
    response_model=PurchaseOrderResponse,
    dependencies=[_MANAGE],
)
async def receive_order(
    order_id: uuid.UUID,
    payload: ReceiveRequest,
    service: PurchasingServiceDep,
    tenant_id: TenantDep,
) -> PurchaseOrderResponse:
    order = await service.receive_items(
        tenant_id,
        order_id,
        [i.model_dump() for i in payload.items],
        payload.received_by_employee_id,
    )
    return PurchaseOrderResponse.model_validate(order, from_attributes=True)


# --- Payments ---------------------------------------------------------------
@router.post(
    "/orders/{order_id}/payments",
    response_model=PurchasePaymentResponse,
    status_code=201,
    dependencies=[_MANAGE],
)
async def register_payment(
    order_id: uuid.UUID,
    payload: RegisterPaymentRequest,
    service: PurchasingServiceDep,
    tenant_id: TenantDep,
) -> PurchasePaymentResponse:
    payment = await service.register_payment(
        tenant_id, order_id, payload.amount, payload.method, payload.employee_id
    )
    return PurchasePaymentResponse.model_validate(payment, from_attributes=True)


@router.get(
    "/orders/{order_id}/payments",
    response_model=list[PurchasePaymentResponse],
    dependencies=[_READ],
)
async def list_payments(
    order_id: uuid.UUID, service: PurchasingServiceDep, tenant_id: TenantDep
) -> list[PurchasePaymentResponse]:
    payments = await service.list_payments(tenant_id, order_id)
    return [
        PurchasePaymentResponse.model_validate(p, from_attributes=True)
        for p in payments
    ]
