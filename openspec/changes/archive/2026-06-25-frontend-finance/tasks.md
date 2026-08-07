## 1. Service layer

- [x] 1.1 Create `front/src/services/finance.api.ts` with types `ExpenseCategory` and `Expense` (`amount` typed as `string`, matching backend schemas)
- [x] 1.2 Add category calls: `listCategories(active?)` (`GET /finance/categories`), `createCategory(input)` (`POST /finance/categories`), `updateCategory(id, patch)` (`PATCH /finance/categories/{id}`)
- [x] 1.3 Add expense calls: `listExpenses({ branchId, categoryId? })` (`GET /finance/expenses` with `branch_id`/`category_id` params), `getExpense(id)`, `recordExpense(input)` (`POST /finance/expenses`)
- [x] 1.4 Add service unit tests in `front/src/services/__tests__/finance.api.spec.ts` (URLs, payloads, the active/branch_id/category_id params, returned shapes)

## 2. Store layer

- [x] 2.1 Create `front/src/stores/finance.ts` (Pinia options) state: `categories`, `expenses`, `categoryFilter`
- [x] 2.2 Add `loadCategories()` and `loadExpenses(branchId, categoryId?)`; add `activeCategories` and `categoryName(id)` getters (graceful fallback)
- [x] 2.3 Add category mutations `createCategory` / `updateCategory` / `deactivateCategory` (the last calls `updateCategory(id, { is_active: false })`) — write-through refetch categories
- [x] 2.4 Add `recordExpense(input)` (write-through: refetch the branch's expenses honoring the active category filter)
- [x] 2.5 Add `total` getter (integer-cents sum of `expenses`) and `subtotalsByCategory` getter
- [x] 2.6 Add store unit tests: categories/expenses load, category-name fallback, create/deactivate write-through, record-expense refetch, total + per-category subtotal derivations

## 3. Screen, components, routing

- [x] 3.1 Add `/finance` route (name `finance`, `meta.permission: 'finance.read'`) in `front/src/router/index.ts` and a nav link (`Finanzas`) in `front/src/components/AppSidebar.vue`
- [x] 3.2 Create `front/src/views/FinanceView.vue` container + `FinancePanel.vue` orchestrator: active-branch guard, load (categories + branch expenses + staff), area switch (Gastos / Categorías), refresh, error surface
- [x] 3.3 Create the Gastos area: expense list (description, category name, amount, date) with a category filter, a running total, and per-category subtotals
- [x] 3.4 Create the record-expense dialog (gated by `finance.manage`): category, description, amount (currency input), employee picker (reuse staff store), optional date; block non-positive amount
- [x] 3.5 Create the Categorías area (gated by `finance.manage` for writes): list categories with active filter, create, rename, and deactivate
- [x] 3.6 Render amounts via `formatCOP`; resolve category names from the store and employee names from staff; surface API errors with friendly messages (reuse `apiError` helpers)

## 4. Verification

- [x] 4.1 `pnpm type-check` and `pnpm lint` clean (and `pnpm build` succeeds)
- [x] 4.2 `pnpm test:unit` green (new service + store tests included)
- [ ] 4.3 Manual smoke against the running backend: create a category → record an expense (amount, employee, date) → see it in the list with the total and per-category subtotal updating → filter by category → deactivate a category; verify a read-only user sees no manage controls
