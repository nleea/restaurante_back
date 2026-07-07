"""Pydantic schemas for the reports API."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ZChannelLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    channel: str
    amount: Decimal
    tickets: int


class ZPaymentLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    method: str
    amount: Decimal


class RevenueSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    total: Decimal
    tickets: int
    avg_ticket: Decimal
    discounts: Decimal
    returns: Decimal
    return_count: int
    net: Decimal
    channels: list[ZChannelLineResponse]
    payments: list[ZPaymentLineResponse]


class DailyPointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    day: str
    income: Decimal
    expenses: Decimal


class TopProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    variant_id: uuid.UUID
    name: str | None = None
    units: int
    revenue: Decimal


class ChannelCogsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    channel: str
    cogs: Decimal


class CogsSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    cogs: Decimal
    partial: bool
    priced_variants: int
    unpriced_variants: int
    channels: list[ChannelCogsResponse]


class ChannelMarginResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    channel: str
    revenue: Decimal
    cogs: Decimal
    margin: Decimal
    margin_pct: Decimal


class ProfitAndLossResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    revenue: Decimal
    cogs: Decimal
    cogs_partial: bool
    gross_profit: Decimal
    gross_margin_pct: Decimal
    operating_expenses: Decimal
    ebitda: Decimal
    ebitda_margin_pct: Decimal
    estimated_taxes: Decimal
    taxes_estimated: bool = True
    net_profit: Decimal
    net_margin_pct: Decimal
    contribution_margin_pct: Decimal
    break_even_revenue: Decimal | None = None
    channels: list[ChannelMarginResponse]


class ManagerCostKpisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    revenue: Decimal
    food_cost_pct: Decimal | None = None
    labor_cost: Decimal | None = None
    labor_cost_pct: Decimal | None = None
    prime_cost: Decimal | None = None
    prime_cost_pct: Decimal | None = None
    cogs_partial: bool
    labor_available: bool


class ProductMarginResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    variant_id: uuid.UUID
    name: str | None = None
    units: int
    revenue: Decimal
    cogs: Decimal
    margin: Decimal
    margin_pct: Decimal
    cost_available: bool


class ProductMarginReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    top: list[ProductMarginResponse]
    bottom: list[ProductMarginResponse]


class CashFlowCategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    category: str
    direction: str  # "in" | "out"
    amount: Decimal


class CashFlowDailyPointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    day: str
    inflow: Decimal
    outflow: Decimal
    net: Decimal


class CashFlowSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    inflows: Decimal
    outflows: Decimal
    net: Decimal
    cash_inflows: Decimal
    other_inflows: Decimal
    cash_outflows: Decimal
    other_outflows: Decimal
    categories: list[CashFlowCategoryResponse]
    daily: list[CashFlowDailyPointResponse]


class ZReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cash_session_id: uuid.UUID
    branch_id: uuid.UUID
    cashier_employee_id: uuid.UUID
    opened_at: datetime
    closed_at: datetime | None = None
    # Arqueo.
    opening_amount: Decimal
    expected_amount: Decimal | None = None
    counted_amount: Decimal | None = None
    difference: Decimal | None = None
    withdrawals: Decimal
    # Sales.
    channels: list[ZChannelLineResponse]
    gross_sales: Decimal
    gross_tickets: int
    discounts: Decimal
    returns: Decimal
    return_count: int
    net_sales: Decimal
    payments: list[ZPaymentLineResponse]
    # Estimated taxes — never filed tax.
    tax_iva: Decimal
    tax_inc: Decimal
    tax_impoconsumo: Decimal
    taxes_estimated: bool = True
    # Operative summary.
    avg_ticket: Decimal
    peak_hour: int | None = None
    cashier_name: str | None = None
    top_server_employee_id: uuid.UUID | None = None
    top_server_name: str | None = None
    top_product_variant_id: uuid.UUID | None = None
    top_product_name: str | None = None
    top_product_units: int
