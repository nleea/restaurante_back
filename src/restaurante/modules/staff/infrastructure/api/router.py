"""Staff API: workforce management (employees, shifts, attendance, commissions).

Reads require `staff.read`; writes require `staff.manage` (RBAC). Every operation
is scoped to the tenant resolved by the subdomain middleware; branch-scoped
entities validate their `branch_id` against the tenant.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from restaurante.modules.identity.infrastructure.api.deps import (
    CurrentUserDep,
    require_permission,
)
from restaurante.modules.staff.infrastructure.api.deps import (
    StaffServiceDep,
    TenantDep,
)
from restaurante.modules.staff.infrastructure.api.schemas import (
    ApproveTimeOffRequest,
    AssignCoverageRequest,
    AttendanceResponse,
    CheckInRequest,
    CheckOutRequest,
    CommissionResponse,
    CreateCommissionRequest,
    CreateEmployeeRequest,
    CreatePlannedShiftRequest,
    CreateTimeOffRequestRequest,
    EmployeeResponse,
    MarkDayOffRequest,
    PlannedShiftResponse,
    RejectTimeOffRequest,
    ShiftTemplateResponse,
    TimeOffRequestResponse,
    UpdateEmployeeRoleRequest,
    UpdatePlannedShiftRequest,
    UpsertTemplateRequest,
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


# Authenticated-only self-service: an employee sees their own shifts and requests
# their own days off without needing `staff.read` / `staff.manage`.
@router.get("/employees/me/shifts", response_model=list[PlannedShiftResponse])
async def list_my_shifts(
    current_user: CurrentUserDep, service: StaffServiceDep, tenant_id: TenantDep
) -> list[PlannedShiftResponse]:
    employee = await service.get_employee_for_user(tenant_id, current_user.id)
    assert employee.id is not None
    shifts = await service.list_planned_shifts(tenant_id, employee.id)
    return [PlannedShiftResponse.model_validate(s, from_attributes=True) for s in shifts]


@router.post(
    "/employees/me/time-off-requests",
    response_model=TimeOffRequestResponse,
    status_code=201,
)
async def create_my_time_off_request(
    payload: CreateTimeOffRequestRequest,
    current_user: CurrentUserDep,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> TimeOffRequestResponse:
    employee = await service.get_employee_for_user(tenant_id, current_user.id)
    assert employee.id is not None
    request = await service.create_time_off_request(
        tenant_id, employee.id, payload.request_date, payload.reason
    )
    return TimeOffRequestResponse.model_validate(request, from_attributes=True)


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
        payload.note,
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


@router.get("/shifts", response_model=list[PlannedShiftResponse], dependencies=[_READ])
async def list_shifts_range(
    service: StaffServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID,
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
) -> list[PlannedShiftResponse]:
    shifts = await service.list_shifts_in_range(
        tenant_id, branch_id, date_from, date_to
    )
    return [PlannedShiftResponse.model_validate(s, from_attributes=True) for s in shifts]


@router.post(
    "/shifts/{shift_id}/day-off",
    response_model=PlannedShiftResponse,
    dependencies=[_WRITE],
)
async def mark_day_off(
    shift_id: uuid.UUID,
    payload: MarkDayOffRequest,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> PlannedShiftResponse:
    shift = await service.mark_day_off(
        tenant_id, shift_id, payload.reason, payload.cover_employee_id
    )
    return PlannedShiftResponse.model_validate(shift, from_attributes=True)


@router.post(
    "/shifts/{shift_id}/coverage",
    response_model=PlannedShiftResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def assign_coverage(
    shift_id: uuid.UUID,
    payload: AssignCoverageRequest,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> PlannedShiftResponse:
    shift = await service.assign_coverage(
        tenant_id, shift_id, payload.cover_employee_id
    )
    return PlannedShiftResponse.model_validate(shift, from_attributes=True)


@router.get(
    "/coverage", response_model=list[EmployeeResponse], dependencies=[_READ]
)
async def available_covers(
    service: StaffServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID,
    on_date: Annotated[date, Query(alias="date")],
) -> list[EmployeeResponse]:
    employees = await service.available_covers(tenant_id, branch_id, on_date)
    return [EmployeeResponse.model_validate(e, from_attributes=True) for e in employees]


# --- Shift templates --------------------------------------------------------
@router.put(
    "/employees/{employee_id}/template",
    response_model=ShiftTemplateResponse,
    dependencies=[_WRITE],
)
async def upsert_template(
    employee_id: uuid.UUID,
    payload: UpsertTemplateRequest,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> ShiftTemplateResponse:
    template = await service.upsert_template(
        tenant_id,
        employee_id,
        payload.weekdays,
        payload.start_time,
        payload.end_time,
        payload.valid_from,
        payload.valid_until,
    )
    return ShiftTemplateResponse.model_validate(template, from_attributes=True)


@router.get(
    "/employees/{employee_id}/template",
    response_model=ShiftTemplateResponse | None,
    dependencies=[_READ],
)
async def get_template(
    employee_id: uuid.UUID, service: StaffServiceDep, tenant_id: TenantDep
) -> ShiftTemplateResponse | None:
    template = await service.get_template(tenant_id, employee_id)
    if template is None:
        return None
    return ShiftTemplateResponse.model_validate(template, from_attributes=True)


@router.get(
    "/templates", response_model=list[ShiftTemplateResponse], dependencies=[_READ]
)
async def list_templates(
    service: StaffServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID | None = None,
) -> list[ShiftTemplateResponse]:
    templates = await service.list_templates(tenant_id, branch_id)
    return [
        ShiftTemplateResponse.model_validate(t, from_attributes=True) for t in templates
    ]


@router.post(
    "/employees/{employee_id}/template/extend",
    response_model=ShiftTemplateResponse,
    dependencies=[_WRITE],
)
async def extend_horizon(
    employee_id: uuid.UUID, service: StaffServiceDep, tenant_id: TenantDep
) -> ShiftTemplateResponse:
    template = await service.extend_horizon(tenant_id, employee_id)
    return ShiftTemplateResponse.model_validate(template, from_attributes=True)


# --- Time-off requests ------------------------------------------------------
@router.post(
    "/employees/{employee_id}/time-off-requests",
    response_model=TimeOffRequestResponse,
    status_code=201,
    dependencies=[_WRITE],
)
async def create_time_off_request(
    employee_id: uuid.UUID,
    payload: CreateTimeOffRequestRequest,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> TimeOffRequestResponse:
    request = await service.create_time_off_request(
        tenant_id, employee_id, payload.request_date, payload.reason
    )
    return TimeOffRequestResponse.model_validate(request, from_attributes=True)


@router.get(
    "/time-off-requests",
    response_model=list[TimeOffRequestResponse],
    dependencies=[_READ],
)
async def list_time_off_requests(
    service: StaffServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID | None = None,
    request_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[TimeOffRequestResponse]:
    requests = await service.list_time_off_requests(
        tenant_id, branch_id=branch_id, status=request_status
    )
    return [
        TimeOffRequestResponse.model_validate(r, from_attributes=True) for r in requests
    ]


@router.post(
    "/time-off-requests/{request_id}/approve",
    response_model=TimeOffRequestResponse,
    dependencies=[_WRITE],
)
async def approve_time_off_request(
    request_id: uuid.UUID,
    payload: ApproveTimeOffRequest,
    current_user: CurrentUserDep,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> TimeOffRequestResponse:
    request = await service.approve_time_off_request(
        tenant_id, request_id, current_user.id, payload.cover_employee_id
    )
    return TimeOffRequestResponse.model_validate(request, from_attributes=True)


@router.post(
    "/time-off-requests/{request_id}/reject",
    response_model=TimeOffRequestResponse,
    dependencies=[_WRITE],
)
async def reject_time_off_request(
    request_id: uuid.UUID,
    payload: RejectTimeOffRequest,
    current_user: CurrentUserDep,
    service: StaffServiceDep,
    tenant_id: TenantDep,
) -> TimeOffRequestResponse:
    request = await service.reject_time_off_request(
        tenant_id, request_id, current_user.id, payload.reason
    )
    return TimeOffRequestResponse.model_validate(request, from_attributes=True)


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
