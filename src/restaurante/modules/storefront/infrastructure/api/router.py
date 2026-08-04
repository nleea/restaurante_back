"""Public Storefront API: appearance, menu read-model and order intake.

Unauthenticated by design — a customer is not logged in. Every endpoint is scoped to
the subdomain tenant via ``TenantDep`` only (the ``/auth/login`` pattern); none is
``menu.read``-gated. The created order is OPEN/unpaid and requires staff confirmation
before it closes, which is the intended abuse boundary (rate limiting is a fast follow).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from restaurante.modules.business.application.clock import weekday_and_minute
from restaurante.modules.business.application.use_cases.manage_business import (
    BusinessService,
)
from restaurante.modules.menu.infrastructure.api.schemas import (
    MenuAppearanceConfigSchema,
)
from restaurante.modules.orders.domain.entities import Order
from restaurante.modules.storefront.application.use_cases.manage_storefront import (
    OrderLineCommand,
    StorefrontOrderCommand,
)
from restaurante.modules.storefront.infrastructure.api.deps import (
    AppearanceServiceDep,
    BusinessServiceDep,
    StorefrontServiceDep,
    TenantDep,
)
from restaurante.modules.storefront.infrastructure.api.schemas import (
    CreateStorefrontOrderRequest,
    StorefrontBranchResponse,
    StorefrontHoursResponse,
    StorefrontHourWindow,
    StorefrontMenuResponse,
    StorefrontNextOpening,
    StorefrontOrderResponse,
    StorefrontSessionResponse,
)
from restaurante.shared.domain.errors import NotFoundError
from restaurante.shared.domain.order_label import order_label

router = APIRouter(prefix="/storefront", tags=["storefront"])


@router.get("/appearance", response_model=MenuAppearanceConfigSchema)
async def get_appearance(
    service: AppearanceServiceDep, tenant_id: TenantDep
) -> MenuAppearanceConfigSchema:
    """The tenant's saved public-carta appearance, or the computed default."""
    config = await service.get_appearance(tenant_id)
    return MenuAppearanceConfigSchema.model_validate(config)


@router.get("/branches", response_model=list[StorefrontBranchResponse])
async def list_branches(
    service: StorefrontServiceDep, tenant_id: TenantDep
) -> list[StorefrontBranchResponse]:
    """Active branches, so a customer arriving without a code can pick one."""
    branches = await service.list_branches(tenant_id)
    return [
        StorefrontBranchResponse(
            id=b.id, code=b.code, name=b.name, address=b.address, phone=b.phone
        )
        for b in branches
    ]


@router.get("/session/{token}", response_model=StorefrontSessionResponse)
async def resolve_session(
    token: str, service: StorefrontServiceDep, tenant_id: TenantDep
) -> StorefrontSessionResponse:
    """Quién viene detrás del enlace de WhatsApp, para precargar el checkout.

    Declarada ANTES que `/{branch_code}/…`: si no, un token llamado "menu" se comería
    la ruta de la carta.

    Un token desconocido y uno vencido responden lo mismo (404): quien pruebe enlaces no
    debe poder distinguir "nunca existió" de "existió y caducó". El token NO autentica —
    lo que devuelve es lo que el cliente puede corregir a mano en el formulario.
    """
    contact = await service.resolve_store_token(tenant_id, token)
    if contact is None:
        raise NotFoundError("El enlace no es válido o ya venció.")
    return StorefrontSessionResponse(
        name=contact.name, phone=contact.phone, branch_code=contact.branch_code
    )


async def _hours_for(
    business: BusinessService, tenant_id: uuid.UUID, branch_id: uuid.UUID | None
) -> StorefrontHoursResponse:
    # Hora local del negocio, no la del contenedor: `datetime.now()` en un contenedor es
    # UTC, y con eso la carta anunciaba "cerrado" a media tarde en Colombia.
    weekday, minute = weekday_and_minute()
    open_now, nxt, hours = await business.storefront_status(
        tenant_id,
        weekday=weekday,
        minute=minute,
        branch_id=branch_id,
    )
    return StorefrontHoursResponse(
        is_open_now=open_now,
        next_opening=(
            StorefrontNextOpening(weekday=nxt[0], minute=nxt[1]) if nxt else None
        ),
        windows=[
            StorefrontHourWindow(
                weekday=h.weekday,
                open_minute=h.open_minute,
                close_minute=h.close_minute,
            )
            for h in hours
        ],
    )


