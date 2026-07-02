"""Application service for the Inventory module.

Validates domain rules (referenced entities exist within the tenant, positive
quantities, no negative on-hand) and delegates persistence to
`InventoryRepository`. Stock changes are recorded as movements and applied
atomically by the repository.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from restaurante.modules.inventory.domain.entities import (
    InventoryMovement,
    InventoryStock,
)
from restaurante.modules.inventory.domain.ports import InventoryRepository
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

MOVEMENT_IN = "in"
MOVEMENT_OUT = "out"
MOVEMENT_ADJUSTMENT = "adjustment"


class InventoryService:
    def __init__(self, repo: InventoryRepository) -> None:
        self._repo = repo

    # --- internal guards ---------------------------------------------------
    async def _require_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> None:
        if not await self._repo.branch_exists(tenant_id, branch_id):
            raise NotFoundError(f"Sucursal no encontrada: {branch_id}")

    async def _require_ingredient(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> None:
        if not await self._repo.ingredient_exists(tenant_id, ingredient_id):
            raise NotFoundError(f"Insumo no encontrado: {ingredient_id}")

    async def _require_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> None:
        if not await self._repo.employee_exists(tenant_id, employee_id):
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")

    # --- Stock reads -------------------------------------------------------
    async def get_stock(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> InventoryStock:
        await self._require_branch(tenant_id, branch_id)
        stock = await self._repo.get_stock(tenant_id, branch_id, ingredient_id)
        if stock is None:
            raise NotFoundError(
                f"Sin stock para el insumo {ingredient_id} en la sucursal {branch_id}"
            )
        return stock

    async def list_stock(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[InventoryStock]:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.list_stock(tenant_id, branch_id)

    async def list_low_stock(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[InventoryStock]:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.list_low_stock(tenant_id, branch_id)

    # --- Reorder threshold -------------------------------------------------
    async def set_min_stock(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        ingredient_id: uuid.UUID,
        min_stock: Decimal,
    ) -> InventoryStock:
        await self._require_branch(tenant_id, branch_id)
        await self._require_ingredient(tenant_id, ingredient_id)
        if min_stock < 0:
            raise ValidationError("El umbral mínimo no puede ser negativo.")
        return await self._repo.set_min_stock(
            tenant_id, branch_id, ingredient_id, min_stock
        )

    # --- Movements ---------------------------------------------------------
    async def register_movement(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        ingredient_id: uuid.UUID,
        employee_id: uuid.UUID,
        movement_type: str,
        quantity: Decimal,
        reason: str,
        reference_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> InventoryMovement:
        await self._require_branch(tenant_id, branch_id)
        await self._require_ingredient(tenant_id, ingredient_id)
        await self._require_employee(tenant_id, employee_id)
        if quantity <= 0:
            raise ValidationError("La cantidad del movimiento debe ser positiva.")

        if movement_type == MOVEMENT_IN:
            delta = quantity
        elif movement_type == MOVEMENT_OUT:
            current = await self._repo.get_stock(tenant_id, branch_id, ingredient_id)
            on_hand = current.current_quantity if current else Decimal(0)
            if quantity > on_hand:
                raise ConflictError(
                    "La salida supera el stock disponible "
                    f"({on_hand}) del insumo {ingredient_id}."
                )
            delta = -quantity
        else:
            raise ValidationError(f"Tipo de movimiento inválido: {movement_type}")

        movement = InventoryMovement(
            tenant_id=tenant_id,
            branch_id=branch_id,
            ingredient_id=ingredient_id,
            type=movement_type,
            reason=reason,
            quantity=quantity,
            employee_id=employee_id,
            reference_id=reference_id,
            notes=notes,
        )
        return await self._repo.apply_movement(movement, delta)

    async def recount(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        ingredient_id: uuid.UUID,
        employee_id: uuid.UUID,
        counted_quantity: Decimal,
        reason: str = "count",
        notes: str | None = None,
    ) -> InventoryMovement:
        await self._require_branch(tenant_id, branch_id)
        await self._require_ingredient(tenant_id, ingredient_id)
        await self._require_employee(tenant_id, employee_id)
        if counted_quantity < 0:
            raise ValidationError("La cantidad contada no puede ser negativa.")

        current = await self._repo.get_stock(tenant_id, branch_id, ingredient_id)
        on_hand = current.current_quantity if current else Decimal(0)
        delta = counted_quantity - on_hand

        movement = InventoryMovement(
            tenant_id=tenant_id,
            branch_id=branch_id,
            ingredient_id=ingredient_id,
            type=MOVEMENT_ADJUSTMENT,
            reason=reason,
            quantity=abs(delta),
            employee_id=employee_id,
            notes=notes,
        )
        return await self._repo.apply_movement(movement, delta)

    async def list_movements(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> list[InventoryMovement]:
        await self._require_branch(tenant_id, branch_id)
        await self._require_ingredient(tenant_id, ingredient_id)
        return await self._repo.list_movements(tenant_id, branch_id, ingredient_id)
