"""Ports (interfaces) of the Staff module."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Protocol

from restaurante.modules.staff.domain.entities import (
    Attendance,
    Commission,
    Employee,
    PlannedShift,
    ShiftTemplate,
    TimeOffRequest,
)


class StaffRepository(Protocol):
    # --- Reference existence checks ----------------------------------------
    async def branch_exists(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...

    async def person_exists(self, person_id: uuid.UUID) -> bool: ...

    async def user_exists(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool: ...

    async def role_exists(self, tenant_id: uuid.UUID, role_id: uuid.UUID) -> bool: ...

    # --- Employees ---------------------------------------------------------
    async def create_employee(self, employee: Employee) -> Employee: ...

    async def get_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> Employee | None: ...

    async def find_employee_by_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> Employee | None: ...

    async def employee_exists_for_person(
        self, tenant_id: uuid.UUID, person_id: uuid.UUID
    ) -> bool: ...

    async def employee_exists_for_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool: ...

    async def list_employees(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        active: bool | None = None,
    ) -> list[Employee]: ...

    async def update_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID, fields: dict[str, Any]
    ) -> Employee | None: ...

    # --- Planned shifts ----------------------------------------------------
    async def create_planned_shift(self, shift: PlannedShift) -> PlannedShift: ...

    async def get_planned_shift(
        self, tenant_id: uuid.UUID, shift_id: uuid.UUID
    ) -> PlannedShift | None: ...

    async def list_planned_shifts(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[PlannedShift]: ...

    async def get_shift_for_slot(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID, shift_date: dt.date
    ) -> PlannedShift | None: ...

    async def list_shifts_in_range(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[PlannedShift]: ...

    async def update_planned_shift(
        self, tenant_id: uuid.UUID, shift_id: uuid.UUID, fields: dict[str, Any]
    ) -> PlannedShift | None: ...

    async def delete_planned_shift(
        self, tenant_id: uuid.UUID, shift_id: uuid.UUID
    ) -> None: ...

    async def delete_template_shifts_from(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID, from_date: dt.date
    ) -> None:
        """Delete future template-origin, still-scheduled shifts (regen prep)."""
        ...

    # --- Shift templates ---------------------------------------------------
    async def create_template(self, template: ShiftTemplate) -> ShiftTemplate: ...

    async def get_template_for_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> ShiftTemplate | None: ...

    async def list_templates(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID | None = None
    ) -> list[ShiftTemplate]: ...

    async def update_template(
        self, tenant_id: uuid.UUID, template_id: uuid.UUID, fields: dict[str, Any]
    ) -> ShiftTemplate | None: ...

    # --- Time-off requests -------------------------------------------------
    async def create_time_off_request(
        self, request: TimeOffRequest
    ) -> TimeOffRequest: ...

    async def get_time_off_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID
    ) -> TimeOffRequest | None: ...

    async def list_time_off_requests(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[TimeOffRequest]: ...

    async def update_time_off_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID, fields: dict[str, Any]
    ) -> TimeOffRequest | None: ...

    # --- Attendances -------------------------------------------------------
    async def create_attendance(self, attendance: Attendance) -> Attendance: ...

    async def get_attendance(
        self, tenant_id: uuid.UUID, attendance_id: uuid.UUID
    ) -> Attendance | None: ...

    async def get_open_attendance(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> Attendance | None: ...

    async def list_attendances(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[Attendance]: ...

    async def update_attendance(
        self, tenant_id: uuid.UUID, attendance_id: uuid.UUID, fields: dict[str, Any]
    ) -> Attendance | None: ...

    # --- Commissions -------------------------------------------------------
    async def create_commission(self, commission: Commission) -> Commission: ...

    async def list_commissions(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[Commission]: ...
