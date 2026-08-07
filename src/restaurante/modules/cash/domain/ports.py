"""Ports (interfaces) of the Cash module."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Protocol

from restaurante.modules.cash.domain.entities import CashMovement, CashSession


class CashRepository(Protocol):
    # --- Reference existence checks ----------------------------------------
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

    # --- Sessions ----------------------------------------------------------
    async def create_session(self, session: CashSession) -> CashSession: ...

    async def get_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> CashSession | None: ...

    async def get_open_session(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> CashSession | None: ...

    async def list_sessions(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[CashSession]: ...

    async def update_session(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID, fields: dict[str, Any]
    ) -> CashSession | None: ...

    # --- Movements ---------------------------------------------------------
    async def create_movement(self, movement: CashMovement) -> CashMovement: ...

    async def list_movements(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> list[CashMovement]: ...

    async def unresolved_deliveries(
        self, tenant_id: uuid.UUID, cash_session_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str]]:
        """Entregas del turno que aún no tienen desenlace: (delivery_id, estado).

        Resuelta es `delivered` o `not_delivered`. Todo lo demás —`pending`, `assigned`,
        `in_transit`— significa que puede haber efectivo en el bolsillo de alguien o comida
        en la calle sin desenlace escrito, y eso no puede cerrar un turno.
        """
        ...

    async def cash_totals(
        self, tenant_id: uuid.UUID, session_id: uuid.UUID
    ) -> tuple[Decimal, Decimal]: ...
