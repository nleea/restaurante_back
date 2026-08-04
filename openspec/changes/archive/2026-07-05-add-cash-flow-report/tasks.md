## 1. Backend — cash-flow aggregation

- [x] 1.1 Domain: add `CashFlowCategoryLine`, `CashFlowDailyPoint`, `CashFlowSummary` (inflows, outflows, net, cash/other subtotals per direction, category lines, daily series) entities in `modules/reports/domain/entities.py`
- [x] 1.2 Ports: add read methods to `ReportsRepository` for the authoritative sources — sales received (`order_payments` by method), customer credit payments (in), supplier payments (`purchase_payments`, all methods), expenses total-by-day, and manual cash movements only (`cash_movements` where `concept` ∉ mirrored concepts), each returning amount + method + day
- [x] 1.3 Repository: implement the read methods in `infrastructure/repositories.py`, reading `OrderPaymentModel`/customer-credit/`PurchasePaymentModel`/`ExpenseModel`/`CashMovementModel`, scoped by `tenant_id`+`branch_id`+date; exclude mirrored `cash_movements` (`sale`, `credit_payment`, `purchase_payment`) to avoid double counting
- [x] 1.4 Application: `ReportsService.cash_flow(tenant, branch, from, to)` assembling inflows/outflows by category, the daily net series, net = inflows − outflows, and the cash-vs-other split
- [x] 1.5 API: `GET /reports/cash-flow` (`branch_id`, `from`, `to`) gated `finance.read` + Pydantic schemas in `infrastructure/api/`
- [x] 1.6 Tests: de-dup invariant (a `sale` movement + its `order_payment` counted once), a paid purchase appears as outflow (any method), manual retiros/ingresos included, expenses included, cash-vs-other split, tenant/branch/period scoping; ruff + mypy clean

## 2. Frontend — wire cash flow

- [x] 2.1 `services/reports.api.ts`: add `getCashFlow(branchId, from, to)` + `CashFlowSummary`/line/point types
- [x] 2.2 `views/FinanceZReportView.vue`: load cash flow in the shared period/branch loader; replace the fake Resumen cash-flow series (`total − expenses` running balance) with the API net-cash series behind `CashFlowLine`
- [x] 2.3 `views/FinanceZReportView.vue`: wire the Reportes "Flujo de caja" card (`key: 'flujo'`) to open the inflows/outflows-by-category breakdown with the cash-vs-other split; empty/loading states
- [x] 2.4 Frontend gates: `pnpm type-check`, `pnpm lint`, `pnpm test:unit`, `pnpm build`; no horizontal page scroll

## 3. Verification

- [x] 3.1 End-to-end against seeded demo data: register a supplier payment (cash and non-cash) → confirm both appear as cash-flow outflows; confirm sales are not double-counted vs the mirror ledger; confirm the cash-method subtotal reconciles with the arqueo/Reporte Z; confirm net = inflows − outflows
