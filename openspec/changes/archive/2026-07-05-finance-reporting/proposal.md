## Why

The Finanzas module (`/finance/z`, 6 tabs: Resumen, Ingresos, Gastos, Rentabilidad, Reporte Z, Reportes) is a complete El Pase prototype running on in-memory seed data. Managers need it on real data to run the business. The blocker: Finanzas owns no data — it is a **read/reporting layer** over `orders`, `cash`, `finance` (expenses) and `recipes`. All the raw transactional data exists, but there is **no aggregation layer** that computes revenue-by-channel, payment mix, daily series, top products, the per-session Reporte Z, or the P&L. Two inputs are also missing: **product cost / COGS** (recipes carry the BOM but no cost; the only price in the backend is `purchasing.unit_price`) and **taxes** (not modeled on orders). This change builds the reporting layer and the costing it needs, and wires the UI — in phases, so the revenue-and-cash side ships without waiting on costing.

## What Changes

- **New backend reporting API** (`finance-reporting`) aggregating existing data — read-only, `finance.read`, scoped by tenant/branch and a period (`from`/`to`) plus optional shift/cashier filters:
  - Revenue summary (total, by channel, tickets, average ticket), payment-method mix, discounts/returns.
  - Daily income-vs-expenses series and cumulative cash-flow (from cash sessions/movements) with the operational-minimum threshold.
  - Top products (from `order_items`).
  - **Reporte Z per cash session**: aggregate the session's orders/payments/movements into ventas-por-canal, métodos-de-pago, arqueo (fondo/esperado/contado/diferencia already on `cash_sessions`), estimated taxes, and operative summary.
  - Manager KPIs that don't need cost (RevPASH, avg tickets, MoM growth).
- **New product-costing capability** (`product-costing`): derive an ingredient unit cost from purchasing history (latest/average `unit_price`), roll it up through the recipe BOM to a **product cost**, and expose **COGS** for sold items. Unblocks margins and the P&L.
- **New frontend wiring** (`frontend-finance-reporting`): replace the prototype's in-memory seed with the reporting API across all six tabs; add the sticky **global filter bar** (período / sucursal / turno / cajero) that recomputes everything; consolidate the module onto the real `/finance` route and add it to the sidebar; keep `finance.read` gating.
- **Taxes are computed estimates** (IVA 19%, INC/Impoconsumo) derived from net sales — clearly labeled as estimates, not tracked tax. Real DIAN tax modeling stays out of scope.
- **Phased delivery** (see design): Ph1 Gastos + Reporte Z · Ph2 Ingresos + Resumen (revenue engine) · Ph3 product-costing · Ph4 Rentabilidad + margin reports.

## Capabilities

### New Capabilities
- `finance-reporting`: read-only aggregation API over orders/cash/finance for revenue, payments, daily series, cash-flow, top products, the per-session Reporte Z, and cost-free manager KPIs.
- `product-costing`: ingredient cost from purchasing + BOM rollup → product cost and COGS for sold items; the input the P&L and margin KPIs need.
- `frontend-finance-reporting`: the six-tab Finanzas module wired to real data, with the global filter bar, route consolidation and sidebar entry.

### Modified Capabilities
<!-- None: reporting reads existing modules without changing their requirements. Recurring
     expenses and cash-posting stay deferred in finance-management as before. -->

## Impact

- **Backend**: new `reports` (or `finance/reporting`) read module with cross-module aggregation queries (SQLAlchemy) over `orders`, `order_items`, `order_payments`, `cash_sessions`, `cash_movements`, `expenses`; a `product-costing` service reading `purchase_order_lines` + `recipe_items`. No writes to those modules; no schema changes except (optionally) a cached product-cost table in a later phase. New permission use of `finance.read`.
- **Frontend**: `FinanceZReportView.vue` (+ `components/finance/*`, `lib/cop.ts`) switch from seed to API-backed stores/services; new finance-reporting service + store; global filter bar; route `/finance` consolidation; sidebar link.
- **Contract**: additive GET endpoints only; no breaking changes to orders/cash/finance APIs.
- **Deferred (explicit)**: real tax modeling (DIAN), recurring-expense automation, materialized/scheduled rollups, and the profitability tab until `product-costing` lands.
