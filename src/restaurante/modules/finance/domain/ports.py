"""Ports (interfaces) of the Finance module."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from restaurante.modules.finance.domain.entities import Expense, ExpenseCategory


class FinanceRepository(Protocol):
    # --- Reference existence checks ----------------------------------------
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool: ...

    async def category_exists(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> bool: ...

    # --- Expense categories ------------------------------------------------
    async def create_category(self, category: ExpenseCategory) -> ExpenseCategory: ...

    async def get_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> ExpenseCategory | None: ...

    async def list_categories(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[ExpenseCategory]: ...

    async def update_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID, fields: dict[str, Any]
    ) -> ExpenseCategory | None: ...

    # --- Expenses ----------------------------------------------------------
    async def create_expense(self, expense: Expense) -> Expense: ...

    async def get_expense(
        self, tenant_id: uuid.UUID, expense_id: uuid.UUID
    ) -> Expense | None: ...

    async def list_expenses(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
    ) -> list[Expense]: ...
