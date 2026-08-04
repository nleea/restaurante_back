## Context

Finanzas is a reporting surface, not a data owner. The transactional data it needs already exists:

- `orders`: `channel`, `subtotal`/`discount`/`total`, `employee_id`, `closed_at`, `status`.
- `order_items`: `product_variant_id`, `quantity`, `unit_price`, `line_subtotal` (top products).
- `order_payments`: `amount`, `method`, `cash_session_id`, `employee_id` (payment mix, ties sales to a session).
- `cancellations`: reason (returns/discount analysis).
- `cash_sessions`: `opening_amount`, `expected_amount`, `counted_amount`, `difference`, opened/closed by, timestamps (the arqueo).
- `cash_movements`: `type`, `concept`, `amount`, `method`, `reference_id` (retiros/ingresos; ref → order).
- `expenses` + `expense_categories` (finance module, already has a CRUD API).
- `recipe_items`: product → ingredient + quantity (BOM), but **no cost**.
- `purchase_order_lines.unit_price`: the only price signal for ingredient cost.

What is missing is (1) an **aggregation layer** and (2) two inputs — **product cost/COGS** and **taxes**. Constraints: hexagonal (`API → application → domain`), row-level `tenant_id` + `branch_id`, English identifiers, `finance.read` for reads, multi-branch by data model.

## Goals / Non-Goals

**Goals:**
- A read-only aggregation API that powers the revenue/cash side of all six tabs against real data.
- A product-costing capability that yields COGS, unblocking the P&L and margin KPIs.
- Wire the existing El Pase prototype to that API with a global filter bar; ship in phases so revenue+cash go out before costing exists.

**Non-Goals:**
- Real tracked taxes / DIAN — taxes are computed estimates, labeled as such.
- Recurring-expense automation and cash-posting of expenses (stay deferred in finance-management).
- Materialized/scheduled rollups or a warehouse — live aggregation for pilots.
- Changing orders/cash/finance write behavior; this change only reads them.

## Decisions

### D1 — A dedicated read-only `reports` module (option 2 refined)

Aggregation lives in a new backend module (`modules/reports`, mounted at `/reports`, or `/finance/reports`) that **reads** across `orders`, `cash`, `finance`, `product-costing`. **Why over "extend finance":** finance owns the expense ledger; making it aggregate every other module blurs its boundary. **Why over one query per view inline:** a single reporting module centralizes the cross-module SQL, tenant/branch scoping and period handling. Hexagonal purity is relaxed deliberately for a cross-cutting read layer — it depends on other modules' *tables* read-only, never their write paths. The **Reporte Z** endpoint is part of this module (`GET /reports/z/{cash_session_id}`) because it joins orders+payments+movements per session, even though the arqueo numbers come straight from `cash_sessions`.

### D2 — Live SQL aggregation, no rollup tables (for pilots)

Endpoints run `GROUP BY` aggregation over the transactional tables per request, filtered by `tenant_id`, `branch_id`, and `[from, to]` on `orders.closed_at` (only `status = closed`/paid orders count as revenue). **Why:** pilot data volumes are small; correctness and simplicity beat pre-aggregation. A cached daily rollup is a later optimization, not needed now. Trade-off: heavier queries as data grows → revisit with indexes on `(branch_id, closed_at, status)`.

### D3 — Product cost via purchasing → BOM rollup

`product-costing` computes: **ingredient unit cost** = latest (or moving-average) `purchase_order_lines.unit_price` per ingredient/unit; **product cost** = Σ over `recipe_items` (ingredient qty × ingredient unit cost); **COGS** for a period = Σ over sold `order_items` (product cost × quantity). **Why latest/avg purchase price:** it is the only cost signal available; no separate standard-cost entry is required from pilots. Alternatives considered: manual standard cost per product (more accurate, more data entry — defer); FIFO/weighted from stock movements (needs valued inventory — not modeled). Start with moving-average purchase cost, expose a `product_cost` read; a cached `product_costs` table is optional in Phase 3.

### D4 — Taxes are computed estimates, labeled

Orders don't carry tax. The Z-report and P&L derive IVA (19%), INC and Impoconsumo as estimates from net sales and surface them with an explicit "estimado" label. **Why:** real tax lines need order-level tax modeling (a separate DIAN-oriented change). Estimates are honest and useful for management now; the UI must not present them as filed tax.

