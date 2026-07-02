"""Application service for the Finance module (operating-expense ledger).

Owns expense categories and branch expenses. Expenses are an independent ledger
(not coupled to the cash drawer). Validates references within the tenant and the
positive-amount rule.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from restaurante.modules.finance.domain.entities import Expense, ExpenseCategory
from restaurante.modules.finance.domain.ports import FinanceRepository
from restaurante.shared.domain.errors import NotFoundError, ValidationError


class FinanceService:
    def __init__(self, repo: FinanceRepository) -> None:
        self._repo = repo

    # --- guards ------------------------------------------------------------
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

    async def _require_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> None:
        if not await self._repo.category_exists(tenant_id, category_id):
            raise NotFoundError(f"Categoría de gasto no encontrada: {category_id}")

    # --- Categories --------------------------------------------------------
    async def create_category(
        self, tenant_id: uuid.UUID, name: str
    ) -> ExpenseCategory:
        return await self._repo.create_category(
            ExpenseCategory(tenant_id=tenant_id, name=name)
        )

    async def list_categories(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[ExpenseCategory]:
        return await self._repo.list_categories(tenant_id, active=active)

    async def update_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID, fields: dict[str, Any]
    ) -> ExpenseCategory:
        updated = await self._repo.update_category(tenant_id, category_id, fields)
        if updated is None:
            raise NotFoundError(f"Categoría de gasto no encontrada: {category_id}")
        return updated

    async def deactivate_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> ExpenseCategory:
        await self._require_category(tenant_id, category_id)
        return await self.update_category(tenant_id, category_id, {"is_active": False})

    # --- Expenses ----------------------------------------------------------
    async def record_expense(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        expense_category_id: uuid.UUID,
        description: str,
        amount: Decimal,
        employee_id: uuid.UUID,
        incurred_at: datetime | None = None,
    ) -> Expense:
        await self._require_branch(tenant_id, branch_id)
        await self._require_category(tenant_id, expense_category_id)
        await self._require_employee(tenant_id, employee_id)
        if amount <= 0:
            raise ValidationError("El monto del gasto debe ser positivo.")
        return await self._repo.create_expense(
            Expense(
                tenant_id=tenant_id,
                branch_id=branch_id,
                expense_category_id=expense_category_id,
                description=description,
                amount=amount,
                employee_id=employee_id,
                incurred_at=incurred_at,
            )
        )

    async def get_expense(
        self, tenant_id: uuid.UUID, expense_id: uuid.UUID
    ) -> Expense:
        expense = await self._repo.get_expense(tenant_id, expense_id)
        if expense is None:
            raise NotFoundError(f"Gasto no encontrado: {expense_id}")
        return expense

    async def list_expenses(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
    ) -> list[Expense]:
        return await self._repo.list_expenses(
            tenant_id, branch_id=branch_id, category_id=category_id
        )
