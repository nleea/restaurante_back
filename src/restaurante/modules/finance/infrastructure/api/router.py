"""Finance API: operating-expense ledger (categories + expenses).

RBAC: reads `finance.read`; all writes `finance.manage`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from restaurante.modules.finance.infrastructure.api.deps import (
    FinanceServiceDep,
    TenantDep,
)
from restaurante.modules.finance.infrastructure.api.schemas import (
    CreateCategoryRequest,
    ExpenseCategoryResponse,
    ExpenseResponse,
    RecordExpenseRequest,
    UpdateCategoryRequest,
)
from restaurante.modules.identity.infrastructure.api.deps import require_permission

router = APIRouter(prefix="/finance", tags=["finance"])

_READ = Depends(require_permission("finance.read"))
_MANAGE = Depends(require_permission("finance.manage"))


# --- Expense categories -----------------------------------------------------
@router.post(
    "/categories",
    response_model=ExpenseCategoryResponse,
    status_code=201,
    dependencies=[_MANAGE],
)
async def create_category(
    payload: CreateCategoryRequest, service: FinanceServiceDep, tenant_id: TenantDep
) -> ExpenseCategoryResponse:
    category = await service.create_category(tenant_id, payload.name)
    return ExpenseCategoryResponse.model_validate(category, from_attributes=True)


@router.get(
    "/categories",
    response_model=list[ExpenseCategoryResponse],
    dependencies=[_READ],
)
async def list_categories(
    service: FinanceServiceDep, tenant_id: TenantDep, active: bool | None = None
) -> list[ExpenseCategoryResponse]:
    categories = await service.list_categories(tenant_id, active=active)
    return [
        ExpenseCategoryResponse.model_validate(c, from_attributes=True)
        for c in categories
    ]


@router.patch(
    "/categories/{category_id}",
    response_model=ExpenseCategoryResponse,
    dependencies=[_MANAGE],
)
async def update_category(
    category_id: uuid.UUID,
    payload: UpdateCategoryRequest,
    service: FinanceServiceDep,
    tenant_id: TenantDep,
) -> ExpenseCategoryResponse:
    category = await service.update_category(
        tenant_id, category_id, payload.model_dump(exclude_unset=True)
    )
    return ExpenseCategoryResponse.model_validate(category, from_attributes=True)


# --- Expenses ---------------------------------------------------------------
@router.post(
    "/expenses", response_model=ExpenseResponse, status_code=201, dependencies=[_MANAGE]
)
async def record_expense(
    payload: RecordExpenseRequest, service: FinanceServiceDep, tenant_id: TenantDep
) -> ExpenseResponse:
    expense = await service.record_expense(
        tenant_id,
        payload.branch_id,
        payload.expense_category_id,
        payload.description,
        payload.amount,
        payload.employee_id,
        payload.incurred_at,
    )
    return ExpenseResponse.model_validate(expense, from_attributes=True)


@router.get("/expenses", response_model=list[ExpenseResponse], dependencies=[_READ])
async def list_expenses(
    service: FinanceServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
) -> list[ExpenseResponse]:
    expenses = await service.list_expenses(
        tenant_id, branch_id=branch_id, category_id=category_id
    )
    return [ExpenseResponse.model_validate(e, from_attributes=True) for e in expenses]


@router.get("/expenses/{expense_id}", response_model=ExpenseResponse, dependencies=[_READ])
async def get_expense(
    expense_id: uuid.UUID, service: FinanceServiceDep, tenant_id: TenantDep
) -> ExpenseResponse:
    expense = await service.get_expense(tenant_id, expense_id)
    return ExpenseResponse.model_validate(expense, from_attributes=True)
