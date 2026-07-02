"""Pydantic schemas for the Staff API."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

# --- Responses --------------------------------------------------------------


class EmployeeResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    person_id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    hired_at: date | None = None
    is_active: bool


class PlannedShiftResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    employee_id: uuid.UUID
    shift_date: date
    start_time: time
    end_time: time


class AttendanceResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    planned_shift_id: uuid.UUID | None = None
    check_in_at: datetime
    check_out_at: datetime | None = None


class CommissionResponse(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    type: str
    amount: Decimal
    reference_id: uuid.UUID | None = None
    occurred_at: datetime | None = None


# --- Requests ---------------------------------------------------------------


class CreateEmployeeRequest(BaseModel):
    branch_id: uuid.UUID
    person_id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID


class UpdateEmployeeRoleRequest(BaseModel):
    role_id: uuid.UUID


class CreatePlannedShiftRequest(BaseModel):
    shift_date: date
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _check_range(self) -> CreatePlannedShiftRequest:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class UpdatePlannedShiftRequest(BaseModel):
    shift_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None


class CheckInRequest(BaseModel):
    check_in_at: datetime
    planned_shift_id: uuid.UUID | None = None


class CheckOutRequest(BaseModel):
    check_out_at: datetime


class CreateCommissionRequest(BaseModel):
    type: str = Field(min_length=1, max_length=30)
    amount: Decimal = Field(gt=0)
    reference_id: uuid.UUID | None = None
