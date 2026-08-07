## Context

Finanzas already computes revenue, expenses, COGS and a P&L on an **accrual** basis (see the archived `finance-reporting` change). The gap is a **cash view**: a purchase of insumos is not an `expense` and only becomes COGS when the dish sells, so the cash that left the drawer/bank is invisible; and the Resumen "flujo de caja" widget is a proxy (`Σ order.total − Σ expenses.amount` running balance) that never reads real money movements.

Money movements already live in the transactional tables:

- `order_payments`: `amount`, `method`, `employee_id`, `cash_session_id`, tied to an `order` (sales received).
- `customer credit payments`: AR abonos (money in).
- `purchase_payments`: supplier payments, **all methods** (cash + transfer + credit) — the authoritative record of what was paid for a purchase.
- `expenses`: operating spend (`amount`, `incurred_at`, `expense_category_id`); **no `method`, no paid-at**.
- `cash_movements`: `type` (in/out), `concept`, `amount`, `method`, `cash_session_id`, `reference_id`. A `sale`/`credit_payment`/`purchase_payment` row is written **per event** (a partial mirror of the tables above), plus manual `ingresos`/`retiros` that exist nowhere else.

Constraints: hexagonal (`API → application → domain`), row-level `tenant_id` + `branch_id`, English identifiers, `finance.read` for reads, follow the existing `reports` module (cross-cutting read-only layer that reads other modules' tables, never their write paths).

## Goals / Non-Goals

**Goals:**
- A read-only, cash-basis, method-agnostic **money-in / money-out** report for a branch and period, from authoritative sources, with **no double counting**.
- Make a purchase of insumos visible as an **outflow when paid** (any method), while COGS still hits the P&L only on sale — both correct, coexisting.
- A **daily net-cash series** and a **category breakdown**, plus a **cash-vs-other split** that reconciles the physical-cash portion with the arqueo.
- Replace the fake Resumen widget and wire the Reportes "Flujo de caja" card to the real data.

**Non-Goals:**
- Bank-account modeling and any **absolute cash balance** — we report **net flow** only.
- A GAAP cash-flow statement (operating / investing / financing sections).
- Schema changes: adding `expenses.method` / `paid_at`, or AP aging.
- Changing any write behavior; this change only reads.

## Decisions

### D1 — Authoritative-source aggregation with an explicit de-dup rule

Each flow is read from the table that **owns** it, and `cash_movements` contributes **only its manual rows**:

```
INFLOWS
  ventas            ← order_payments               (branch, all methods)
  abonos crédito    ← cash_movements[type=in, concept=credit_payment]   (branch, cash)
  ingresos de caja  ← cash_movements[type=in]  WHERE concept NOT IN (sale, credit_payment)
OUTFLOWS
  compras           ← purchase_payments ⋈ purchase_orders (branch, all methods)  ← the insumo purchase
  gastos            ← expenses                     (branch)
  retiros de caja   ← cash_movements[type=out] WHERE concept <> purchase_payment
NET = Σ inflows − Σ outflows   (each flow read from exactly one source)
```

**Why:** `cash_movements` is a partial mirror — summing it *and* the source tables would double-count. The invariant is **each flow read from exactly one source**: sales from `order_payments` (branch-scoped, all methods; the `sale` movement is excluded), supplier spend from `purchase_payments` (all methods; the cash `purchase_payment` movement is excluded), expenses from `expenses`, and the *manual* retiros/ingresos from `cash_movements`.

**Branch-scoping caveat (implementation reality):** `purchase_payments`, `customer_credit_payments` and `customer_credits` are **tenant-scoped** (no `branch_id`). Supplier payments are branch-scoped by joining `purchase_orders` (which carries `branch_id`). Customer credit payments have **no** branch on the source table, so credit abonos are read from their **branch-scoped `cash_movements[concept=credit_payment]`** (which only exist for cash abonos); non-cash abonos have no branch and are out of scope for a branch cash flow. This is not double counting — the source table is not read for abonos. **Alternative rejected:** aggregate everything from `cash_movements` — misses non-cash supplier payments and all `expenses` (which never post a movement), and misses card/Nequi sales.

### D2 — Cash-basis dates, no schema change

Each source contributes on its **own best available date**: `order_payments` timestamp, `purchase_payments` payment date, `cash_movements.created_at`, and **`expenses.incurred_at` treated as the cash date**. **Why:** keeps the change a pure read aggregation; `expenses` has no paid-at, and for pilots incurred≈paid is close enough. **Trade-off:** an expense recorded late lands on its incurred date, not its true payment date — acceptable until an explicit `method`/`paid_at` is added (deferred).

### D3 — Net flow, not balance

We expose `inflows`, `outflows`, `net`, a daily series and category totals — but **no absolute cash-on-hand**, because there is no bank-account entity and non-cash money leaves the system's view (card settlements, transfers). **Why:** an absolute balance would be wrong/misleading without bank modeling. The Reporte Z arqueo remains the source of truth for physical drawer balance.

### D4 — Cash-vs-other split for reconciliation

The response separates the **cash-method** portion (which, for a period that maps to sessions, reconciles with the arqueo) from **other methods** (tarjeta/Nequi/transferencia), labeled "en tránsito a banco". **Why:** it lets an operator sanity-check the cash line against the drawer while still seeing total business cash flow. Method normalization: group by `order_payments.method` / `purchase_payments.method` / `cash_movements.method`; `cash` vs everything else. **`expenses` carry no method**, so they are classified as **other** (not cash) — consistent with the arqueo, which never saw them (expenses post no cash movement). Documented until an explicit expense `method` exists (deferred).

### D5 — Frontend: replace the proxy, reuse the chart

The real net-cash daily series replaces the fake series behind the existing Resumen cash-flow chart (`CashFlowLine`), and the Reportes "Flujo de caja" card (`key: 'flujo'`) opens a breakdown (inflows/outflows by category + the cash-vs-other split). One new `getCashFlow` client; the global period/branch filter drives it like the other reports.

## Risks / Trade-offs

- **Double counting from the mirror ledger** → the de-dup rule (D1) is the load-bearing invariant; cover it with a test that seeds a `sale` movement + its `order_payment` and asserts the sale is counted once.
- **Expense date ≠ payment date** (D2) → documented; revisit with `expenses.paid_at` if pilots need precise cash timing.
- **"Cash flow" read as a bank balance** → expose net flow only, label the cash-vs-other split, and keep arqueo as the drawer's truth (D3/D4).
- **Non-cash supplier payment previously invisible** → now visible via `purchase_payments`; ensure the query reads all methods, not only cash.
- **Aggregation cost at scale** → live `GROUP BY` over transactional tables like the rest of `reports`; existing indexes on `orders(branch_id, closed_at)` / `order_payments(cash_session_id)` help. Revisit rollups only if pilots outgrow live queries.

## Migration Plan

1. Backend: add cash-flow entities/ports/repository methods + `ReportsService.cash_flow` + `GET /reports/cash-flow` + schemas + tests. No DB migration.
2. Frontend: add `getCashFlow`; swap the Resumen widget's data source; wire the "Flujo de caja" report card.
3. Rollback = remove the additive endpoint/UI; the fake widget can be restored trivially (no data loss, read-only).

## Open Questions

- Should `expenses` gain `method` + `paid_at` in a later change so cash-basis timing is exact? (Deferred; incurred≈paid for now.)
- Is a consolidated multi-branch cash flow needed, or is per-branch enough for pilots? (Per-branch now, consistent with the rest of `reports`.)
