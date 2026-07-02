"""Persistence adapter for the Inventory module over SQLAlchemy async.

Stock changes go through ``apply_movement``, which updates the ``inventory_stocks``
row and inserts the ``inventory_movements`` audit row in a single transaction.
Every query filters explicitly by ``tenant_id`` (and ``branch_id``) as defense in
depth on top of the automatic tenancy filter.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.inventory.domain.entities import (
    InventoryMovement,
    InventoryStock,
)
from restaurante.modules.inventory.infrastructure.models import (
    InventoryMovementModel,
    InventoryStockModel,
)
from restaurante.modules.recipes.infrastructure.models import IngredientModel
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.tenancy.models import BranchModel


def _stock(m: InventoryStockModel) -> InventoryStock:
    return InventoryStock(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        ingredient_id=m.ingredient_id,
        current_quantity=m.current_quantity,
        min_stock=m.min_stock,
        updated_at=m.updated_at,
    )


def _movement(m: InventoryMovementModel) -> InventoryMovement:
    return InventoryMovement(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        ingredient_id=m.ingredient_id,
        type=m.type,
        reason=m.reason,
        quantity=m.quantity,
        employee_id=m.employee_id,
        reference_id=m.reference_id,
        notes=m.notes,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlAlchemyInventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reference existence checks ----------------------------------------
    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def ingredient_exists(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> bool:
        stmt = select(IngredientModel.id).where(
            IngredientModel.id == ingredient_id,
            IngredientModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool:
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.id == employee_id, EmployeeModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Stock -------------------------------------------------------------
    async def _get_stock_model(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> InventoryStockModel | None:
        stmt = select(InventoryStockModel).where(
            InventoryStockModel.tenant_id == tenant_id,
            InventoryStockModel.branch_id == branch_id,
            InventoryStockModel.ingredient_id == ingredient_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_stock(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> InventoryStock | None:
        model = await self._get_stock_model(tenant_id, branch_id, ingredient_id)
        return _stock(model) if model else None

    async def list_stock(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[InventoryStock]:
        stmt = (
            select(InventoryStockModel)
            .where(
                InventoryStockModel.tenant_id == tenant_id,
                InventoryStockModel.branch_id == branch_id,
            )
            .order_by(InventoryStockModel.ingredient_id)
        )
        return [_stock(m) for m in (await self._session.execute(stmt)).scalars()]

    async def list_low_stock(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[InventoryStock]:
        stmt = (
            select(InventoryStockModel)
            .where(
                InventoryStockModel.tenant_id == tenant_id,
                InventoryStockModel.branch_id == branch_id,
                InventoryStockModel.current_quantity <= InventoryStockModel.min_stock,
            )
            .order_by(InventoryStockModel.ingredient_id)
        )
        return [_stock(m) for m in (await self._session.execute(stmt)).scalars()]

    async def set_min_stock(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        ingredient_id: uuid.UUID,
        min_stock: Decimal,
    ) -> InventoryStock:
        model = await self._get_stock_model(tenant_id, branch_id, ingredient_id)
        if model is None:
            model = InventoryStockModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                ingredient_id=ingredient_id,
                current_quantity=Decimal(0),
                min_stock=min_stock,
            )
            self._session.add(model)
        else:
            model.min_stock = min_stock
        await self._session.commit()
        await self._session.refresh(model)
        return _stock(model)

    # --- Movements (atomic stock change) -----------------------------------
    async def apply_movement(
        self, movement: InventoryMovement, delta: Decimal
    ) -> InventoryMovement:
        stock = await self._get_stock_model(
            movement.tenant_id, movement.branch_id, movement.ingredient_id
        )
        if stock is None:
            stock = InventoryStockModel(
                tenant_id=movement.tenant_id,
                branch_id=movement.branch_id,
                ingredient_id=movement.ingredient_id,
                current_quantity=delta,
                min_stock=Decimal(0),
            )
            self._session.add(stock)
        else:
            stock.current_quantity = stock.current_quantity + delta

        model = InventoryMovementModel(
            tenant_id=movement.tenant_id,
            branch_id=movement.branch_id,
            ingredient_id=movement.ingredient_id,
            type=movement.type,
            reason=movement.reason,
            quantity=movement.quantity,
            employee_id=movement.employee_id,
            reference_id=movement.reference_id,
            notes=movement.notes,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _movement(model)

    async def list_movements(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> list[InventoryMovement]:
        stmt = (
            select(InventoryMovementModel)
            .where(
                InventoryMovementModel.tenant_id == tenant_id,
                InventoryMovementModel.branch_id == branch_id,
                InventoryMovementModel.ingredient_id == ingredient_id,
            )
            .order_by(InventoryMovementModel.created_at.desc())
        )
        return [_movement(m) for m in (await self._session.execute(stmt)).scalars()]
