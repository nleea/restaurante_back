"""Application service for the Cash module (caja / arqueo).

Owns the cash-register session lifecycle (open → movements → close with
reconciliation) and enforces the one-open-session-per-branch invariant. The
close-time `expected_amount` reconciles physical cash only; non-cash methods are
recorded but excluded from the drawer count.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from restaurante.modules.cash.domain.entities import CashMovement, CashSession
from restaurante.modules.cash.domain.ports import CashRepository
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

SESSION_OPEN = "open"
SESSION_CLOSED = "closed"

MOVEMENT_TYPES = ("in", "out")


class CashService:
    def __init__(self, repo: CashRepository) -> None:
        self._repo = repo

    # --- internal guards ---------------------------------------------------
    async def _require_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> None:
        if not await self._repo.branch_exists(tenant_id, branch_id):
            raise NotFoundError(f"Sucursal no encontrada: {branch_id}")

    async def _require_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> None:
        if not await self._repo.employee_exists(tenant_id, employee_id):
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")

    async def _require_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> CashSession:
        session = await self._repo.get_session(tenant_id, session_id)
        if session is None:
            raise NotFoundError(f"Sesión de caja no encontrada: {session_id}")
        return session

    async def _require_open_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> CashSession:
        session = await self._require_session(tenant_id, session_id)
        if session.status != SESSION_OPEN:
            raise ConflictError(
                f"La sesión de caja no está abierta (estado: {session.status})."
            )
        return session

    # --- Sessions ----------------------------------------------------------
    async def open_session(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        opened_by_employee_id: uuid.UUID,
        opening_amount: Decimal,
    ) -> CashSession:
        await self._require_branch(tenant_id, branch_id)
        await self._require_employee(tenant_id, opened_by_employee_id)
        if opening_amount < 0:
            raise ValidationError("El monto de apertura no puede ser negativo.")
        if await self._repo.get_open_session(tenant_id, branch_id) is not None:
            raise ConflictError("La sucursal ya tiene una sesión de caja abierta.")
        return await self._repo.create_session(
            CashSession(
                tenant_id=tenant_id,
                branch_id=branch_id,
                opened_by_employee_id=opened_by_employee_id,
                opening_amount=opening_amount,
            )
        )

    async def get_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> CashSession:
        return await self._require_session(tenant_id, session_id)

    async def get_open_session(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> CashSession:
        await self._require_branch(tenant_id, branch_id)
        session = await self._repo.get_open_session(tenant_id, branch_id)
        if session is None:
            raise NotFoundError(
                f"No hay sesión de caja abierta en la sucursal: {branch_id}"
            )
        return session

    async def list_sessions(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[CashSession]:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.list_sessions(tenant_id, branch_id, status=status)

    async def close_session(
        self,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        closed_by_employee_id: uuid.UUID,
        counted_amount: Decimal,
    ) -> CashSession:
        session = await self._require_open_session(tenant_id, session_id)
        await self._require_employee(tenant_id, closed_by_employee_id)
        if counted_amount < 0:
            raise ValidationError("El monto contado no puede ser negativo.")
        cash_in, cash_out = await self._repo.cash_totals(tenant_id, session_id)
        expected = session.opening_amount + cash_in - cash_out
        updated = await self._repo.update_session(
            tenant_id,
            session_id,
            {
                "status": SESSION_CLOSED,
                "counted_amount": counted_amount,
                "expected_amount": expected,
                "difference": counted_amount - expected,
                "closed_by_employee_id": closed_by_employee_id,
                "closed_at": datetime.now(UTC),
            },
        )
        assert updated is not None
        return updated

    # --- Movements ---------------------------------------------------------
    async def register_movement(
        self,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        movement_type: str,
        concept: str,
        amount: Decimal,
        method: str,
        reference_id: uuid.UUID | None = None,
    ) -> CashMovement:
        session = await self._require_open_session(tenant_id, session_id)
        if movement_type not in MOVEMENT_TYPES:
            raise ValidationError(f"Tipo de movimiento inválido: {movement_type}")
        if amount <= 0:
            raise ValidationError("El monto del movimiento debe ser positivo.")
        return await self._repo.create_movement(
            CashMovement(
                tenant_id=tenant_id,
                branch_id=session.branch_id,
                cash_session_id=session_id,
                type=movement_type,
                concept=concept,
                amount=amount,
                method=method,
                reference_id=reference_id,
            )
        )

    async def list_movements(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> list[CashMovement]:
        await self._require_session(tenant_id, session_id)
        return await self._repo.list_movements(tenant_id, session_id)
