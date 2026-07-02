"""Application service for the Staff module.

Validates domain rules (referenced entities exist and belong to the tenant,
branch validation, time-range and single-open-attendance invariants) and
delegates persistence to `StaffRepository`. Accepts/returns framework-free
domain entities; the API layer maps to/from Pydantic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from restaurante.modules.staff.domain.entities import (
    Attendance,
    Commission,
    Employee,
    PlannedShift,
)
from restaurante.modules.staff.domain.ports import StaffRepository
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


def _as_aware(value: datetime) -> datetime:
    """Coerce a datetime to UTC-aware.

    Postgres (``timestamptz``) returns tz-aware datetimes, but some backends
    (e.g. SQLite) return naive ones. Normalizing avoids "can't compare
    offset-naive and offset-aware datetimes" when checking ordering.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class StaffService:
    def __init__(self, repo: StaffRepository) -> None:
        self._repo = repo

    # --- internal guards ---------------------------------------------------
    async def _require_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> Employee:
        employee = await self._repo.get_employee(tenant_id, employee_id)
        if employee is None:
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")
        return employee

    async def _require_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> None:
        if not await self._repo.branch_exists(tenant_id, branch_id):
            raise NotFoundError(f"Sucursal no encontrada: {branch_id}")

    # --- Employees ---------------------------------------------------------
    async def create_employee(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        person_id: uuid.UUID,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
    ) -> Employee:
        await self._require_branch(tenant_id, branch_id)
        if not await self._repo.person_exists(person_id):
            raise NotFoundError(f"Persona no encontrada: {person_id}")
        if not await self._repo.user_exists(tenant_id, user_id):
            raise NotFoundError(f"Usuario no encontrado: {user_id}")
        if not await self._repo.role_exists(tenant_id, role_id):
            raise NotFoundError(f"Rol no encontrado: {role_id}")
        if await self._repo.employee_exists_for_person(tenant_id, person_id):
            raise ConflictError("Esa persona ya está vinculada a un empleado.")
        if await self._repo.employee_exists_for_user(tenant_id, user_id):
            raise ConflictError("Ese usuario ya está vinculado a un empleado.")
        return await self._repo.create_employee(
            Employee(
                tenant_id=tenant_id,
                branch_id=branch_id,
                person_id=person_id,
                user_id=user_id,
                role_id=role_id,
            )
        )

    async def list_employees(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        active: bool | None = None,
    ) -> list[Employee]:
        return await self._repo.list_employees(
            tenant_id, branch_id=branch_id, active=active
        )

    async def get_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> Employee:
        return await self._require_employee(tenant_id, employee_id)

    async def get_employee_for_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> Employee:
        employee = await self._repo.find_employee_by_user(tenant_id, user_id)
        if employee is None:
            raise NotFoundError("El usuario no está vinculado a un empleado.")
        return employee

    async def update_employee_role(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID, role_id: uuid.UUID
    ) -> Employee:
        await self._require_employee(tenant_id, employee_id)
        if not await self._repo.role_exists(tenant_id, role_id):
            raise NotFoundError(f"Rol no encontrado: {role_id}")
        updated = await self._repo.update_employee(
            tenant_id, employee_id, {"role_id": role_id}
        )
        if updated is None:
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")
        return updated

    async def deactivate_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> Employee:
        await self._require_employee(tenant_id, employee_id)
        updated = await self._repo.update_employee(
            tenant_id, employee_id, {"is_active": False}
        )
        if updated is None:
            raise NotFoundError(f"Empleado no encontrado: {employee_id}")
        return updated

    # --- Planned shifts ----------------------------------------------------
    async def create_planned_shift(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
        shift_date: date,
        start_time: time,
        end_time: time,
    ) -> PlannedShift:
        employee = await self._require_employee(tenant_id, employee_id)
        if end_time <= start_time:
            raise ValidationError(
                "La hora de fin debe ser posterior a la de inicio."
            )
        return await self._repo.create_planned_shift(
            PlannedShift(
                tenant_id=tenant_id,
                branch_id=employee.branch_id,
                employee_id=employee_id,
                shift_date=shift_date,
                start_time=start_time,
                end_time=end_time,
            )
        )

    async def list_planned_shifts(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[PlannedShift]:
        await self._require_employee(tenant_id, employee_id)
        return await self._repo.list_planned_shifts(tenant_id, employee_id)

    async def update_planned_shift(
        self, tenant_id: uuid.UUID, shift_id: uuid.UUID, fields: dict[str, Any]
    ) -> PlannedShift:
        current = await self._repo.get_planned_shift(tenant_id, shift_id)
        if current is None:
            raise NotFoundError(f"Turno no encontrado: {shift_id}")
        start = fields.get("start_time", current.start_time)
        end = fields.get("end_time", current.end_time)
        if end <= start:
            raise ValidationError(
                "La hora de fin debe ser posterior a la de inicio."
            )
        updated = await self._repo.update_planned_shift(tenant_id, shift_id, fields)
        if updated is None:
            raise NotFoundError(f"Turno no encontrado: {shift_id}")
        return updated

    async def delete_planned_shift(
        self, tenant_id: uuid.UUID, shift_id: uuid.UUID
    ) -> None:
        current = await self._repo.get_planned_shift(tenant_id, shift_id)
        if current is None:
            raise NotFoundError(f"Turno no encontrado: {shift_id}")
        await self._repo.delete_planned_shift(tenant_id, shift_id)

    # --- Attendances -------------------------------------------------------
    async def check_in(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
        check_in_at: datetime,
        planned_shift_id: uuid.UUID | None,
    ) -> Attendance:
        await self._require_employee(tenant_id, employee_id)
        if planned_shift_id is not None:
            shift = await self._repo.get_planned_shift(tenant_id, planned_shift_id)
            if shift is None:
                raise NotFoundError(f"Turno no encontrado: {planned_shift_id}")
        if await self._repo.get_open_attendance(tenant_id, employee_id) is not None:
            raise ConflictError("El empleado ya tiene una asistencia abierta.")
        return await self._repo.create_attendance(
            Attendance(
                tenant_id=tenant_id,
                employee_id=employee_id,
                check_in_at=check_in_at,
                planned_shift_id=planned_shift_id,
            )
        )

    async def check_out(
        self,
        tenant_id: uuid.UUID,
        attendance_id: uuid.UUID,
        check_out_at: datetime,
    ) -> Attendance:
        attendance = await self._repo.get_attendance(tenant_id, attendance_id)
        if attendance is None:
            raise NotFoundError(f"Asistencia no encontrada: {attendance_id}")
        if attendance.check_out_at is not None:
            raise ConflictError("La asistencia ya fue cerrada.")
        if _as_aware(check_out_at) <= _as_aware(attendance.check_in_at):
            raise ValidationError(
                "La hora de salida debe ser posterior a la de entrada."
            )
        updated = await self._repo.update_attendance(
            tenant_id, attendance_id, {"check_out_at": check_out_at}
        )
        if updated is None:
            raise NotFoundError(f"Asistencia no encontrada: {attendance_id}")
        return updated

    async def list_attendances(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[Attendance]:
        await self._require_employee(tenant_id, employee_id)
        return await self._repo.list_attendances(tenant_id, employee_id)

    # --- Commissions -------------------------------------------------------
    async def create_commission(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
        commission_type: str,
        amount: Decimal,
        reference_id: uuid.UUID | None,
    ) -> Commission:
        await self._require_employee(tenant_id, employee_id)
        if amount <= 0:
            raise ValidationError("El monto de la comisión debe ser positivo.")
        return await self._repo.create_commission(
            Commission(
                tenant_id=tenant_id,
                employee_id=employee_id,
                type=commission_type,
                amount=amount,
                reference_id=reference_id,
            )
        )

    async def list_commissions(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[Commission]:
        await self._require_employee(tenant_id, employee_id)
        return await self._repo.list_commissions(tenant_id, employee_id)
