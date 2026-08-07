"""Cash API: cash-register sessions (open/close arqueo) + movement ledger.

RBAC: reads `cash.read`; open `cash.open`; close `cash.close`; movements
`cash.move`. The orders→cash payment integration is out of scope.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from restaurante.modules.cash.infrastructure.api.deps import (
    CashServiceDep,
    ReportsServiceDep,
    TenantDep,
)
from restaurante.modules.cash.infrastructure.api.schemas import (
    CashMovementResponse,
    CashSessionResponse,
    CashShiftSummaryResponse,
    CashSummaryChannelLine,
    CashSummaryPaymentLine,
    CloseSessionRequest,
    OpenSessionRequest,
    RegisterMovementRequest,
    ShiftPendingSummaryResponse,
)
from restaurante.modules.identity.infrastructure.api.deps import require_permission

router = APIRouter(prefix="/cash", tags=["cash"])

_READ = Depends(require_permission("cash.read"))
_OPEN = Depends(require_permission("cash.open"))
_CLOSE = Depends(require_permission("cash.close"))
_MOVE = Depends(require_permission("cash.move"))


# --- Sessions ---------------------------------------------------------------
@router.post(
    "/sessions", response_model=CashSessionResponse, status_code=201, dependencies=[_OPEN]
)
async def open_session(
    payload: OpenSessionRequest, service: CashServiceDep, tenant_id: TenantDep
) -> CashSessionResponse:
    session = await service.open_session(
        tenant_id,
        payload.branch_id,
        payload.opened_by_employee_id,
        payload.opening_amount,
    )
    return CashSessionResponse.model_validate(session, from_attributes=True)


@router.get(
    "/sessions", response_model=list[CashSessionResponse], dependencies=[_READ]
)
async def list_sessions(
    branch_id: uuid.UUID,
    service: CashServiceDep,
    tenant_id: TenantDep,
    status_filter: str | None = None,
) -> list[CashSessionResponse]:
    sessions = await service.list_sessions(
        tenant_id, branch_id, status=status_filter
    )
    return [
        CashSessionResponse.model_validate(s, from_attributes=True) for s in sessions
    ]


@router.get(
    "/branches/{branch_id}/open-session",
    response_model=CashSessionResponse,
    dependencies=[_READ],
)
async def get_open_session(
    branch_id: uuid.UUID, service: CashServiceDep, tenant_id: TenantDep
) -> CashSessionResponse:
    session = await service.get_open_session(tenant_id, branch_id)
    return CashSessionResponse.model_validate(session, from_attributes=True)


@router.get(
    "/sessions/{session_id}",
    response_model=CashSessionResponse,
    dependencies=[_READ],
)
async def get_session(
    session_id: uuid.UUID, service: CashServiceDep, tenant_id: TenantDep
) -> CashSessionResponse:
    session = await service.get_session(tenant_id, session_id)
    return CashSessionResponse.model_validate(session, from_attributes=True)


@router.post(
    "/sessions/{session_id}/close",
    response_model=CashSessionResponse,
    dependencies=[_CLOSE],
)
async def close_session(
    session_id: uuid.UUID,
    payload: CloseSessionRequest,
    service: CashServiceDep,
    tenant_id: TenantDep,
) -> CashSessionResponse:
    session = await service.close_session(
        tenant_id,
        session_id,
        payload.closed_by_employee_id,
        payload.counted_amount,
        notes=payload.notes,
        incident=payload.incident,
        incident_note=payload.incident_note,
    )
    return CashSessionResponse.model_validate(session, from_attributes=True)


# --- Movements --------------------------------------------------------------
@router.post(
    "/sessions/{session_id}/movements",
    response_model=CashMovementResponse,
    status_code=201,
    dependencies=[_MOVE],
)
async def register_movement(
    session_id: uuid.UUID,
    payload: RegisterMovementRequest,
    service: CashServiceDep,
    tenant_id: TenantDep,
) -> CashMovementResponse:
    movement = await service.register_movement(
        tenant_id,
        session_id,
        payload.type,
        payload.concept,
        payload.amount,
        payload.method,
        payload.reference_id,
        category=payload.category,
    )
    return CashMovementResponse.model_validate(movement, from_attributes=True)


@router.get(
    "/sessions/{session_id}/movements",
    response_model=list[CashMovementResponse],
    dependencies=[_READ],
)
async def list_movements(
    session_id: uuid.UUID, service: CashServiceDep, tenant_id: TenantDep
) -> list[CashMovementResponse]:
    movements = await service.list_movements(tenant_id, session_id)
    return [
        CashMovementResponse.model_validate(m, from_attributes=True) for m in movements
    ]


# --- Live shift summary -----------------------------------------------------
async def _shift_summary(
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    cash_service: CashServiceDep,
    reports_service: ReportsServiceDep,
) -> CashShiftSummaryResponse:
    session = await cash_service.get_session(tenant_id, session_id)
    expected = await cash_service.expected_cash(tenant_id, session_id)
    z = await reports_service.z_report(tenant_id, session_id)
    return CashShiftSummaryResponse(
        cash_session_id=session_id,
        status=session.status,
        sales_total=z.gross_sales,
        tickets=z.gross_tickets,
        avg_ticket=z.avg_ticket,
        channels=[
            CashSummaryChannelLine(
                channel=c.channel, amount=c.amount, tickets=c.tickets
            )
            for c in z.channels
        ],
        payments=[
            CashSummaryPaymentLine(method=p.method, amount=p.amount)
            for p in z.payments
        ],
        withdrawals=z.withdrawals,
        expected_cash=expected,
    )


@router.get(
    "/sessions/{session_id}/summary",
    response_model=CashShiftSummaryResponse,
    dependencies=[_READ],
)
async def get_session_summary(
    session_id: uuid.UUID,
    cash_service: CashServiceDep,
    reports_service: ReportsServiceDep,
    tenant_id: TenantDep,
) -> CashShiftSummaryResponse:
    return await _shift_summary(
        tenant_id, session_id, cash_service, reports_service
    )


@router.get(
    "/sessions/{session_id}/pending",
    response_model=ShiftPendingSummaryResponse,
    dependencies=[_READ],
)
async def get_session_pending(
    session_id: uuid.UUID,
    reports_service: ReportsServiceDep,
    tenant_id: TenantDep,
) -> ShiftPendingSummaryResponse:
    """Advisory pre-close summary: uncollected orders + undelivered deliveries this shift."""
    summary = await reports_service.pending_summary(tenant_id, session_id)
    return ShiftPendingSummaryResponse(
        cash_session_id=session_id,
        uncollected_count=summary.uncollected_count,
        uncollected_total=summary.uncollected_total,
        undelivered_count=summary.undelivered_count,
    )


@router.get(
    "/branches/{branch_id}/open-session/summary",
    response_model=CashShiftSummaryResponse,
    dependencies=[_READ],
)
async def get_open_session_summary(
    branch_id: uuid.UUID,
    cash_service: CashServiceDep,
    reports_service: ReportsServiceDep,
    tenant_id: TenantDep,
) -> CashShiftSummaryResponse:
    session = await cash_service.get_open_session(tenant_id, branch_id)
    assert session.id is not None
    return await _shift_summary(
        tenant_id, session.id, cash_service, reports_service
    )