@router.get("/hours", response_model=StorefrontHoursResponse)
async def get_hours(
    business: BusinessServiceDep, tenant_id: TenantDep
) -> StorefrontHoursResponse:
    """The tenant's primary-branch opening hours + whether open now + next opening.

    Powers the customer-facing "cerrado · abrimos a las X" state. Informational only —
    the actual order gate is the open cash session.
    """
    return await _hours_for(business, tenant_id, None)


@router.get("/{branch_code}/hours", response_model=StorefrontHoursResponse)
async def get_branch_hours(
    branch_code: str,
    business: BusinessServiceDep,
    service: StorefrontServiceDep,
    tenant_id: TenantDep,
) -> StorefrontHoursResponse:
    """Opening hours of the ADDRESSED branch — a closed sede reports its own next opening."""
    branch_id = await service.resolve_branch(tenant_id, branch_code)
    return await _hours_for(business, tenant_id, branch_id)


@router.get("/menu", response_model=StorefrontMenuResponse)
async def get_menu(
    service: StorefrontServiceDep, tenant_id: TenantDep
) -> StorefrontMenuResponse:
    """Customer-safe menu read-model resolved against the tenant's primary branch.

    Retained for single-branch tenants; the branch-addressed form is
    ``GET /storefront/{branch_code}/menu``.
    """
    branch_id = await service.resolve_branch(tenant_id, None)
    menu = await service.get_menu(tenant_id, branch_id)
    return StorefrontMenuResponse.from_menu(menu)


@router.get("/{branch_code}/menu", response_model=StorefrontMenuResponse)
async def get_branch_menu(
    branch_code: str,
    service: StorefrontServiceDep,
    tenant_id: TenantDep,
) -> StorefrontMenuResponse:
    """Customer-safe menu of the ADDRESSED branch (404 when the code is unknown)."""
    branch_id = await service.resolve_branch(tenant_id, branch_code)
    menu = await service.get_menu(tenant_id, branch_id)
    return StorefrontMenuResponse.from_menu(menu)


def _to_command(payload: CreateStorefrontOrderRequest) -> StorefrontOrderCommand:
    return StorefrontOrderCommand(
        customer_name=payload.customer.name,
        customer_phone=payload.customer.phone,
        fulfillment_type=payload.fulfillment.type,
        payment_method=payload.payment_method,
        address_text=payload.fulfillment.address_text,
        latitude=payload.fulfillment.latitude,
        longitude=payload.fulfillment.longitude,
        reference=payload.fulfillment.reference,
        store_token=payload.store_token,
        lines=[
            OrderLineCommand(
                variant_id=line.variant_id,
                quantity=line.quantity,
                addon_ids=list(line.addon_ids),
                removed_ingredients=list(line.removed_ingredients),
                note=line.note,
            )
            for line in payload.lines
        ],
    )


def _to_response(order: Order) -> StorefrontOrderResponse:
    assert order.id is not None
    return StorefrontOrderResponse(
        order_id=order.id,
        # La MISMA etiqueta que sale por WhatsApp. Antes iba el UUID entero, así que el cliente
        # veía dos números distintos para un solo pedido.
        order_number=order_label(order.id),
        status=order.status,
        edit_token=order.edit_token,
    )


@router.post("/orders", response_model=StorefrontOrderResponse, status_code=201)
async def create_order(
    payload: CreateStorefrontOrderRequest,
    service: StorefrontServiceDep,
    tenant_id: TenantDep,
) -> StorefrontOrderResponse:
    """Create a real OPEN/unpaid order on the primary branch; leaves items pending."""
    branch_id = await service.resolve_branch(tenant_id, None)
    order = await service.create_order(tenant_id, branch_id, _to_command(payload))
    return _to_response(order)


@router.post(
    "/{branch_code}/orders", response_model=StorefrontOrderResponse, status_code=201
)
async def create_branch_order(
    branch_code: str,
    payload: CreateStorefrontOrderRequest,
    service: StorefrontServiceDep,
    tenant_id: TenantDep,
) -> StorefrontOrderResponse:
    """Create the order on the ADDRESSED branch.

    The branch comes from the path only — the body cannot select it, so the menu the
    customer saw and the kitchen that receives the ticket are the same URL.
    """
    branch_id = await service.resolve_branch(tenant_id, branch_code)
    order = await service.create_order(tenant_id, branch_id, _to_command(payload))
    return _to_response(order)
