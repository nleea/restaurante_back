"""Pydantic schemas for the Finance API."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# --- Responses --------------------------------------------------------------


class ExpenseCategoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool


class ExpenseResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    expense_category_id: uuid.UUID
    description: str
    amount: Decimal
    employee_id: uuid.UUID
    incurred_at: datetime | None = None


# --- Requests ---------------------------------------------------------------


class CreateCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class UpdateCategoryRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None


class RecordExpenseRequest(BaseModel):
    branch_id: uuid.UUID
    expense_category_id: uuid.UUID
    description: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0)
    employee_id: uuid.UUID
    incurred_at: datetime | None = None
