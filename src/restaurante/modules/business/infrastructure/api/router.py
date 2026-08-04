"""Business API: consolidated business profile + structured operating hours (admin).

Reads gated by ``menu.read`` and writes by ``menu.manage`` — the same admin who edits
the public carta's appearance owns the business identity and hours. The storefront's
public hours/next-opening live in the storefront module, not here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from restaurante.modules.business.domain.entities import (
    BranchDetailsUpdate,
    OperatingHours,
)
from restaurante.modules.business.infrastructure.api.deps import (
    BusinessServiceDep,
    TenantDep,
)
from restaurante.modules.business.infrastructure.api.schemas import (
    BusinessProfileResponse,
    OperatingHoursResponse,
    SetHoursRequest,
    UpdateProfileRequest,
)
from restaurante.modules.identity.infrastructure.api.deps import require_permission

router = APIRouter(prefix="/business", tags=["business"])

_READ = Depends(require_permission("menu.read"))
_MANAGE = Depends(require_permission("menu.manage"))


@router.get("/profile", response_model=BusinessProfileResponse, dependencies=[_READ])
async def get_profile(
    service: BusinessServiceDep, tenant_id: TenantDep
) -> BusinessProfileResponse:
    return BusinessProfileResponse.of(await service.get_profile(tenant_id))


@router.put("/profile", response_model=BusinessProfileResponse, dependencies=[_MANAGE])
async def update_profile(
    payload: UpdateProfileRequest,
    service: BusinessServiceDep,
    tenant_id: TenantDep,
) -> BusinessProfileResponse:
    profile = await service.update_profile(
        tenant_id,
        name=payload.name,
        tax_id=payload.tax_id,
        email=payload.email,
        phone=payload.phone,
        branches=[
            BranchDetailsUpdate(id=b.id, address=b.address, phone=b.phone, name=b.name)
            for b in payload.branches
        ],
        photo_url=payload.photo_url,
        payment_qr_url=payload.payment_qr_url,
    )
    return BusinessProfileResponse.of(profile)


@router.get(
    "/branches/{branch_id}/hours",
    response_model=list[OperatingHoursResponse],
    dependencies=[_READ],
)
async def get_hours(
    branch_id: uuid.UUID, service: BusinessServiceDep, tenant_id: TenantDep
) -> list[OperatingHoursResponse]:
    hours = await service.get_hours(tenant_id, branch_id)
    return [OperatingHoursResponse.of(h) for h in hours]


@router.put(
    "/branches/{branch_id}/hours",
    response_model=list[OperatingHoursResponse],
    dependencies=[_MANAGE],
)
async def set_hours(
    branch_id: uuid.UUID,
    payload: SetHoursRequest,
    service: BusinessServiceDep,
    tenant_id: TenantDep,
) -> list[OperatingHoursResponse]:
    hours = await service.set_hours(
        tenant_id,
        branch_id,
        [
            OperatingHours(
                tenant_id=tenant_id,
                branch_id=branch_id,
                weekday=w.weekday,
                open_minute=w.open_minute,
                close_minute=w.close_minute,
            )
            for w in payload.windows
        ],
    )
    return [OperatingHoursResponse.of(h) for h in hours]
