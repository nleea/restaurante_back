"""Application service for the Staff module.

Validates domain rules (referenced entities exist and belong to the tenant,
branch validation, time-range and single-open-attendance invariants) and
delegates persistence to `StaffRepository`. Accepts/returns framework-free
domain entities; the API layer maps to/from Pydantic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from restaurante.modules.staff.domain.entities import (
    Attendance,
    Commission,
    Employee,
    PlannedShift,
    ShiftTemplate,
    TimeOffRequest,
)
from restaurante.modules.staff.domain.ports import StaffRepository
from restaurante.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)

_HORIZON_DAYS = 90


def _dow(d: date) -> int:
    """Weekday as 0=Sun..6=Sat (matches the calendar UI and templates)."""
    return (d.weekday() + 1) % 7


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
        note: str | None = None,
    ) -> PlannedShift:
        """Create a one-off (manual) shift outside the template pattern."""
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
                status="manual",
                origin="manual",
                note=note,
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

    async def list_shifts_in_range(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: date,
        date_to: date,
    ) -> list[PlannedShift]:
        await self._require_branch(tenant_id, branch_id)
        if date_to < date_from:
            raise ValidationError("El rango de fechas es inválido.")
        return await self._repo.list_shifts_in_range(
            tenant_id, branch_id, date_from, date_to
        )

    # --- Day off / coverage ------------------------------------------------
    async def mark_day_off(
        self,
        tenant_id: uuid.UUID,
        shift_id: uuid.UUID,
        reason: str,
        cover_employee_id: uuid.UUID | None = None,
    ) -> PlannedShift:
        shift = await self._repo.get_planned_shift(tenant_id, shift_id)
        if shift is None:
            raise NotFoundError(f"Turno no encontrado: {shift_id}")
        updated = await self._repo.update_planned_shift(
            tenant_id, shift_id, {"status": "day_off", "note": reason}
        )
        if updated is None:
            raise NotFoundError(f"Turno no encontrado: {shift_id}")
        if cover_employee_id is not None:
            await self._create_coverage(tenant_id, updated, cover_employee_id)
        return updated

    async def assign_coverage(
        self,
        tenant_id: uuid.UUID,
        shift_id: uuid.UUID,
        cover_employee_id: uuid.UUID,
    ) -> PlannedShift:
        """Assign a substitute to an already-off shift; returns the coverage shift."""
        absent_shift = await self._repo.get_planned_shift(tenant_id, shift_id)
        if absent_shift is None:
            raise NotFoundError(f"Turno no encontrado: {shift_id}")
        if absent_shift.status != "day_off":
            raise ValidationError("Solo se puede cubrir un día libre.")
        return await self._create_coverage(tenant_id, absent_shift, cover_employee_id)

    async def _create_coverage(
        self,
        tenant_id: uuid.UUID,
        absent_shift: PlannedShift,
        cover_employee_id: uuid.UUID,
    ) -> PlannedShift:
        cover = await self._require_employee(tenant_id, cover_employee_id)
        if not cover.is_active:
            raise ValidationError("El empleado de cobertura no está activo.")
        if not await self._is_available(
            tenant_id, cover_employee_id, absent_shift.shift_date
        ):
            raise ConflictError("El empleado no está disponible ese día.")
        return await self._repo.create_planned_shift(
            PlannedShift(
                tenant_id=tenant_id,
                branch_id=absent_shift.branch_id,
                employee_id=cover_employee_id,
                shift_date=absent_shift.shift_date,
                start_time=absent_shift.start_time,
                end_time=absent_shift.end_time,
                status="covered",
                origin="coverage",
                covered_by_employee_id=absent_shift.employee_id,
            )
        )

    async def _is_available(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID, on_date: date
    ) -> bool:
        if await self._repo.get_shift_for_slot(tenant_id, employee_id, on_date):
            return False
        template = await self._repo.get_template_for_employee(tenant_id, employee_id)
        if template is not None and _dow(on_date) in template.weekdays:
            return False
        return True

    async def available_covers(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, on_date: date
    ) -> list[Employee]:
        await self._require_branch(tenant_id, branch_id)
        employees = await self._repo.list_employees(
            tenant_id, branch_id=branch_id, active=True
        )
        available: list[Employee] = []
        for emp in employees:
            if emp.id is not None and await self._is_available(
                tenant_id, emp.id, on_date
            ):
                available.append(emp)
        return available

    # --- Shift templates + generation -------------------------------------
    async def get_template(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> ShiftTemplate | None:
        await self._require_employee(tenant_id, employee_id)
        return await self._repo.get_template_for_employee(tenant_id, employee_id)

    async def list_templates(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID | None = None
    ) -> list[ShiftTemplate]:
        return await self._repo.list_templates(tenant_id, branch_id)

    async def upsert_template(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
        weekdays: list[int],
        start_time: time,
        end_time: time,
        valid_from: date,
        valid_until: date | None = None,
        today: date | None = None,
    ) -> ShiftTemplate:
        employee = await self._require_employee(tenant_id, employee_id)
        if end_time <= start_time:
            raise ValidationError("La hora de fin debe ser posterior a la de inicio.")
        if not weekdays or any(d < 0 or d > 6 for d in weekdays):
            raise ValidationError("Los días de la semana son inválidos (0=Dom..6=Sáb).")
        if valid_until is not None and valid_until < valid_from:
            raise ValidationError("La vigencia final no puede ser anterior al inicio.")
        ref = today or date.today()
        existing = await self._repo.get_template_for_employee(tenant_id, employee_id)
        fields = {
            "weekdays": sorted(set(weekdays)),
            "start_time": start_time,
            "end_time": end_time,
            "valid_from": valid_from,
            "valid_until": valid_until,
        }
        if existing is not None and existing.id is not None:
            updated = await self._repo.update_template(
                tenant_id, existing.id, fields
            )
            assert updated is not None
            await self._regenerate(tenant_id, updated, effective=ref)
            refreshed = await self._repo.get_template_for_employee(
                tenant_id, employee_id
            )
            return refreshed if refreshed is not None else updated
        template = await self._repo.create_template(
            ShiftTemplate(
                tenant_id=tenant_id,
                branch_id=employee.branch_id,
                employee_id=employee_id,
                weekdays=sorted(set(weekdays)),
                start_time=start_time,
                end_time=end_time,
                valid_from=valid_from,
                valid_until=valid_until,
            )
        )
        await self._generate(tenant_id, template, through=ref + timedelta(days=_HORIZON_DAYS))
        refreshed = await self._repo.get_template_for_employee(tenant_id, employee_id)
        return refreshed if refreshed is not None else template

    async def extend_horizon(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
        today: date | None = None,
    ) -> ShiftTemplate:
        template = await self._repo.get_template_for_employee(tenant_id, employee_id)
        if template is None:
            raise NotFoundError("El empleado no tiene plantilla.")
        ref = today or date.today()
        base = template.generated_through or ref
        await self._generate(
            tenant_id, template, through=base + timedelta(days=_HORIZON_DAYS)
        )
        refreshed = await self._repo.get_template_for_employee(tenant_id, employee_id)
        return refreshed if refreshed is not None else template

    async def _generate(
        self, tenant_id: uuid.UUID, template: ShiftTemplate, through: date
    ) -> None:
        """Materialize scheduled/template shifts up to `through` (idempotent)."""
        start = template.valid_from
        if (
            template.generated_through is not None
            and template.generated_through >= start
        ):
            start = template.generated_through + timedelta(days=1)
        cap = through
        if template.valid_until is not None and cap > template.valid_until:
            cap = template.valid_until
        await self._fill(tenant_id, template, start, cap)
        new_through = through
        if template.valid_until is not None and new_through > template.valid_until:
            new_through = template.valid_until
        if (
            template.generated_through is None
            or new_through > template.generated_through
        ) and template.id is not None:
            await self._repo.update_template(
                tenant_id, template.id, {"generated_through": new_through}
            )

    async def _regenerate(
        self, tenant_id: uuid.UUID, template: ShiftTemplate, effective: date
    ) -> None:
        """Refill future scheduled shifts from `effective`, preserving resolved
        slots (day_off / covered / manual) and never touching past dates."""
        await self._repo.delete_template_shifts_from(
            tenant_id, template.employee_id, effective
        )
        horizon = effective + timedelta(days=_HORIZON_DAYS)
        target = template.generated_through or horizon
        if target < horizon:
            target = horizon
        if template.valid_until is not None and target > template.valid_until:
            target = template.valid_until
        await self._fill(tenant_id, template, effective, target)

    async def _fill(
        self,
        tenant_id: uuid.UUID,
        template: ShiftTemplate,
        date_from: date,
        date_to: date,
    ) -> None:
        d = date_from
        while d <= date_to:
            in_validity = d >= template.valid_from and (
                template.valid_until is None or d <= template.valid_until
            )
            if in_validity and _dow(d) in template.weekdays:
                existing = await self._repo.get_shift_for_slot(
                    tenant_id, template.employee_id, d
                )
                if existing is None:
                    await self._repo.create_planned_shift(
                        PlannedShift(
                            tenant_id=tenant_id,
                            branch_id=template.branch_id,
                            employee_id=template.employee_id,
                            shift_date=d,
                            start_time=template.start_time,
                            end_time=template.end_time,
                            status="scheduled",
                            origin="template",
                        )
                    )
            d += timedelta(days=1)

    # --- Time-off requests -------------------------------------------------
    async def create_time_off_request(
        self,
        tenant_id: uuid.UUID,
        employee_id: uuid.UUID,
        request_date: date,
        reason: str,
    ) -> TimeOffRequest:
        employee = await self._require_employee(tenant_id, employee_id)
        return await self._repo.create_time_off_request(
            TimeOffRequest(
                tenant_id=tenant_id,
                branch_id=employee.branch_id,
                employee_id=employee_id,
                request_date=request_date,
                reason=reason,
            )
        )

    async def list_time_off_requests(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[TimeOffRequest]:
        return await self._repo.list_time_off_requests(
            tenant_id, branch_id=branch_id, status=status
        )

    async def approve_time_off_request(
        self,
        tenant_id: uuid.UUID,
        request_id: uuid.UUID,
        decided_by: uuid.UUID,
        cover_employee_id: uuid.UUID | None = None,
    ) -> TimeOffRequest:
        request = await self._repo.get_time_off_request(tenant_id, request_id)
        if request is None:
            raise NotFoundError(f"Solicitud no encontrada: {request_id}")
        if request.status != "pending":
            raise ConflictError("La solicitud ya fue resuelta.")
        shift = await self._repo.get_shift_for_slot(
            tenant_id, request.employee_id, request.request_date
        )
        if shift is not None and shift.id is not None and shift.status == "scheduled":
            await self._repo.update_planned_shift(
                tenant_id, shift.id, {"status": "day_off", "note": request.reason}
            )
            if cover_employee_id is not None:
                covered = await self._repo.get_shift_for_slot(
                    tenant_id, request.employee_id, request.request_date
                )
                if covered is not None:
                    await self._create_coverage(tenant_id, covered, cover_employee_id)
        updated = await self._repo.update_time_off_request(
            tenant_id,
            request_id,
            {
                "status": "approved",
                "decided_by": decided_by,
                "decided_at": datetime.now(UTC),
            },
        )
        assert updated is not None
        return updated

    async def reject_time_off_request(
        self,
        tenant_id: uuid.UUID,
        request_id: uuid.UUID,
        decided_by: uuid.UUID,
        reason: str,
    ) -> TimeOffRequest:
        request = await self._repo.get_time_off_request(tenant_id, request_id)
        if request is None:
            raise NotFoundError(f"Solicitud no encontrada: {request_id}")
        if request.status != "pending":
            raise ConflictError("La solicitud ya fue resuelta.")
        updated = await self._repo.update_time_off_request(
            tenant_id,
            request_id,
            {
                "status": "rejected",
                "decided_by": decided_by,
                "decided_at": datetime.now(UTC),
                "note": reason,
            },
        )
        assert updated is not None
        return updated

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
