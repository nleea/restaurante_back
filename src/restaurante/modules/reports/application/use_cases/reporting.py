"""Application service for finance reporting (read-only aggregation)."""

from __future__ import annotations

import datetime as dt
import uuid
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

from restaurante.modules.reports.domain.entities import (
    CashFlowCategoryLine,
    CashFlowDailyPoint,
    CashFlowSummary,
    ChannelCogsLine,
    ChannelMargin,
    CogsSummary,
    DailyPoint,
    ManagerCostKpis,
    ProductMargin,
    ProductMarginReport,
    ProfitAndLoss,
    RevenueSummary,
    TopProduct,
    ZChannelLine,
    ZPaymentLine,
    ZReport,
)
from restaurante.modules.reports.domain.ports import ReportsRepository
from restaurante.shared.domain.errors import NotFoundError

# IVA embedded in a price that already includes 19%: price - price/1.19.
_IVA_RATE = Decimal("0.19") / Decimal("1.19")
# Cash-flow constants.
_CASH_METHOD = "cash"
_CONCEPT_CREDIT_PAYMENT = "credit_payment"


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    """Percentage part/whole (e.g. 42.50); 0 when the base is zero."""
    if whole == 0:
        return Decimal("0.00")
    return (part / whole * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ReportsService:
    def __init__(self, repo: ReportsRepository) -> None:
        self._repo = repo

    async def z_report(
        self, tenant_id: uuid.UUID, cash_session_id: uuid.UUID
    ) -> ZReport:
        facts = await self._repo.get_session_facts(tenant_id, cash_session_id)
        if facts is None:
            raise NotFoundError(f"Sesión de caja no encontrada: {cash_session_id}")

        order_ids = await self._repo.order_ids_for_session(tenant_id, cash_session_id)
        channels = await self._repo.channels_for_orders(tenant_id, order_ids)
        gross_sales = sum((c.amount for c in channels), Decimal(0))
        gross_tickets = sum(c.tickets for c in channels)

        discounts = await self._repo.discount_total(tenant_id, order_ids)
        returns, return_count = await self._repo.returns_total(tenant_id, order_ids)
        net_sales = gross_sales - discounts - returns

        payments = await self._repo.payments_for_session(tenant_id, cash_session_id)
        withdrawals = await self._repo.withdrawals_total(tenant_id, cash_session_id)

        hours = await self._repo.order_close_hours(tenant_id, order_ids)
        peak_hour = Counter(hours).most_common(1)[0][0] if hours else None
        top_server = await self._repo.top_server(tenant_id, order_ids)
        top_product = await self._repo.top_product(tenant_id, order_ids)

        cashier_name = await self._repo.employee_name(
            tenant_id, facts.cashier_employee_id
        )
        top_server_name = (
            await self._repo.employee_name(tenant_id, top_server)
            if top_server
            else None
        )
        top_product_name = (
            await self._repo.variant_name(tenant_id, top_product[0])
            if top_product
            else None
        )

        avg_ticket = _money(net_sales / gross_tickets) if gross_tickets else Decimal(0)

        return ZReport(
            cash_session_id=cash_session_id,
            branch_id=facts.branch_id,
            cashier_employee_id=facts.cashier_employee_id,
            opened_at=facts.opened_at,
            closed_at=facts.closed_at,
            opening_amount=facts.opening_amount,
            expected_amount=facts.expected_amount,
            counted_amount=facts.counted_amount,
            difference=facts.difference,
            withdrawals=withdrawals,
            channels=[ZChannelLine(c.channel, c.amount, c.tickets) for c in channels],
            gross_sales=gross_sales,
            gross_tickets=gross_tickets,
            discounts=discounts,
            returns=returns,
            return_count=return_count,
            net_sales=net_sales,
            payments=[ZPaymentLine(p.method, p.amount) for p in payments],
            # Estimated taxes (IVA embedded at 19%); INC/Impoconsumo left at 0 until
            # a beverage/consumption base is modeled. All flagged as estimates.
            tax_iva=_money(net_sales * _IVA_RATE),
            tax_inc=Decimal(0),
            tax_impoconsumo=Decimal(0),
            avg_ticket=avg_ticket,
            peak_hour=peak_hour,
            cashier_name=cashier_name,
            top_server_employee_id=top_server,
            top_server_name=top_server_name,
            top_product_variant_id=top_product[0] if top_product else None,
            top_product_name=top_product_name,
            top_product_units=top_product[1] if top_product else 0,
        )

    # --- Revenue engine ----------------------------------------------------
    async def revenue_summary(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        cashier_employee_id: uuid.UUID | None = None,
    ) -> RevenueSummary:
        channels = await self._repo.revenue_channels(
            tenant_id, branch_id, date_from, date_to, cashier_employee_id
        )
        total = sum((c.amount for c in channels), Decimal(0))
        tickets = sum(c.tickets for c in channels)
        payments = await self._repo.revenue_payments(
            tenant_id, branch_id, date_from, date_to
        )
        discounts, returns, return_count = await self._repo.revenue_discounts_returns(
            tenant_id, branch_id, date_from, date_to
        )
        return RevenueSummary(
            total=total,
            tickets=tickets,
            avg_ticket=_money(total / tickets) if tickets else Decimal(0),
            discounts=discounts,
            returns=returns,
            return_count=return_count,
            net=total - discounts - returns,
            channels=[ZChannelLine(c.channel, c.amount, c.tickets) for c in channels],
            payments=[ZPaymentLine(p.method, p.amount) for p in payments],
        )

    async def daily_series(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> list[DailyPoint]:
        income = {
            d.day: d.amount
            for d in await self._repo.daily_income(
                tenant_id, branch_id, date_from, date_to
            )
        }
        expenses = {
            d.day: d.amount
            for d in await self._repo.daily_expenses(
                tenant_id, branch_id, date_from, date_to
            )
        }
        days = sorted(set(income) | set(expenses))
        return [
            DailyPoint(
                day=day,
                income=income.get(day, Decimal(0)),
                expenses=expenses.get(day, Decimal(0)),
            )
            for day in days
        ]

    async def top_products(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        limit: int = 5,
    ) -> list[TopProduct]:
        aggs = await self._repo.top_products(
            tenant_id, branch_id, date_from, date_to, limit
        )
        out: list[TopProduct] = []
        for a in aggs:
            name = await self._repo.variant_name(tenant_id, a.variant_id)
            out.append(TopProduct(a.variant_id, name, a.units, a.revenue))
        return out

    # --- Product costing (COGS) --------------------------------------------
    async def _variant_costs(
        self, tenant_id: uuid.UUID
    ) -> tuple[dict[uuid.UUID, Decimal], dict[uuid.UUID, bool]]:
        """Roll the BOM up to a per-variant cost. A variant is "partial" when
        any of its ingredients has no purchase-derived cost."""
        costs = dict(await self._repo.ingredient_avg_costs(tenant_id))
        variant_cost: dict[uuid.UUID, Decimal] = {}
        variant_partial: dict[uuid.UUID, bool] = {}
        for item in await self._repo.all_recipe_items(tenant_id):
            c = costs.get(item.ingredient_id)
            variant_cost[item.variant_id] = variant_cost.get(
                item.variant_id, Decimal(0)
            ) + (item.quantity * (c or Decimal(0)))
            if c is None:
                variant_partial[item.variant_id] = True
        return variant_cost, variant_partial

    async def cogs_summary(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> CogsSummary:
        variant_cost, variant_partial = await self._variant_costs(tenant_id)

        sold = await self._repo.sold_items_by_channel(
            tenant_id, branch_id, date_from, date_to
        )
        by_channel: dict[str, Decimal] = {}
        total = Decimal(0)
        priced: set[uuid.UUID] = set()
        unpriced: set[uuid.UUID] = set()
        partial = False
        for row in sold:
            if row.variant_id not in variant_cost or variant_partial.get(
                row.variant_id
            ):
                partial = True
                unpriced.add(row.variant_id)
            else:
                priced.add(row.variant_id)
            line = variant_cost.get(row.variant_id, Decimal(0)) * row.units
            total += line
            by_channel[row.channel] = by_channel.get(row.channel, Decimal(0)) + line

        return CogsSummary(
            cogs=_money(total),
            partial=partial,
            priced_variants=len(priced),
            unpriced_variants=len(unpriced),
            channels=[
                ChannelCogsLine(channel=ch, cogs=_money(v))
                for ch, v in by_channel.items()
            ],
        )

    # --- Profitability (P&L, margins) --------------------------------------
    async def profit_and_loss(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> ProfitAndLoss:
        revenue = (
            await self.revenue_summary(tenant_id, branch_id, date_from, date_to)
        ).net
        cogs = await self.cogs_summary(tenant_id, branch_id, date_from, date_to)
        opex = await self._repo.expenses_total(
            tenant_id, branch_id, date_from, date_to
        )

        gross_profit = revenue - cogs.cogs
        ebitda = gross_profit - opex
        estimated_taxes = _money(revenue * _IVA_RATE)
        net_profit = ebitda - estimated_taxes

        # Break-even revenue = fixed opex / contribution-margin ratio, treating
        # COGS as the only variable cost. Undefined when contribution ≤ 0.
        break_even = (
            _money(opex * revenue / gross_profit) if gross_profit > 0 else None
        )

        # Per-channel margin: channel gross revenue − channel COGS. Discounts and
        # returns are not allocated per channel, so channels use gross totals.
        channel_cogs = {c.channel: c.cogs for c in cogs.channels}
        channel_rev = await self._repo.revenue_channels(
            tenant_id, branch_id, date_from, date_to
        )
        channels: list[ChannelMargin] = []
        for ch in channel_rev:
            ch_cogs = channel_cogs.get(ch.channel, Decimal(0))
            ch_margin = ch.amount - ch_cogs
            channels.append(
                ChannelMargin(
                    channel=ch.channel,
                    revenue=ch.amount,
                    cogs=ch_cogs,
                    margin=ch_margin,
                    margin_pct=_pct(ch_margin, ch.amount),
                )
            )

        return ProfitAndLoss(
            revenue=revenue,
            cogs=cogs.cogs,
            cogs_partial=cogs.partial,
            gross_profit=gross_profit,
            gross_margin_pct=_pct(gross_profit, revenue),
            operating_expenses=opex,
            ebitda=ebitda,
            ebitda_margin_pct=_pct(ebitda, revenue),
            estimated_taxes=estimated_taxes,
            net_profit=net_profit,
            net_margin_pct=_pct(net_profit, revenue),
            contribution_margin_pct=_pct(gross_profit, revenue),
            break_even_revenue=break_even,
            channels=channels,
        )

    async def cost_kpis(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> ManagerCostKpis:
        revenue = (
            await self.revenue_summary(tenant_id, branch_id, date_from, date_to)
        ).net
        cogs = await self.cogs_summary(tenant_id, branch_id, date_from, date_to)
        labor = await self._repo.labor_expenses_total(
            tenant_id, branch_id, date_from, date_to
        )

        food_cost_pct = _pct(cogs.cogs, revenue) if revenue > 0 else None
        labor_available = labor is not None
        labor_cost_pct = _pct(labor, revenue) if labor is not None else None
        prime_cost = cogs.cogs + labor if labor is not None else None
        prime_cost_pct = _pct(prime_cost, revenue) if prime_cost is not None else None

        return ManagerCostKpis(
            revenue=revenue,
            food_cost_pct=food_cost_pct,
            labor_cost=labor,
            labor_cost_pct=labor_cost_pct,
            prime_cost=prime_cost,
            prime_cost_pct=prime_cost_pct,
            cogs_partial=cogs.partial,
            labor_available=labor_available,
        )

    async def product_margins(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
        limit: int = 5,
    ) -> ProductMarginReport:
        variant_cost, variant_partial = await self._variant_costs(tenant_id)
        sales = await self._repo.variant_sales(
            tenant_id, branch_id, date_from, date_to
        )

        priced: list[ProductMargin] = []
        unpriced: list[ProductMargin] = []
        for row in sales:
            cost_available = (
                row.variant_id in variant_cost
                and not variant_partial.get(row.variant_id, False)
            )
            unit_cost = variant_cost.get(row.variant_id, Decimal(0))
            line_cogs = _money(unit_cost * row.units) if cost_available else Decimal(0)
            margin = row.revenue - line_cogs if cost_available else Decimal(0)
            name = await self._repo.variant_name(tenant_id, row.variant_id)
            entry = ProductMargin(
                variant_id=row.variant_id,
                name=name,
                units=row.units,
                revenue=row.revenue,
                cogs=line_cogs,
                margin=margin,
                margin_pct=_pct(margin, row.revenue) if cost_available else Decimal(0),
                cost_available=cost_available,
            )
            (priced if cost_available else unpriced).append(entry)

        priced.sort(key=lambda p: p.margin, reverse=True)
        return ProductMarginReport(
            top=priced[:limit],
            bottom=list(reversed(priced[-limit:])) if priced else [],
        )

    # --- Cash flow (money-in / money-out) ----------------------------------
    async def cash_flow(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        date_from: dt.date,
        date_to: dt.date,
    ) -> CashFlowSummary:
        cats: dict[tuple[str, str], Decimal] = {}
        daily_in: dict[str, Decimal] = {}
        daily_out: dict[str, Decimal] = {}
        splits = {"cash_in": Decimal(0), "other_in": Decimal(0),
                  "cash_out": Decimal(0), "other_out": Decimal(0)}

        def record(category: str, direction: str, method: str, day: str,
                   amount: Decimal) -> None:
            cats[(category, direction)] = cats.get(
                (category, direction), Decimal(0)
            ) + amount
            bucket = daily_in if direction == "in" else daily_out
            bucket[day] = bucket.get(day, Decimal(0)) + amount
            side = "cash" if method == _CASH_METHOD else "other"
            splits[f"{side}_{direction}"] += amount

        for s in await self._repo.cf_sales(tenant_id, branch_id, date_from, date_to):
            record("Ventas", "in", s.method, s.day, s.amount)
        for m in await self._repo.cf_movements(
            tenant_id, branch_id, date_from, date_to, "in"
        ):
            # credit-payment movements are branch-scoped abonos; the rest are manual.
            category = (
                "Abonos a crédito"
                if m.concept == _CONCEPT_CREDIT_PAYMENT
                else "Ingresos de caja"
            )
            record(category, "in", m.method, m.day, m.amount)
        for p in await self._repo.cf_supplier_payments(
            tenant_id, branch_id, date_from, date_to
        ):
            record("Compras", "out", p.method, p.day, p.amount)
        # Expenses carry no payment method → classified as "other" (they never
        # touch the tracked drawer, so the cash split stays reconcilable).
        for day, amount in await self._repo.cf_expenses(
            tenant_id, branch_id, date_from, date_to
        ):
            record("Gastos", "out", "other", day, amount)
        for m in await self._repo.cf_movements(
            tenant_id, branch_id, date_from, date_to, "out"
        ):
            record("Retiros de caja", "out", m.method, m.day, m.amount)

        inflows = splits["cash_in"] + splits["other_in"]
        outflows = splits["cash_out"] + splits["other_out"]
        days = sorted(set(daily_in) | set(daily_out))
        daily = [
            CashFlowDailyPoint(
                day=d,
                inflow=_money(daily_in.get(d, Decimal(0))),
                outflow=_money(daily_out.get(d, Decimal(0))),
                net=_money(daily_in.get(d, Decimal(0)) - daily_out.get(d, Decimal(0))),
            )
            for d in days
        ]
        categories = [
            CashFlowCategoryLine(category=c, direction=dr, amount=_money(amt))
            for (c, dr), amt in cats.items()
        ]
        categories.sort(key=lambda x: (x.direction != "in", -x.amount))
        return CashFlowSummary(
            inflows=_money(inflows),
            outflows=_money(outflows),
            net=_money(inflows - outflows),
            cash_inflows=_money(splits["cash_in"]),
            other_inflows=_money(splits["other_in"]),
            cash_outflows=_money(splits["cash_out"]),
            other_outflows=_money(splits["other_out"]),
            categories=categories,
            daily=daily,
        )
