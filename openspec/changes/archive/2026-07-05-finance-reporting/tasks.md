## 1. Phase 1 — Gastos real + Reporte Z

- [x] 1.1 Scaffold a read-only `modules/reports` backend module (hexagonal: API → application → domain ports → read repositories); mount at `/reports`, gate `finance.read`
- [x] 1.2 Implement the Z session-report aggregation: given a `cash_session_id`, join orders/order_payments/cash_movements → ventas-por-canal, métodos-de-pago, descuentos/devoluciones, arqueo (from `cash_sessions`), retiros (movements), operative summary; taxes estimated + flagged
- [x] 1.3 Add `GET /reports/z/{cash_session_id}` + Pydantic schemas; backend tests (session scoping, arqueo matches session, tenant/branch isolation); ruff + mypy clean
- [x] 1.4 Frontend: reports service + `getZReport`, `listCashSessions`; wire Reporte Z tab to real sessions + docket; keep the arqueo "cerrar turno" flow calling the existing cash close API
- [x] 1.5 Frontend: wire Gastos tab to the existing finance expense API (categories, expenses, record-expense gated by `finance.manage`); category totals + filter from real data

## 2. Phase 2 — Ingresos + Resumen (revenue engine)

- [x] 2.1 Implement revenue summary aggregation (total, by channel, tickets, avg ticket) over closed orders in `[from,to]` for a branch; period/cashier filters
- [x] 2.2 Implement payment-method mix, discounts/returns, daily income-vs-expenses series, top products (`order_items`), and cumulative cash-flow (cash sessions/movements) with threshold
- [x] 2.3 Add reporting endpoints + schemas for the above; cost-free manager KPIs (RevPASH, avg tickets, MoM); Alembic read indexes on `orders(branch_id, closed_at, status)` and `order_payments(cash_session_id)`
- [x] 2.4 Backend tests for the revenue engine (channel/payment/day grouping, scoping); ruff + mypy clean
- [x] 2.5 Frontend: reports store + `period/branch/filters` state; wire Ingresos (stats, channel cards, transactions table, payment donut) and Resumen (KPIs, charts, alerts, cost-free indicators) to the API
- [x] 2.6 Frontend: the sticky global filter bar (período/sucursal/turno/cajero) recomputes all KPIs/charts on change; "turno" derived from cash session / time-of-day

## 3. Phase 3 — product-costing (COGS)

- [x] 3.1 `product-costing` service: ingredient unit cost = moving-average of `purchase_order_lines.unit_price` normalized to stock unit; unavailable when no purchase history
- [x] 3.2 Product cost = BOM rollup over `recipe_items` (qty × ingredient cost); flag partial when any ingredient cost is unavailable
- [x] 3.3 COGS for a period = Σ sold `order_items` (product cost × qty); expose `GET /reports/cogs` (or cost read); optional cached `product_costs` table + migration
- [x] 3.4 Backend tests (cost rollup, partial flag, period COGS); seed/demo cost data via purchasing; ruff + mypy clean

## 4. Phase 4 — Rentabilidad + margin reports

- [x] 4.1 P&L endpoint: revenue − COGS (gross) − operating expenses + estimated taxes → EBITDA and net; margin-by-channel (revenue − COGS per channel); break-even (fixed opex ÷ contribution margin)
- [x] 4.2 Cost-dependent manager KPIs (food cost %, labor cost %, prime cost) and product margin (top/bottom) reports
- [x] 4.3 Backend tests for P&L math and margins; ruff + mypy clean
- [x] 4.4 Frontend: wire Rentabilidad (P&L statement, margen table, break-even) and the cost-dependent report cards; remove the "pendiente de costeo" placeholders

## 5. Consolidation & verification

- [x] 5.1 Consolidate the module onto `/finance` (old expenses-only `FinanceView.vue` becomes the Gastos tab); `/finance/z` redirects; single sidebar "Finanzas" entry gated by `finance.read`
- [x] 5.2 Frontend gates green: `pnpm type-check`, `pnpm lint`, `pnpm test:unit`, `pnpm build`; no horizontal page scroll across tabs
- [x] 5.3 End-to-end against seeded demo data: pick a period → verify Resumen/Ingresos/Gastos/Reporte Z reconcile with the underlying orders/cash/expenses; close a real shift and view its Z; confirm estimated-tax and pending-costing labels render
