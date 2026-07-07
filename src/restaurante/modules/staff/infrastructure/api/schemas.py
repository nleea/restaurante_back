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
    status: str
    origin: str
    covered_by_employee_id: uuid.UUID | None = None
    note: str | None = None


class ShiftTemplateResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    employee_id: uuid.UUID
    weekdays: list[int]
    start_time: time
    end_time: time
    valid_from: date
    valid_until: date | None = None
    generated_through: date | None = None


class TimeOffRequestResponse(BaseModel):
    id: uuid.UUID
    branch_id: uuid.UUID
    employee_id: uuid.UUID
    request_date: date
    reason: str
    status: str
    decided_by: uuid.UUID | None = None
    decided_at: datetime | None = None
    note: str | None = None


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
    note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check_range(self) -> CreatePlannedShiftRequest:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class UpdatePlannedShiftRequest(BaseModel):
    shift_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None


class UpsertTemplateRequest(BaseModel):
    weekdays: list[int] = Field(min_length=1)
    start_time: time
    end_time: time
    valid_from: date
    valid_until: date | None = None

    @model_validator(mode="after")
    def _check(self) -> UpsertTemplateRequest:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError("weekdays must be 0..6 (0=Sun)")
        return self


class MarkDayOffRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=200)
    cover_employee_id: uuid.UUID | None = None


class AssignCoverageRequest(BaseModel):
    cover_employee_id: uuid.UUID


class CreateTimeOffRequestRequest(BaseModel):
    request_date: date
    reason: str = Field(min_length=1, max_length=200)


class ApproveTimeOffRequest(BaseModel):
    cover_employee_id: uuid.UUID | None = None


class RejectTimeOffRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


class CheckInRequest(BaseModel):
    check_in_at: datetime
    planned_shift_id: uuid.UUID | None = None


class CheckOutRequest(BaseModel):
    check_out_at: datetime


class CreateCommissionRequest(BaseModel):
    type: str = Field(min_length=1, max_length=30)
    amount: Decimal = Field(gt=0)
    reference_id: uuid.UUID | None = None
