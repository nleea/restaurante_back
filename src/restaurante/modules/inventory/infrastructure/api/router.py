"""Inventory API: stock tracking + auditable movement ledger.

Reads require `inventory.read`; writes require `inventory.adjust` (RBAC). Every
operation is scoped to the tenant resolved by the subdomain middleware; the
`branch_id` is taken from the path and validated against the tenant.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from restaurante.modules.identity.infrastructure.api.deps import require_permission
from restaurante.modules.inventory.infrastructure.api.deps import (
    InventoryServiceDep,
    TenantDep,
)
from restaurante.modules.inventory.infrastructure.api.schemas import (
    MovementResponse,
    RecountRequest,
    RegisterMovementRequest,
    SetMinStockRequest,
    StockResponse,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])

_READ = Depends(require_permission("inventory.read"))
_WRITE = Depends(require_permission("inventory.adjust"))


# --- Stock ------------------------------------------------------------------
@router.get(
    "/branches/{branch_id}/stock",
    response_model=list[StockResponse],
    dependencies=[_READ],
)
async def list_stock(
    branch_id: uuid.UUID, service: InventoryServiceDep, tenant_id: TenantDep
) -> list[StockResponse]:
    items = await service.list_stock(tenant_id, branch_id)
    return [StockResponse.model_validate(s, from_attributes=True) for s in items]


@router.get(
    "/branches/{branch_id}/stock/low",
    response_model=list[StockResponse],
    dependencies=[_READ],
)
async def list_low_stock(
    branch_id: uuid.UUID, service: InventoryServiceDep, tenant_id: TenantDep
) -> list[StockResponse]:
    items = await service.list_low_stock(tenant_id, branch_id)
    return [StockResponse.model_validate(s, from_attributes=True) for s in items]


@router.get(
    "/branches/{branch_id}/stock/{ingredient_id}",
    response_model=StockResponse,
    dependencies=[_READ],
)
async def get_stock(
    branch_id: uuid.UUID,
    ingredient_id: uuid.UUID,
    service: InventoryServiceDep,
    tenant_id: TenantDep,
) -> StockResponse:
    stock = await service.get_stock(tenant_id, branch_id, ingredient_id)
    return StockResponse.model_validate(stock, from_attributes=True)


@router.put(
    "/branches/{branch_id}/stock/threshold",
    response_model=StockResponse,
    dependencies=[_WRITE],
)
async def set_min_stock(
    branch_id: uuid.UUID,
    payload: SetMinStockRequest,
    service: InventoryServiceDep,
    tenant_id: TenantDep,
) -> StockResponse:
    stock = await service.set_min_stock(
        tenant_id, branch_id, payload.ingredient_id, payload.min_stock
    )
    return StockResponse.model_validate(stock, from_attributes=True)


# --- Movements --------------------------------------------------------------
@router.post(
    "/branches/{branch_id}/movements",
    response_model=MovementResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def register_movement(
    branch_id: uuid.UUID,
    payload: RegisterMovementRequest,
    service: InventoryServiceDep,
    tenant_id: TenantDep,
) -> MovementResponse:
    movement = await service.register_movement(
        tenant_id,
        branch_id,
        payload.ingredient_id,
        payload.employee_id,
        payload.type,
        payload.quantity,
        payload.reason,
        payload.reference_id,
        payload.notes,
    )
    return MovementResponse.model_validate(movement, from_attributes=True)


@router.post(
    "/branches/{branch_id}/recounts",
    response_model=MovementResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def recount(
    branch_id: uuid.UUID,
    payload: RecountRequest,
    service: InventoryServiceDep,
    tenant_id: TenantDep,
) -> MovementResponse:
    movement = await service.recount(
        tenant_id,
        branch_id,
        payload.ingredient_id,
        payload.employee_id,
        payload.counted_quantity,
        payload.reason,
        payload.notes,
    )
    return MovementResponse.model_validate(movement, from_attributes=True)


@router.get(
    "/branches/{branch_id}/movements/{ingredient_id}",
    response_model=list[MovementResponse],
    dependencies=[_READ],
)
async def list_movements(
    branch_id: uuid.UUID,
    ingredient_id: uuid.UUID,
    service: InventoryServiceDep,
    tenant_id: TenantDep,
) -> list[MovementResponse]:
    items = await service.list_movements(tenant_id, branch_id, ingredient_id)
    return [MovementResponse.model_validate(m, from_attributes=True) for m in items]
