"""Persistence adapter for the Cash module over SQLAlchemy async.

Each write method commits its own unit of work and filters explicitly by
``tenant_id`` (and ``branch_id``). ``cash_totals`` aggregates only physical-cash
movements (``method = 'cash'``) for the close-time reconciliation; non-cash
methods (card, Nequi, Daviplata) are recorded but excluded from the drawer count.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.cash.domain.entities import CashMovement, CashSession
from restaurante.modules.cash.infrastructure.models import (
    CashMovementModel,
    CashSessionModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.tenancy.models import BranchModel

CASH_METHOD = "cash"
_MOVEMENT_IN = "in"
_MOVEMENT_OUT = "out"


def _session(m: CashSessionModel) -> CashSession:
    return CashSession(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        opened_by_employee_id=m.opened_by_employee_id,
        opening_amount=m.opening_amount,
        status=m.status,
        opened_at=m.opened_at,
        closed_by_employee_id=m.closed_by_employee_id,
        counted_amount=m.counted_amount,
        expected_amount=m.expected_amount,
        difference=m.difference,
        closed_at=m.closed_at,
    )


def _movement(m: CashMovementModel) -> CashMovement:
    return CashMovement(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        cash_session_id=m.cash_session_id,
        type=m.type,
        concept=m.concept,
        amount=m.amount,
        method=m.method,
        reference_id=m.reference_id,
    )


class SqlAlchemyCashRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reference existence checks ----------------------------------------
    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool:
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.id == employee_id, EmployeeModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Sessions ----------------------------------------------------------
    async def create_session(self, session: CashSession) -> CashSession:
        model = CashSessionModel(
            tenant_id=session.tenant_id,
            branch_id=session.branch_id,
            opened_by_employee_id=session.opened_by_employee_id,
            opening_amount=session.opening_amount,
            status=session.status,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _session(model)

    async def _get_session_model(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> CashSessionModel | None:
        stmt = select(CashSessionModel).where(
            CashSessionModel.id == session_id,
            CashSessionModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> CashSession | None:
        model = await self._get_session_model(tenant_id, session_id)
        return _session(model) if model else None

    async def get_open_session(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> CashSession | None:
        stmt = select(CashSessionModel).where(
            CashSessionModel.tenant_id == tenant_id,
            CashSessionModel.branch_id == branch_id,
            CashSessionModel.status == "open",
        )
        model = (await self._session.execute(stmt)).scalars().first()
        return _session(model) if model else None

    async def list_sessions(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[CashSession]:
        stmt = select(CashSessionModel).where(
            CashSessionModel.tenant_id == tenant_id,
            CashSessionModel.branch_id == branch_id,
        )
        if status is not None:
            stmt = stmt.where(CashSessionModel.status == status)
        stmt = stmt.order_by(CashSessionModel.opened_at.desc())
        return [_session(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID, fields: dict[str, Any]
    ) -> CashSession | None:
        model = await self._get_session_model(tenant_id, session_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _session(model)

    # --- Movements ---------------------------------------------------------
    async def create_movement(self, movement: CashMovement) -> CashMovement:
        model = CashMovementModel(
            tenant_id=movement.tenant_id,
            branch_id=movement.branch_id,
            cash_session_id=movement.cash_session_id,
            type=movement.type,
            concept=movement.concept,
            amount=movement.amount,
            method=movement.method,
            reference_id=movement.reference_id,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _movement(model)

    async def list_movements(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> list[CashMovement]:
        stmt = (
            select(CashMovementModel)
            .where(
                CashMovementModel.tenant_id == tenant_id,
                CashMovementModel.cash_session_id == session_id,
            )
            .order_by(CashMovementModel.created_at)
        )
        return [_movement(m) for m in (await self._session.execute(stmt)).scalars()]

    async def cash_totals(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> tuple[Decimal, Decimal]:
        stmt = (
            select(
                CashMovementModel.type,
                func.coalesce(func.sum(CashMovementModel.amount), 0),
            )
            .where(
                CashMovementModel.tenant_id == tenant_id,
                CashMovementModel.cash_session_id == session_id,
                CashMovementModel.method == CASH_METHOD,
            )
            .group_by(CashMovementModel.type)
        )
        rows = (await self._session.execute(stmt)).all()
        totals = {row[0]: Decimal(str(row[1])) for row in rows}
        return totals.get(_MOVEMENT_IN, Decimal(0)), totals.get(
            _MOVEMENT_OUT, Decimal(0)
        )
