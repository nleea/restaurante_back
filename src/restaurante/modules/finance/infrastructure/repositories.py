"""Persistence adapter for the Finance module over SQLAlchemy async.

Each write commits its own unit of work and filters explicitly by ``tenant_id``
(and ``branch_id`` where applicable).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.finance.domain.entities import Expense, ExpenseCategory
from restaurante.modules.finance.infrastructure.models import (
    ExpenseCategoryModel,
    ExpenseModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.tenancy.models import BranchModel


def _category(m: ExpenseCategoryModel) -> ExpenseCategory:
    return ExpenseCategory(
        id=m.id, tenant_id=m.tenant_id, name=m.name, is_active=m.is_active
    )


def _expense(m: ExpenseModel) -> Expense:
    return Expense(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        expense_category_id=m.expense_category_id,
        description=m.description,
        amount=m.amount,
        employee_id=m.employee_id,
        incurred_at=m.incurred_at,
    )


class SqlAlchemyFinanceRepository:
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

    async def category_exists(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> bool:
        stmt = select(ExpenseCategoryModel.id).where(
            ExpenseCategoryModel.id == category_id,
            ExpenseCategoryModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Expense categories ------------------------------------------------
    async def create_category(self, category: ExpenseCategory) -> ExpenseCategory:
        model = ExpenseCategoryModel(
            tenant_id=category.tenant_id,
            name=category.name,
            is_active=category.is_active,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _category(model)

    async def _get_category_model(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> ExpenseCategoryModel | None:
        stmt = select(ExpenseCategoryModel).where(
            ExpenseCategoryModel.id == category_id,
            ExpenseCategoryModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID
    ) -> ExpenseCategory | None:
        model = await self._get_category_model(tenant_id, category_id)
        return _category(model) if model else None

    async def list_categories(
        self, tenant_id: uuid.UUID, *, active: bool | None = None
    ) -> list[ExpenseCategory]:
        stmt = select(ExpenseCategoryModel).where(
            ExpenseCategoryModel.tenant_id == tenant_id
        )
        if active is not None:
            stmt = stmt.where(ExpenseCategoryModel.is_active.is_(active))
        stmt = stmt.order_by(ExpenseCategoryModel.name)
        return [_category(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_category(
        self, tenant_id: uuid.UUID, category_id: uuid.UUID, fields: dict[str, Any]
    ) -> ExpenseCategory | None:
        model = await self._get_category_model(tenant_id, category_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _category(model)

    # --- Expenses ----------------------------------------------------------
    async def create_expense(self, expense: Expense) -> Expense:
        kwargs: dict[str, Any] = {
            "tenant_id": expense.tenant_id,
            "branch_id": expense.branch_id,
            "expense_category_id": expense.expense_category_id,
            "description": expense.description,
            "amount": expense.amount,
            "employee_id": expense.employee_id,
        }
        if expense.incurred_at is not None:
            kwargs["incurred_at"] = expense.incurred_at
        model = ExpenseModel(**kwargs)
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _expense(model)

    async def get_expense(
        self, tenant_id: uuid.UUID, expense_id: uuid.UUID
    ) -> Expense | None:
        stmt = select(ExpenseModel).where(
            ExpenseModel.id == expense_id, ExpenseModel.tenant_id == tenant_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _expense(model) if model else None

    async def list_expenses(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
    ) -> list[Expense]:
        stmt = select(ExpenseModel).where(ExpenseModel.tenant_id == tenant_id)
        if branch_id is not None:
            stmt = stmt.where(ExpenseModel.branch_id == branch_id)
        if category_id is not None:
            stmt = stmt.where(ExpenseModel.expense_category_id == category_id)
        stmt = stmt.order_by(ExpenseModel.incurred_at.desc())
        return [_expense(m) for m in (await self._session.execute(stmt)).scalars()]
