"""Staff API: workforce management (employees, shifts, attendance, commissions).

Reads require `staff.read`; writes require `staff.manage` (RBAC). Every operation
is scoped to the tenant resolved by the subdomain middleware; branch-scoped
entities validate their `branch_id` against the tenant.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from restaurante.modules.identity.infrastructure.api.deps import (
    CurrentUserDep,
    require_permission,
)
from restaurante.modules.staff.infrastructure.api.deps import (
    StaffServiceDep,
    TenantDep,
)
from restaurante.modules.staff.infrastructure.api.schemas import (
    AttendanceResponse,
    CheckInRequest,
    CheckOutRequest,
    CommissionResponse,
    CreateCommissionRequest,
    CreateEmployeeRequest,
    CreatePlannedShiftRequest,
    EmployeeResponse,
    PlannedShiftResponse,
    UpdateEmployeeRoleRequest,
    UpdatePlannedShiftRequest,
)

router = APIRouter(prefix="/staff", tags=["staff"])

_READ = Depends(require_permission("staff.read"))
_WRITE = Depends(require_permission("staff.manage"))
_NO_CONTENT = status.HTTP_204_NO_CONTENT


# --- Employees --------------------------------------------------------------
@router.post(
    "/employees", response_model=EmployeeResponse, status_code=201, dependencies=[_WRITE]
)
async def create_employee(
    payload: CreateEmployeeRequest, service: StaffServiceDep, tenant_id: TenantDep
) -> EmployeeResponse:
    employee = await service.create_employee(
        tenant_id,
        payload.branch_id,
        payload.person_id,
        payload.user_id,
        payload.role_id,
    )
    return EmployeeResponse.model_validate(employee, from_attributes=True)


@router.get("/employees", response_model=list[EmployeeResponse], dependencies=[_READ])
async def list_employees(
    service: StaffServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID | None = None,
    active: bool | None = None,
) -> list[EmployeeResponse]:
    employees = await service.list_employees(
        tenant_id, branch_id=branch_id, active=active
    )
    return [EmployeeResponse.model_validate(e, from_attributes=True) for e in employees]


# Declared before `/employees/{employee_id}` so "me" is not parsed as a UUID.
# Authenticated-only (no `staff.read`): an order-taker must resolve their own employee.
@router.get("/employees/me", response_model=EmployeeResponse)
async def get_my_employee(
    current_user: CurrentUserDep,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> EmployeeResponse:
    employee = await service.get_employee_for_user(tenant_id, current_user.id)
    return EmployeeResponse.model_validate(employee, from_attributes=True)


@router.get(
    "/employees/{employee_id}", response_model=EmployeeResponse, dependencies=[_READ]
)
async def get_employee(
    employee_id: uuid.UUID, service: StaffServiceDep, tenant_id: TenantDep
) -> EmployeeResponse:
    employee = await service.get_employee(tenant_id, employee_id)
    return EmployeeResponse.model_validate(employee, from_attributes=True)


@router.patch(
    "/employees/{employee_id}/role",
    response_model=EmployeeResponse,
    dependencies=[_WRITE],
)
async def update_employee_role(
    employee_id: uuid.UUID,
    payload: UpdateEmployeeRoleRequest,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> EmployeeResponse:
    employee = await service.update_employee_role(
        tenant_id, employee_id, payload.role_id
    )
    return EmployeeResponse.model_validate(employee, from_attributes=True)


@router.delete(
    "/employees/{employee_id}", response_model=EmployeeResponse, dependencies=[_WRITE]
)
async def deactivate_employee(
    employee_id: uuid.UUID, service: StaffServiceDep, tenant_id: TenantDep
) -> EmployeeResponse:
    employee = await service.deactivate_employee(tenant_id, employee_id)
    return EmployeeResponse.model_validate(employee, from_attributes=True)


# --- Planned shifts ---------------------------------------------------------
@router.post(
    "/employees/{employee_id}/shifts",
    response_model=PlannedShiftResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def create_planned_shift(
    employee_id: uuid.UUID,
    payload: CreatePlannedShiftRequest,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> PlannedShiftResponse:
    shift = await service.create_planned_shift(
        tenant_id,
        employee_id,
        payload.shift_date,
        payload.start_time,
        payload.end_time,
    )
    return PlannedShiftResponse.model_validate(shift, from_attributes=True)


@router.get(
    "/employees/{employee_id}/shifts",
    response_model=list[PlannedShiftResponse],
    dependencies=[_READ],
)
async def list_planned_shifts(
    employee_id: uuid.UUID, service: StaffServiceDep, tenant_id: TenantDep
) -> list[PlannedShiftResponse]:
    shifts = await service.list_planned_shifts(tenant_id, employee_id)
    return [PlannedShiftResponse.model_validate(s, from_attributes=True) for s in shifts]


@router.patch(
    "/shifts/{shift_id}", response_model=PlannedShiftResponse, dependencies=[_WRITE]
)
async def update_planned_shift(
    shift_id: uuid.UUID,
    payload: UpdatePlannedShiftRequest,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> PlannedShiftResponse:
    shift = await service.update_planned_shift(
        tenant_id, shift_id, payload.model_dump(exclude_unset=True)
    )
    return PlannedShiftResponse.model_validate(shift, from_attributes=True)


@router.delete("/shifts/{shift_id}", status_code=_NO_CONTENT, dependencies=[_WRITE])
async def delete_planned_shift(
    shift_id: uuid.UUID, service: StaffServiceDep, tenant_id: TenantDep
) -> Response:
    await service.delete_planned_shift(tenant_id, shift_id)
    return Response(status_code=_NO_CONTENT)


# --- Attendances ------------------------------------------------------------
@router.post(
    "/employees/{employee_id}/attendances",
    response_model=AttendanceResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def check_in(
    employee_id: uuid.UUID,
    payload: CheckInRequest,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> AttendanceResponse:
    attendance = await service.check_in(
        tenant_id, employee_id, payload.check_in_at, payload.planned_shift_id
    )
    return AttendanceResponse.model_validate(attendance, from_attributes=True)


@router.get(
    "/employees/{employee_id}/attendances",
    response_model=list[AttendanceResponse],
    dependencies=[_READ],
)
async def list_attendances(
    employee_id: uuid.UUID, service: StaffServiceDep, tenant_id: TenantDep
) -> list[AttendanceResponse]:
    items = await service.list_attendances(tenant_id, employee_id)
    return [AttendanceResponse.model_validate(a, from_attributes=True) for a in items]


@router.patch(
    "/attendances/{attendance_id}",
    response_model=AttendanceResponse,
    dependencies=[_WRITE],
)
async def check_out(
    attendance_id: uuid.UUID,
    payload: CheckOutRequest,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> AttendanceResponse:
    attendance = await service.check_out(
        tenant_id, attendance_id, payload.check_out_at
    )
    return AttendanceResponse.model_validate(attendance, from_attributes=True)


# --- Commissions ------------------------------------------------------------
@router.post(
    "/employees/{employee_id}/commissions",
    response_model=CommissionResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def create_commission(
    employee_id: uuid.UUID,
    payload: CreateCommissionRequest,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> CommissionResponse:
    commission = await service.create_commission(
        tenant_id, employee_id, payload.type, payload.amount, payload.reference_id
    )
    return CommissionResponse.model_validate(commission, from_attributes=True)


@router.get(
    "/employees/{employee_id}/commissions",
    response_model=list[CommissionResponse],
    dependencies=[_READ],
)
async def list_commissions(
    employee_id: uuid.UUID, service: StaffServiceDep, tenant_id: TenantDep
) -> list[CommissionResponse]:
    items = await service.list_commissions(tenant_id, employee_id)
    return [CommissionResponse.model_validate(c, from_attributes=True) for c in items]
