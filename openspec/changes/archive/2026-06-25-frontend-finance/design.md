## Context

The backend `/finance` module is an **operating-expense ledger** (not P&L reporting, which is
explicitly out of the capability's scope). Its contract:

- **Categories** (tenant-scoped — no branch): `POST /finance/categories` (`{ name }`),
  `GET /finance/categories?active=`, `PATCH /finance/categories/{id}` (`{ name?, is_active? }`).
  There is **no** DELETE — deactivation is `PATCH { is_active: false }`. Perm `finance.read` (read)
  / `finance.manage` (write).
- **Expenses** (branch-scoped): `POST /finance/expenses`
  (`{ branch_id, expense_category_id, description, amount, employee_id, incurred_at? }`),
  `GET /finance/expenses?branch_id=&category_id=`, `GET /finance/expenses/{id}`.
- `ExpenseCategory = { id, name, is_active }`. `Expense = { id, branch_id, expense_category_id,
  description, amount, employee_id, incurred_at }`. `amount` is a server-side `Decimal`, serialized
  as a **string**; `incurred_at` is optional (no server default).

Three facts drive the design: (1) **categories are tenant-scoped, expenses branch-scoped** — so the
screen mixes a tenant master-data list (categories) with a branch-filtered ledger (expenses),
filtering expenses by the active branch's id via the query param; (2) `amount` is **money**, so it
renders with `formatCOP` and is captured with the currency InputNumber; and (3) the module's whole
point is "see the real cost base", so the screen earns its keep with a **client-side total and
per-category subtotals** over the loaded expenses. The expense record needs a category, an employee
(reused from staff), and an optional date. Conventions follow the existing screens (Vue 3
`<script setup>`, Pinia options stores, PrimeVue + Tailwind, the shared `@/lib/http` axios instance,
active-branch scope, mobile-first; categories management mirrors the suppliers screen, expenses the
cash ledger).

## Goals / Non-Goals

**Goals:**
- A working expense ledger: record branch expenses and review them with a running total and
  per-category breakdown, plus manage the tenant's expense categories.
- Reuse the staff employee picker and the active-branch context; resolve category names from the
  loaded categories.
- Mirror the established store discipline (write-through, `can()` gating) and the two-area UX.

**Non-Goals:**
- Posting an expense to the POS cash drawer; consolidated P&L / profit reporting; recurring expenses;
  editing/deleting a recorded expense; customer store credit (fiado — customers capability);
  realtime/auto-refresh.

## Decisions

**1. One `FinanceView` with two areas (Gastos / Categorías).** Expenses is the default; categories
is the supporting master data. The two share a screen via the house tabbed pattern, both gated by
`finance.read`. Rejected: a single screen with categories hidden in a dialog — categories deserve
their own manageable list, and tabs match the procurement screen the user just shipped.

**2. Amount stays string-decimal; the only client arithmetic is the total and subtotals.** The
currency InputNumber captures a number sent as `toFixed(2)`; `formatCOP` renders. The total and
per-category subtotals sum in **integer cents** (as the cash/procurement screens do) to avoid float
drift. These are presentational summaries, not authoritative accounting — there is no server total
endpoint, so the client sums the loaded list and the displayed total always matches the visible
rows (and the active category filter).

**3. Expenses are branch-scoped via the query param; categories are tenant-wide.** The store loads
expenses with `branch_id = activeBranchId` (and `category_id` when a filter is active) and loads
categories once for the tenant. Re-scoping on branch change reloads expenses; categories persist.

**4. Category filter drives both the list and the total.** Selecting a category refetches expenses
with `category_id` (server-side filter) so the list and the derived total/subtotals stay consistent
with one source of truth, rather than fetching all and filtering twice.

**5. Record-expense reuses the staff employee picker and an optional date.** `employee_id` comes
from the staff store's active-branch employees (load on demand, as cash/inventory do). `incurred_at`
is an optional date input (PrimeVue DatePicker); omitted means the backend records it without a
client default. Category and description round out the form.

**6. Store shape parallels the suppliers/inventory stores.** State: `categories: ExpenseCategory[]`,
`expenses: Expense[]`, `categoryFilter: string | null`. Getters: `activeCategories`,
`categoryName(id)`, `total` (integer-cents sum of `expenses`), `subtotalsByCategory`. Actions (each
write-through): `loadCategories()`, `loadExpenses(branchId, categoryId?)`, `createCategory`,
`updateCategory`, `deactivateCategory`, `recordExpense` (refetch the branch's expenses).

**7. Permission model mirrors existing screens.** Route guard `meta.permission: 'finance.read'`;
within the view, `auth.can('finance.manage')` gates record-expense and category create/rename/
deactivate. Read-only users see expenses, the total, and categories without action affordances. The
backend enforces the same permissions regardless.

## Risks / Trade-offs

- **Client total over the loaded list only** → if the backend ever paginates expenses, the total
  would reflect only the loaded page. → Mitigation: no pagination today; the total is explicitly the
  sum of the shown rows, and the category filter keeps it scoped. Flagged for when volume grows.
- **No GET-by-category-name / labels are list-resolved** → a category not in the loaded list (e.g.
  an expense referencing a since-removed category) shows a short ref. → Mitigation: load categories
  with the expenses; degrade clearly.
- **No DELETE for categories** → deactivation is a PATCH; a category in use stays referenced by past
  expenses. → Mitigation: deactivate (not delete) and keep resolving its name for historical rows.
- **Money correctness** → amounts via `formatCOP` and integer-cents sums; never `parseFloat`
  accumulation.

## Migration Plan

Pure additive frontend change; no backend deploy, no data migration. Ship behind existing
`finance.read` / `finance.manage` permissions. Rollback = revert the new files, the router entry,
and the nav link; no persisted client state.

## Open Questions

- Should the expense list support a date range filter? Deferred — the backend filters by branch and
  category only; a date filter is a clean future add (client or backend).
- Should the total area break expenses down by period (day/month)? Deferred — out of the ledger
  scope this slice; the per-category subtotal is the cost-base view for now.
