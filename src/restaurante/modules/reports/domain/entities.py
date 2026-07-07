"""Framework-free domain entities for finance reporting.

These are read-only aggregates assembled from other modules' data (orders, cash).
The reports module never writes; it only reads and rolls up.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class ZChannelLine:
    channel: str
    amount: Decimal
    tickets: int


@dataclass
class ZPaymentLine:
    method: str
    amount: Decimal


@dataclass
class RevenueSummary:
    total: Decimal
    tickets: int
    avg_ticket: Decimal
    discounts: Decimal
    returns: Decimal
    return_count: int
    net: Decimal
    channels: list[ZChannelLine] = field(default_factory=list)
    payments: list[ZPaymentLine] = field(default_factory=list)


@dataclass
class DailyPoint:
    day: str  # yyyy-mm-dd
    income: Decimal
    expenses: Decimal


@dataclass
class TopProduct:
    variant_id: uuid.UUID
    name: str | None
    units: int
    revenue: Decimal


@dataclass
class ChannelCogsLine:
    channel: str
    cogs: Decimal


@dataclass
class CogsSummary:
    """Cost of goods sold for a period, derived from purchasing → BOM → sold items.

    `partial` is True when any sold variant lacks a fully-priced recipe, so the
    UI can flag the COGS/margin as estimated rather than complete.
    """

    cogs: Decimal
    partial: bool
    priced_variants: int
    unpriced_variants: int
    channels: list[ChannelCogsLine] = field(default_factory=list)


@dataclass
class ChannelMargin:
    channel: str
    revenue: Decimal
    cogs: Decimal
    margin: Decimal
    margin_pct: Decimal


@dataclass
class ProfitAndLoss:
    """A period P&L: net revenue − COGS − operating expenses, with estimated taxes.

    `revenue` is net sales (total − discounts − returns). `cogs_partial` mirrors
    the costing partial flag so the UI can label EBITDA/net as estimated. Taxes
    are the same embedded-IVA estimate used by the Z report, never filed tax.
    `break_even_revenue` is None when the contribution margin is non-positive.
    """

    revenue: Decimal
    cogs: Decimal
    cogs_partial: bool
    gross_profit: Decimal
    gross_margin_pct: Decimal
    operating_expenses: Decimal
    ebitda: Decimal
    ebitda_margin_pct: Decimal
    estimated_taxes: Decimal
    net_profit: Decimal
    net_margin_pct: Decimal
    contribution_margin_pct: Decimal
    break_even_revenue: Decimal | None
    channels: list[ChannelMargin] = field(default_factory=list)


@dataclass
class ManagerCostKpis:
    """Cost-dependent manager KPIs. Labor comes from expenses in labor-tagged
    categories; when none exist labor/prime figures are unavailable, not zero."""

    revenue: Decimal
    food_cost_pct: Decimal | None
    labor_cost: Decimal | None
    labor_cost_pct: Decimal | None
    prime_cost: Decimal | None
    prime_cost_pct: Decimal | None
    cogs_partial: bool
    labor_available: bool


@dataclass
class ProductMargin:
    variant_id: uuid.UUID
    name: str | None
    units: int
    revenue: Decimal
    cogs: Decimal
    margin: Decimal
    margin_pct: Decimal
    cost_available: bool


@dataclass
class ProductMarginReport:
    top: list[ProductMargin] = field(default_factory=list)
    bottom: list[ProductMargin] = field(default_factory=list)


@dataclass
class CashFlowCategoryLine:
    category: str
    direction: str  # "in" | "out"
    amount: Decimal


@dataclass
class CashFlowDailyPoint:
    day: str  # yyyy-mm-dd
    inflow: Decimal
    outflow: Decimal
    net: Decimal


@dataclass
class CashFlowSummary:
    """Cash-basis money-in / money-out for a period, from authoritative sources.

    A purchase of insumos shows here as an outflow when paid (any method), while it
    only reaches the P&L as COGS when the dish sells. `cash_*` vs `other_*` splits the
    physical-cash portion (reconciles with the arqueo) from card/Nequi/transfer. There
    is deliberately no absolute balance — only net flow (see design D3).
    """

    inflows: Decimal
    outflows: Decimal
    net: Decimal
    cash_inflows: Decimal
    other_inflows: Decimal
    cash_outflows: Decimal
    other_outflows: Decimal
    categories: list[CashFlowCategoryLine] = field(default_factory=list)
    daily: list[CashFlowDailyPoint] = field(default_factory=list)


@dataclass
class ZReport:
    """The per-cash-session close report (Reporte Z).

    Arqueo figures (opening/expected/counted/difference) come straight from the
    cash session; everything else is aggregated from the session's orders,
    payments, movements and items. Taxes are estimates derived from net sales.
    """

    cash_session_id: uuid.UUID
    branch_id: uuid.UUID
    cashier_employee_id: uuid.UUID
    opened_at: datetime
    closed_at: datetime | None
    # Arqueo — from the cash session.
    opening_amount: Decimal
    expected_amount: Decimal | None
    counted_amount: Decimal | None
    difference: Decimal | None
    withdrawals: Decimal
    # Sales.
    channels: list[ZChannelLine] = field(default_factory=list)
    gross_sales: Decimal = Decimal(0)
    gross_tickets: int = 0
    discounts: Decimal = Decimal(0)
    returns: Decimal = Decimal(0)
    return_count: int = 0
    net_sales: Decimal = Decimal(0)
    payments: list[ZPaymentLine] = field(default_factory=list)
    # Estimated taxes (labeled as estimates in the API/UI).
    tax_iva: Decimal = Decimal(0)
    tax_inc: Decimal = Decimal(0)
    tax_impoconsumo: Decimal = Decimal(0)
    # Operative summary.
    avg_ticket: Decimal = Decimal(0)
    peak_hour: int | None = None
    cashier_name: str | None = None
    top_server_employee_id: uuid.UUID | None = None
    top_server_name: str | None = None
    top_product_variant_id: uuid.UUID | None = None
    top_product_name: str | None = None
    top_product_units: int = 0
