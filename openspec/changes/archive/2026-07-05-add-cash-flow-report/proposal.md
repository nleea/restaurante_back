## Why

A purchase of insumos is invisible across Finanzas: a purchase is not an `expense` (so it never hits the Gastos/P&L operating-expense lines) and only reaches the P&L as COGS when the resulting dish is sold. The money left the business, but no finance surface shows it — and the current Resumen "flujo de caja" widget is fake (a running balance of `order.total − expenses.amount` that never reads the real `cash_movements` ledger). Pilots that can't see where their cash went go back to Excel. We need a **cash-basis, method-agnostic money-in/money-out report** that sits alongside the accrual P&L.

## What Changes

- Add a read-only **cash-flow aggregation** to the `reports` module: `GET /reports/cash-flow?branch_id&from&to`, gated by `finance.read`, tenant/branch scoped.
- Aggregate **all real money movement** for the period from each flow's authoritative source, de-duplicated:
  - **Inflows** = `order_payments` (sales received, by method) + customer credit payments + manual cash-in movements.
  - **Outflows** = `purchase_payments` (all methods — where the insumo purchase becomes visible) + `expenses` + manual cash-out movements (retiros).
  - Report **net flow** = inflows − outflows, a daily series and a category breakdown.
- Expose a **cash-vs-other split** so the physical-cash portion reconciles with the arqueo (Reporte Z) and the rest (tarjeta/Nequi/transferencia) is labeled "en tránsito a banco".
- **BREAKING (UI data source)**: replace the fake Resumen cash-flow widget's series with the real net-cash series; wire the existing "Flujo de caja" report card (`key: 'flujo'`) in the Reportes tab to the new endpoint.

De-dup rule: `cash_movements` is a partial mirror (it writes a `sale`/`purchase_payment`/`credit_payment` row per event), so it contributes **only the manual retiros/ingresos**; sales and purchase payments are read from their own tables.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `finance-reporting`: ADD a cash-flow aggregation requirement (period/branch-scoped money-in/money-out from authoritative sources with de-dup, cash-vs-other split, daily series, category breakdown).
- `frontend-finance-reporting`: ADD a cash-flow report requirement and REPLACE the current daily cash-flow widget behavior (fake `total − expenses` series → real net-cash series from the API).

## Impact

- **Backend** (`modules/reports`): new domain entities, ports, repository read methods (reading `order_payments`, `purchase_payments`, `expenses`, `cash_movements`), a `ReportsService.cash_flow` use case, Pydantic schemas, one new route, and tests. No schema migration.
- **Frontend**: `services/reports.api.ts` (new `getCashFlow` client + types) and `views/FinanceZReportView.vue` (Resumen widget data source + Reportes "Flujo de caja" card).
- **Explicit Non-Goals / deferred**: bank-account entity, absolute cash balance, GAAP operating/investing/financing statement, `expenses.method`/`paid_at` schema change, AP aging.
- **No breaking API changes**; the only breaking behavior is the Resumen widget's data source moving from a proxy to real cash flow.
