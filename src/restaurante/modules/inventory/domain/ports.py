"""Ports (interfaces) of the Inventory module."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Protocol

from restaurante.modules.inventory.domain.entities import (
    InventoryMovement,
    InventoryStock,
)


class InventoryRepository(Protocol):
    # --- Reference existence checks ----------------------------------------
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    async def ingredient_exists(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> bool: ...

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

    # --- Stock -------------------------------------------------------------
    async def get_stock(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> InventoryStock | None: ...

    async def list_stock(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[InventoryStock]: ...

    async def list_low_stock(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[InventoryStock]: ...

    async def set_min_stock(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        ingredient_id: uuid.UUID,
        min_stock: Decimal,
    ) -> InventoryStock: ...

    # --- Movements (atomic stock change) -----------------------------------
    async def apply_movement(
        self, movement: InventoryMovement, delta: Decimal
    ) -> InventoryMovement: ...

    async def list_movements(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> list[InventoryMovement]: ...
