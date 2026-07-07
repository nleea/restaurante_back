"""Persistence adapter for the Staff module over SQLAlchemy async.

Each write method commits its own unit of work (admin actions are atomic) and
filters explicitly by ``tenant_id`` (and ``branch_id`` where applicable) as
defense in depth on top of the automatic tenancy filter. Uniqueness violations
are translated to ``ConflictError``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.identity.infrastructure.models import (
    PersonModel,
    RoleModel,
    UserModel,
)
from restaurante.modules.staff.domain.entities import (
    Attendance,
    Commission,
    Employee,
    PlannedShift,
    ShiftTemplate,
    TimeOffRequest,
)
from restaurante.modules.staff.infrastructure.models import (
    AttendanceModel,
    CommissionModel,
    EmployeeModel,
    PlannedShiftModel,
    ShiftTemplateModel,
    TimeOffRequestModel,
)
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.tenancy.models import BranchModel


def _employee(m: EmployeeModel) -> Employee:
    return Employee(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        person_id=m.person_id,
        user_id=m.user_id,
        role_id=m.role_id,
        hired_at=m.hired_at,
        is_active=m.is_active,
    )


def _shift(m: PlannedShiftModel) -> PlannedShift:
    return PlannedShift(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        employee_id=m.employee_id,
        shift_date=m.shift_date,
        start_time=m.start_time,
        end_time=m.end_time,
        status=m.status,
        origin=m.origin,
        covered_by_employee_id=m.covered_by_employee_id,
        note=m.note,
    )


def _template(m: ShiftTemplateModel) -> ShiftTemplate:
    return ShiftTemplate(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        employee_id=m.employee_id,
        weekdays=list(m.weekdays),
        start_time=m.start_time,
        end_time=m.end_time,
        valid_from=m.valid_from,
        valid_until=m.valid_until,
        generated_through=m.generated_through,
    )


def _request(m: TimeOffRequestModel) -> TimeOffRequest:
    return TimeOffRequest(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        employee_id=m.employee_id,
        request_date=m.request_date,
        reason=m.reason,
        status=m.status,
        decided_by=m.decided_by,
        decided_at=m.decided_at,
        note=m.note,
    )


def _attendance(m: AttendanceModel) -> Attendance:
    return Attendance(
        id=m.id,
        tenant_id=m.tenant_id,
        employee_id=m.employee_id,
        check_in_at=m.check_in_at,
        planned_shift_id=m.planned_shift_id,
        check_out_at=m.check_out_at,
    )


def _commission(m: CommissionModel) -> Commission:
    return Commission(
        id=m.id,
        tenant_id=m.tenant_id,
        employee_id=m.employee_id,
        type=m.type,
        amount=m.amount,
        occurred_at=m.occurred_at,
        reference_id=m.reference_id,
    )


class SqlAlchemyStaffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reference existence checks ----------------------------------------
    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def person_exists(self, person_id: uuid.UUID) -> bool:
        stmt = select(PersonModel.id).where(PersonModel.id == person_id)
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def user_exists(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        stmt = select(UserModel.id).where(
            UserModel.id == user_id, UserModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def role_exists(self, tenant_id: uuid.UUID, role_id: uuid.UUID) -> bool:
        stmt = select(RoleModel.id).where(
            RoleModel.id == role_id,
            or_(RoleModel.tenant_id == tenant_id, RoleModel.is_global.is_(True)),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Employees ---------------------------------------------------------
    async def create_employee(self, employee: Employee) -> Employee:
        model = EmployeeModel(
            tenant_id=employee.tenant_id,
            branch_id=employee.branch_id,
            person_id=employee.person_id,
            user_id=employee.user_id,
            role_id=employee.role_id,
            is_active=employee.is_active,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "Ya existe un empleado para esa persona o ese usuario."
            ) from exc
        await self._session.refresh(model)
        return _employee(model)

    async def _get_employee_model(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> EmployeeModel | None:
        stmt = select(EmployeeModel).where(
            EmployeeModel.id == employee_id, EmployeeModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> Employee | None:
        model = await self._get_employee_model(tenant_id, employee_id)
        return _employee(model) if model else None

    async def find_employee_by_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> Employee | None:
        stmt = select(EmployeeModel).where(
            EmployeeModel.tenant_id == tenant_id,
            EmployeeModel.user_id == user_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _employee(model) if model else None

    async def employee_exists_for_person(
        self, tenant_id: uuid.UUID, person_id: uuid.UUID
    ) -> bool:
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.tenant_id == tenant_id,
            EmployeeModel.person_id == person_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def employee_exists_for_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.tenant_id == tenant_id,
            EmployeeModel.user_id == user_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def list_employees(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        active: bool | None = None,
    ) -> list[Employee]:
        stmt = select(EmployeeModel).where(EmployeeModel.tenant_id == tenant_id)
        if branch_id is not None:
            stmt = stmt.where(EmployeeModel.branch_id == branch_id)
        if active is not None:
            stmt = stmt.where(EmployeeModel.is_active.is_(active))
        stmt = stmt.order_by(EmployeeModel.hired_at)
        return [_employee(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID, fields: dict[str, Any]
    ) -> Employee | None:
        model = await self._get_employee_model(tenant_id, employee_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _employee(model)

    # --- Planned shifts ----------------------------------------------------
    async def create_planned_shift(self, shift: PlannedShift) -> PlannedShift:
        model = PlannedShiftModel(
            tenant_id=shift.tenant_id,
            branch_id=shift.branch_id,
            employee_id=shift.employee_id,
            shift_date=shift.shift_date,
            start_time=shift.start_time,
            end_time=shift.end_time,
            status=shift.status,
            origin=shift.origin,
            covered_by_employee_id=shift.covered_by_employee_id,
            note=shift.note,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "Ya existe un turno para ese empleado en esa fecha."
            ) from exc
        await self._session.refresh(model)
        return _shift(model)

    async def get_shift_for_slot(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID, shift_date: dt.date
    ) -> PlannedShift | None:
        stmt = select(PlannedShiftModel).where(
            PlannedShiftModel.tenant_id == tenant_id,
            PlannedShiftModel.employee_id == employee_id,
            PlannedShiftModel.shift_date == shift_date,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _shift(model) if model else None

    async def list_shifts_in_range(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[PlannedShift]:
        stmt = (
            select(PlannedShiftModel)
            .where(
                PlannedShiftModel.tenant_id == tenant_id,
                PlannedShiftModel.branch_id == branch_id,
                PlannedShiftModel.shift_date >= date_from,
                PlannedShiftModel.shift_date <= date_to,
            )
            .order_by(PlannedShiftModel.shift_date, PlannedShiftModel.start_time)
        )
        return [_shift(m) for m in (await self._session.execute(stmt)).scalars()]

    async def delete_template_shifts_from(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID, from_date: dt.date
    ) -> None:
        await self._session.execute(
            sql_delete(PlannedShiftModel).where(
                PlannedShiftModel.tenant_id == tenant_id,
                PlannedShiftModel.employee_id == employee_id,
                PlannedShiftModel.shift_date >= from_date,
                PlannedShiftModel.status == "scheduled",
                PlannedShiftModel.origin == "template",
            )
        )
        await self._session.commit()

    async def _get_shift_model(
        self, tenant_id: uuid.UUID, shift_id: uuid.UUID
    ) -> PlannedShiftModel | None:
        stmt = select(PlannedShiftModel).where(
            PlannedShiftModel.id == shift_id,
            PlannedShiftModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_planned_shift(
        self, tenant_id: uuid.UUID, shift_id: uuid.UUID
    ) -> PlannedShift | None:
        model = await self._get_shift_model(tenant_id, shift_id)
        return _shift(model) if model else None

    async def list_planned_shifts(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[PlannedShift]:
        stmt = (
            select(PlannedShiftModel)
            .where(
                PlannedShiftModel.tenant_id == tenant_id,
                PlannedShiftModel.employee_id == employee_id,
            )
            .order_by(PlannedShiftModel.shift_date, PlannedShiftModel.start_time)
        )
        return [_shift(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_planned_shift(
        self, tenant_id: uuid.UUID, shift_id: uuid.UUID, fields: dict[str, Any]
    ) -> PlannedShift | None:
        model = await self._get_shift_model(tenant_id, shift_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _shift(model)

    async def delete_planned_shift(
        self, tenant_id: uuid.UUID, shift_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_delete(PlannedShiftModel).where(
                PlannedShiftModel.tenant_id == tenant_id,
                PlannedShiftModel.id == shift_id,
            )
        )
        await self._session.commit()

    # --- Attendances -------------------------------------------------------
    async def create_attendance(self, attendance: Attendance) -> Attendance:
        model = AttendanceModel(
            tenant_id=attendance.tenant_id,
            employee_id=attendance.employee_id,
            planned_shift_id=attendance.planned_shift_id,
            check_in_at=attendance.check_in_at,
            check_out_at=attendance.check_out_at,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _attendance(model)

    async def _get_attendance_model(
        self, tenant_id: uuid.UUID, attendance_id: uuid.UUID
    ) -> AttendanceModel | None:
        stmt = select(AttendanceModel).where(
            AttendanceModel.id == attendance_id,
            AttendanceModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_attendance(
        self, tenant_id: uuid.UUID, attendance_id: uuid.UUID
    ) -> Attendance | None:
        model = await self._get_attendance_model(tenant_id, attendance_id)
        return _attendance(model) if model else None

    async def get_open_attendance(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> Attendance | None:
        stmt = select(AttendanceModel).where(
            AttendanceModel.tenant_id == tenant_id,
            AttendanceModel.employee_id == employee_id,
            AttendanceModel.check_out_at.is_(None),
        )
        model = (await self._session.execute(stmt)).scalars().first()
        return _attendance(model) if model else None

    async def list_attendances(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[Attendance]:
        stmt = (
            select(AttendanceModel)
            .where(
                AttendanceModel.tenant_id == tenant_id,
                AttendanceModel.employee_id == employee_id,
            )
            .order_by(AttendanceModel.check_in_at.desc())
        )
        return [_attendance(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_attendance(
        self, tenant_id: uuid.UUID, attendance_id: uuid.UUID, fields: dict[str, Any]
    ) -> Attendance | None:
        model = await self._get_attendance_model(tenant_id, attendance_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _attendance(model)

    # --- Commissions -------------------------------------------------------
    async def create_commission(self, commission: Commission) -> Commission:
        model = CommissionModel(
            tenant_id=commission.tenant_id,
            employee_id=commission.employee_id,
            type=commission.type,
            amount=commission.amount,
            reference_id=commission.reference_id,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _commission(model)

    async def list_commissions(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[Commission]:
        stmt = (
            select(CommissionModel)
            .where(
                CommissionModel.tenant_id == tenant_id,
                CommissionModel.employee_id == employee_id,
            )
            .order_by(CommissionModel.occurred_at.desc())
        )
        return [_commission(m) for m in (await self._session.execute(stmt)).scalars()]

    # --- Shift templates ---------------------------------------------------
    async def create_template(self, template: ShiftTemplate) -> ShiftTemplate:
        model = ShiftTemplateModel(
            tenant_id=template.tenant_id,
            branch_id=template.branch_id,
            employee_id=template.employee_id,
            weekdays=template.weekdays,
            start_time=template.start_time,
            end_time=template.end_time,
            valid_from=template.valid_from,
            valid_until=template.valid_until,
            generated_through=template.generated_through,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "Ese empleado ya tiene una plantilla."
            ) from exc
        await self._session.refresh(model)
        return _template(model)

    async def get_template_for_employee(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> ShiftTemplate | None:
        stmt = select(ShiftTemplateModel).where(
            ShiftTemplateModel.tenant_id == tenant_id,
            ShiftTemplateModel.employee_id == employee_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _template(model) if model else None

    async def list_templates(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID | None = None
    ) -> list[ShiftTemplate]:
        stmt = select(ShiftTemplateModel).where(
            ShiftTemplateModel.tenant_id == tenant_id
        )
        if branch_id is not None:
            stmt = stmt.where(ShiftTemplateModel.branch_id == branch_id)
        return [_template(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_template(
        self, tenant_id: uuid.UUID, template_id: uuid.UUID, fields: dict[str, Any]
    ) -> ShiftTemplate | None:
        stmt = select(ShiftTemplateModel).where(
            ShiftTemplateModel.id == template_id,
            ShiftTemplateModel.tenant_id == tenant_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _template(model)

    # --- Time-off requests -------------------------------------------------
    async def create_time_off_request(
        self, request: TimeOffRequest
    ) -> TimeOffRequest:
        model = TimeOffRequestModel(
            tenant_id=request.tenant_id,
            branch_id=request.branch_id,
            employee_id=request.employee_id,
            request_date=request.request_date,
            reason=request.reason,
            status=request.status,
            decided_by=request.decided_by,
            decided_at=request.decided_at,
            note=request.note,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _request(model)

    async def get_time_off_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID
    ) -> TimeOffRequest | None:
        stmt = select(TimeOffRequestModel).where(
            TimeOffRequestModel.id == request_id,
            TimeOffRequestModel.tenant_id == tenant_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _request(model) if model else None

    async def list_time_off_requests(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[TimeOffRequest]:
        stmt = select(TimeOffRequestModel).where(
            TimeOffRequestModel.tenant_id == tenant_id
        )
        if branch_id is not None:
            stmt = stmt.where(TimeOffRequestModel.branch_id == branch_id)
        if status is not None:
            stmt = stmt.where(TimeOffRequestModel.status == status)
        stmt = stmt.order_by(TimeOffRequestModel.created_at.desc())
        return [_request(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_time_off_request(
        self, tenant_id: uuid.UUID, request_id: uuid.UUID, fields: dict[str, Any]
    ) -> TimeOffRequest | None:
        stmt = select(TimeOffRequestModel).where(
            TimeOffRequestModel.id == request_id,
            TimeOffRequestModel.tenant_id == tenant_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _request(model)
