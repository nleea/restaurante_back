"""Reports API: read-only finance aggregation. All reads require `finance.read`."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from restaurante.modules.identity.infrastructure.api.deps import require_permission
from restaurante.modules.reports.infrastructure.api.deps import (
    ReportsServiceDep,
    TenantDep,
)
from restaurante.modules.reports.infrastructure.api.schemas import (
    CashFlowSummaryResponse,
    CogsSummaryResponse,
    DailyPointResponse,
    ManagerCostKpisResponse,
    ProductMarginReportResponse,
    ProfitAndLossResponse,
    RevenueSummaryResponse,
    TopProductResponse,
    ZReportResponse,
)

router = APIRouter(prefix="/reports", tags=["reports"])

_READ = Depends(require_permission("finance.read"))

FromDep = Annotated[date, Query(alias="from")]
ToDep = Annotated[date, Query(alias="to")]


@router.get("/z/{cash_session_id}", response_model=ZReportResponse, dependencies=[_READ])
async def z_report(
    cash_session_id: uuid.UUID,
    service: ReportsServiceDep,
    tenant_id: TenantDep,
) -> ZReportResponse:
    report = await service.z_report(tenant_id, cash_session_id)
    return ZReportResponse.model_validate(report, from_attributes=True)


@router.get("/revenue", response_model=RevenueSummaryResponse, dependencies=[_READ])
async def revenue_summary(
    service: ReportsServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID,
    date_from: FromDep,
    date_to: ToDep,
    cashier_employee_id: uuid.UUID | None = None,
) -> RevenueSummaryResponse:
    summary = await service.revenue_summary(
        tenant_id, branch_id, date_from, date_to, cashier_employee_id
    )
    return RevenueSummaryResponse.model_validate(summary, from_attributes=True)


@router.get("/daily", response_model=list[DailyPointResponse], dependencies=[_READ])
async def daily_series(
    service: ReportsServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID,
    date_from: FromDep,
    date_to: ToDep,
) -> list[DailyPointResponse]:
    points = await service.daily_series(tenant_id, branch_id, date_from, date_to)
    return [DailyPointResponse.model_validate(p, from_attributes=True) for p in points]


@router.get(
    "/top-products", response_model=list[TopProductResponse], dependencies=[_READ]
)
async def top_products(
    service: ReportsServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID,
    date_from: FromDep,
    date_to: ToDep,
    limit: int = 5,
) -> list[TopProductResponse]:
    products = await service.top_products(
        tenant_id, branch_id, date_from, date_to, limit
    )
    return [TopProductResponse.model_validate(p, from_attributes=True) for p in products]


@router.get("/cogs", response_model=CogsSummaryResponse, dependencies=[_READ])
async def cogs_summary(
    service: ReportsServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID,
    date_from: FromDep,
    date_to: ToDep,
) -> CogsSummaryResponse:
    summary = await service.cogs_summary(tenant_id, branch_id, date_from, date_to)
    return CogsSummaryResponse.model_validate(summary, from_attributes=True)


@router.get("/pl", response_model=ProfitAndLossResponse, dependencies=[_READ])
async def profit_and_loss(
    service: ReportsServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID,
    date_from: FromDep,
    date_to: ToDep,
) -> ProfitAndLossResponse:
    pl = await service.profit_and_loss(tenant_id, branch_id, date_from, date_to)
    return ProfitAndLossResponse.model_validate(pl, from_attributes=True)


@router.get("/cost-kpis", response_model=ManagerCostKpisResponse, dependencies=[_READ])
async def cost_kpis(
    service: ReportsServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID,
    date_from: FromDep,
    date_to: ToDep,
) -> ManagerCostKpisResponse:
    kpis = await service.cost_kpis(tenant_id, branch_id, date_from, date_to)
    return ManagerCostKpisResponse.model_validate(kpis, from_attributes=True)


@router.get(
    "/product-margins",
    response_model=ProductMarginReportResponse,
    dependencies=[_READ],
)
async def product_margins(
    service: ReportsServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID,
    date_from: FromDep,
    date_to: ToDep,
    limit: int = 5,
) -> ProductMarginReportResponse:
    report = await service.product_margins(
        tenant_id, branch_id, date_from, date_to, limit
    )
    return ProductMarginReportResponse.model_validate(report, from_attributes=True)


@router.get("/cash-flow", response_model=CashFlowSummaryResponse, dependencies=[_READ])
async def cash_flow(
    service: ReportsServiceDep,
    tenant_id: TenantDep,
    branch_id: uuid.UUID,
    date_from: FromDep,
    date_to: ToDep,
) -> CashFlowSummaryResponse:
    summary = await service.cash_flow(tenant_id, branch_id, date_from, date_to)
    return CashFlowSummaryResponse.model_validate(summary, from_attributes=True)