### D5 — Period + filter contract, and "turno"

Every reporting endpoint takes `branch_id`, `from`, `to` (dates), and optional `cashier_employee_id`. **"Turno"** (mañana/tarde/noche) is not a stored field: derive it from the payment's `cash_session` (a shift = a cash session) or from `closed_at` time-of-day buckets. The global filter bar maps to these params and recomputes on change. Multi-branch: `branch_id` optional → consolidated is a Phase-2 concern; default to the active branch.

### D6 — Reporte Z reads the session, aggregates the rest

`GET /reports/z/{cash_session_id}` returns: header (branch, shift window from session times, cashier = `opened_by`, `opening_amount`); ventas por canal + tickets (orders whose payments hit this session, grouped by `channel`); métodos de pago (session's `order_payments` grouped by `method`); descuentos/devoluciones (order discounts + cancellations); arqueo (straight from `cash_sessions`: expected/counted/difference) with retiros from `cash_movements`; estimated taxes; operative summary (avg ticket, peak hour, top product, top server). Closing a shift stays the existing `cash.close_session` (arqueo) — reporting only reads.

### D7 — Frontend keeps the prototype, swaps the data source

`FinanceZReportView.vue` and `components/finance/*` are kept; only the seed constants are replaced by a `reports` service + Pinia store. The global filter bar drives one shared `period`/`branch`/`filters` state; each tab reads derived getters. Route consolidation: the module moves to `/finance` (the old expenses-only `FinanceView.vue` becomes the Gastos tab), with `/finance/z` redirecting. Sidebar keeps one "Finanzas" entry.

## Phases

```
 Ph1  Gastos real + Reporte Z          uses finance/expenses (exists) + new
      (cheap, high value)              /reports/z session aggregation
 Ph2  Ingresos + Resumen               /reports revenue engine (channels,
      (revenue engine)                 tickets, payments, daily, top products,
                                        cash-flow) + cost-free KPIs
 Ph3  product-costing (COGS)           purchasing → BOM rollup → product cost
                                        (unblocks margins)
 Ph4  Rentabilidad + margin reports    P&L (rev − COGS − opex + est. taxes),
                                        margin-by-channel, break-even,
                                        food/labor/prime cost, product margin
```

Ph1–Ph2 ship the entire revenue-and-cash experience without costing. Ph4 is gated on Ph3.

## Risks / Trade-offs

- **COGS accuracy from purchase price** → moving-average of `unit_price`; label margins as "costo estimado por compras"; allow a manual override later.
- **Estimated taxes mistaken for real** → explicit "estimado" labels; never present as filed.
- **Cross-module read coupling** → the reports module reads tables via read-only repositories; document the dependency; no writes, no imports of other modules' write use-cases.
- **Aggregation cost at scale** → add composite indexes on `orders(branch_id, closed_at, status)` and `order_payments(cash_session_id)`; revisit rollups only if pilots outgrow live queries.
- **"Turno" ambiguity** → prefer cash-session-derived shift; fall back to time-of-day buckets; make the definition explicit in the API.
- **Order→session linkage** → revenue-by-session relies on `order_payments.cash_session_id`; orders with no payment (comped) are excluded from cash reports but counted in sales — document the rule.

## Migration Plan

1. Ph1: add `modules/reports` with the Z-session endpoint; wire Gastos to existing `finance/expenses`; wire Reporte Z. No migration.
2. Ph2: add revenue/summary endpoints; wire Ingresos/Resumen. Add read indexes via Alembic.
3. Ph3: add `product-costing` (service + optional cached `product_costs` table + migration); seed/demo cost data.
4. Ph4: add P&L/margin endpoints; wire Rentabilidad + margin reports. Consolidate route + sidebar; `/finance/z` → `/finance`.
Rollback per phase = remove the additive endpoints/UI; no destructive schema changes.

## Open Questions

- Ingredient cost: latest purchase price vs moving average vs manual standard? (Leaning moving-average; confirm at Ph3.)
- Does "turno" need to be a first-class concept elsewhere (staff shifts), or is cash-session-derived enough for finance? (Cash-session for now.)
- Consolidated multi-branch reporting in this change or deferred to the multi-branch phase? (Default active-branch; consolidated later.)
