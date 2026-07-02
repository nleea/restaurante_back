"""Ports (interfaces) of the Staff module."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from restaurante.modules.staff.domain.entities import (
    Attendance,
    Commission,
    Employee,
    PlannedShift,
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

    async def update_planned_shift(
        self, tenant_id: uuid.UUID, shift_id: uuid.UUID, fields: dict[str, Any]
    ) -> PlannedShift | None: ...

    async def delete_planned_shift(
        self, tenant_id: uuid.UUID, shift_id: uuid.UUID
    ) -> None: ...

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
