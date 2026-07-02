"""Branches API: list the current tenant's branches (session context).

Served alongside `/auth/me` because the set of branches a user may operate in is
session-bootstrap data, not gated business data: listing them requires only an
authenticated session (no RBAC permission code). Rows are isolated to the request's
tenant automatically by the SQLAlchemy tenancy filter (`install_tenant_filter`).

Placement note: this lives in the identity module rather than `shared/tenancy`
because it depends on `get_current_user` (identity); `shared` must never import
from `modules` (see shared/models_registry as the only deliberate aggregation point).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.api.deps import (
    CurrentUserDep,
    SessionDep,
)
from restaurante.shared.tenancy.models import BranchModel

router = APIRouter(prefix="/branches", tags=["branches"])


class BranchResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    is_primary: bool


@router.get("", response_model=list[BranchResponse])
async def list_branches(
    session: SessionDep,
    _current_user: CurrentUserDep,
) -> list[BranchResponse]:
    """Active branches of the current tenant, primary first then by name."""
    result = await session.execute(
        select(BranchModel)
        .where(BranchModel.is_active.is_(True))
        .order_by(BranchModel.is_primary.desc(), BranchModel.name.asc())
    )
    return [
        BranchResponse.model_validate(branch, from_attributes=True)
        for branch in result.scalars().all()
    ]
