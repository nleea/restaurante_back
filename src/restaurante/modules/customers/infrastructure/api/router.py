"""Customers API: customers (with inline person), preferences, and store credit.

RBAC: reads `customers.read`; all writes `customers.manage`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from restaurante.modules.customers.infrastructure.api.deps import (
    CustomerServiceDep,
    TenantDep,
)
from restaurante.modules.customers.infrastructure.api.schemas import (
    CreateCreditRequest,
    CreateCustomerRequest,
    CreditPaymentRequest,
    CreditPaymentResponse,
    CreditResponse,
    CustomerResponse,
    PreferenceResponse,
    SetPreferenceRequest,
    UpdateCustomerRequest,
)
from restaurante.modules.identity.infrastructure.api.deps import require_permission

router = APIRouter(prefix="/customers", tags=["customers"])

_READ = Depends(require_permission("customers.read"))
_MANAGE = Depends(require_permission("customers.manage"))
_NO_CONTENT = status.HTTP_204_NO_CONTENT


# --- Customers --------------------------------------------------------------
@router.post("", response_model=CustomerResponse, status_code=201, dependencies=[_MANAGE])
async def create_customer(
    payload: CreateCustomerRequest, service: CustomerServiceDep, tenant_id: TenantDep
) -> CustomerResponse:
    customer = await service.create_customer(
        tenant_id,
        payload.first_name,
        payload.last_name,
        document_number=payload.document_number,
        phone=payload.phone,
        email=payload.email,
        user_id=payload.user_id,
    )
    return CustomerResponse.model_validate(customer, from_attributes=True)


@router.get("", response_model=list[CustomerResponse], dependencies=[_READ])
async def list_customers(
    service: CustomerServiceDep, tenant_id: TenantDep, active: bool | None = None
) -> list[CustomerResponse]:
    customers = await service.list_customers(tenant_id, active=active)
    return [CustomerResponse.model_validate(c, from_attributes=True) for c in customers]


@router.get("/{customer_id}", response_model=CustomerResponse, dependencies=[_READ])
async def get_customer(
    customer_id: uuid.UUID, service: CustomerServiceDep, tenant_id: TenantDep
) -> CustomerResponse:
    customer = await service.get_customer(tenant_id, customer_id)
    return CustomerResponse.model_validate(customer, from_attributes=True)


@router.patch(
    "/{customer_id}", response_model=CustomerResponse, dependencies=[_MANAGE]
)
async def update_customer(
    customer_id: uuid.UUID,
    payload: UpdateCustomerRequest,
    service: CustomerServiceDep,
    tenant_id: TenantDep,
) -> CustomerResponse:
    customer = await service.update_customer(
        tenant_id, customer_id, payload.model_dump(exclude_unset=True)
    )
    return CustomerResponse.model_validate(customer, from_attributes=True)


@router.delete(
    "/{customer_id}", response_model=CustomerResponse, dependencies=[_MANAGE]
)
async def deactivate_customer(
    customer_id: uuid.UUID, service: CustomerServiceDep, tenant_id: TenantDep
) -> CustomerResponse:
    customer = await service.deactivate_customer(tenant_id, customer_id)
    return CustomerResponse.model_validate(customer, from_attributes=True)


# --- Preferences ------------------------------------------------------------
@router.post(
    "/{customer_id}/preferences",
    response_model=PreferenceResponse,
    status_code=201,
    dependencies=[_MANAGE],
)
async def set_preference(
    customer_id: uuid.UUID,
    payload: SetPreferenceRequest,
    service: CustomerServiceDep,
    tenant_id: TenantDep,
) -> PreferenceResponse:
    pref = await service.set_preference(
        tenant_id, customer_id, payload.key, payload.value
    )
    return PreferenceResponse.model_validate(pref, from_attributes=True)


@router.get(
    "/{customer_id}/preferences",
    response_model=list[PreferenceResponse],
    dependencies=[_READ],
)
async def list_preferences(
    customer_id: uuid.UUID, service: CustomerServiceDep, tenant_id: TenantDep
) -> list[PreferenceResponse]:
    prefs = await service.list_preferences(tenant_id, customer_id)
    return [PreferenceResponse.model_validate(p, from_attributes=True) for p in prefs]


@router.delete(
    "/preferences/{preference_id}", status_code=_NO_CONTENT, dependencies=[_MANAGE]
)
async def delete_preference(
    preference_id: uuid.UUID, service: CustomerServiceDep, tenant_id: TenantDep
) -> Response:
    await service.delete_preference(tenant_id, preference_id)
    return Response(status_code=_NO_CONTENT)


# --- Credits (fiado) --------------------------------------------------------
@router.post(
    "/{customer_id}/credits",
    response_model=CreditResponse,
    status_code=201,
    dependencies=[_MANAGE],
)
async def register_credit(
    customer_id: uuid.UUID,
    payload: CreateCreditRequest,
    service: CustomerServiceDep,
    tenant_id: TenantDep,
) -> CreditResponse:
    credit = await service.register_credit(
        tenant_id, customer_id, payload.total_amount, payload.reference_id
    )
    return CreditResponse.model_validate(credit, from_attributes=True)


@router.get(
    "/{customer_id}/credits",
    response_model=list[CreditResponse],
    dependencies=[_READ],
)
async def list_credits(
    customer_id: uuid.UUID, service: CustomerServiceDep, tenant_id: TenantDep
) -> list[CreditResponse]:
    credits = await service.list_credits(tenant_id, customer_id)
    return [CreditResponse.model_validate(c, from_attributes=True) for c in credits]


@router.get("/credits/{credit_id}", response_model=CreditResponse, dependencies=[_READ])
async def get_credit(
    credit_id: uuid.UUID, service: CustomerServiceDep, tenant_id: TenantDep
) -> CreditResponse:
    credit = await service.get_credit(tenant_id, credit_id)
    return CreditResponse.model_validate(credit, from_attributes=True)


@router.post(
    "/credits/{credit_id}/payments",
    response_model=CreditPaymentResponse,
    status_code=201,
    dependencies=[_MANAGE],
)
async def register_credit_payment(
    credit_id: uuid.UUID,
    payload: CreditPaymentRequest,
    service: CustomerServiceDep,
    tenant_id: TenantDep,
) -> CreditPaymentResponse:
    payment = await service.register_credit_payment(
        tenant_id, credit_id, payload.amount, payload.method, payload.employee_id
    )
    return CreditPaymentResponse.model_validate(payment, from_attributes=True)


@router.get(
    "/credits/{credit_id}/payments",
    response_model=list[CreditPaymentResponse],
    dependencies=[_READ],
)
async def list_credit_payments(
    credit_id: uuid.UUID, service: CustomerServiceDep, tenant_id: TenantDep
) -> list[CreditPaymentResponse]:
    payments = await service.list_credit_payments(tenant_id, credit_id)
    return [
        CreditPaymentResponse.model_validate(p, from_attributes=True) for p in payments
    ]
