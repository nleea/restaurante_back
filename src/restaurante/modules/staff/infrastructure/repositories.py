"""Persistence adapter for the Staff module over SQLAlchemy async.

Each write method commits its own unit of work (admin actions are atomic) and
filters explicitly by ``tenant_id`` (and ``branch_id`` where applicable) as
defense in depth on top of the automatic tenancy filter. Uniqueness violations
are translated to ``ConflictError``.
"""

from __future__ import annotations

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
)
from restaurante.modules.staff.infrastructure.models import (
    AttendanceModel,
    CommissionModel,
    EmployeeModel,
    PlannedShiftModel,
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
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _shift(model)

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
