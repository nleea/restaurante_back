## Why

The backend `/finance` module — an operating-expense ledger of tenant expense categories and
branch expenses (rent, utilities, supplies, miscellaneous) — has no frontend, so a manager can't
record or review what the branch spends. With sales (orders), cost of goods (purchasing), and the
cash drawer (cash) already on screen, expenses are the missing piece of the real cost base: without
them the pilot restaurants track outgoings in a spreadsheet.

## What Changes

- Add a **Finance service layer** (`finance.api.ts`) over `/finance`: expense categories
  (`GET /finance/categories?active=`, `POST /finance/categories`,
  `PATCH /finance/categories/{id}` — which both renames and deactivates via `is_active`) and
  expenses (`GET /finance/expenses?branch_id=&category_id=`, `GET /finance/expenses/{id}`,
  `POST /finance/expenses`).
- Add a **Finance store** (`finance.ts`): the tenant's expense categories and the active branch's
  expenses (the list endpoint filters by `branch_id`, optionally by `category_id`), plus client-side
  derivations — the total of the listed expenses and per-category subtotals, so the screen shows the
  branch's cost base at a glance. Amounts are carried as string-decimals.
- Add the **FinanceView** screen with two areas, mobile-first per the house pattern:
  - **Gastos** (expenses): the active branch's expenses with an optional category filter, a running
    **total** and per-category subtotals, and a **registrar gasto** action (category, description,
    amount, registering employee, optional date). Read needs `finance.read`; recording needs
    `finance.manage`.
  - **Categorías**: list categories (active filter), create, rename, and deactivate — all gated by
    `finance.manage`.
- Add the **route + nav entry** (`/finance`, permission `finance.read`) and a navigation link.
- Unit tests for the service and store (URLs/payloads/filters, write-through refetch, category-label
  resolution, and the total / per-category subtotal derivations).

Non-goals: posting an expense to the POS cash drawer (a cash `out` — backend keeps these separate);
consolidated P&L or profit reporting (explicitly out of the backend capability's scope);
recurring/scheduled expenses; editing or deleting a recorded expense; customer store credit (fiado,
which lives in the customers capability); and realtime/auto-refresh (manual refresh this slice).

## Capabilities

### New Capabilities
- `frontend-finance`: the operating-expense frontend — manage tenant expense categories
  (create/rename/deactivate) and record and review the active branch's expenses (with a category
  filter, a running total, and per-category subtotals), gated by `finance.read` / `finance.manage`,
  with the registering employee chosen from staff and category names resolved from the categories
  list.

### Modified Capabilities
<!-- None. Consumes the existing finance-management backend unchanged; employee data is read-only
     from staff-management. -->

## Impact

- **Frontend code**: new `front/src/services/finance.api.ts`, `front/src/stores/finance.ts`,
  `front/src/views/FinanceView.vue`, and `front/src/components/finance/*`; a route in
  `front/src/router/index.ts` and a nav link in `front/src/components/AppSidebar.vue`. New tests
  under `front/src/services/__tests__` and `front/src/stores/__tests__`.
- **Reuses**: the staff store (employee picker for recording an expense), the active-branch context
  (expense list + create are branch-scoped), the shared `http` axios instance, `@/lib/money`
  `formatCOP`, and the `apiError` helpers.
- **Backend**: none — consumes existing `/finance` category and expense endpoints.
- **Permissions/RBAC**: relies on `finance.read` (screen + reads) and `finance.manage` (category
  create/rename/deactivate, record expense); employee labels additionally read staff data. No new
  permission codes.
- **Dependencies**: no new packages; PrimeVue + Tailwind + Axios as elsewhere.
