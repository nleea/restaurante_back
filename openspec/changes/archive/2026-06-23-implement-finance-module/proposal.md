## Why

Finance covers operating expenses — the money going out that isn't a purchase order (rent, utilities, payroll cash-outs, supplies, miscellaneous). Without it, a pilot can't see its real cost base alongside sales (orders), purchases (purchasing) and the cash drawer (cash), so daily profitability stays in a spreadsheet. The module exists only as a data layer (`expense_categories`, `expenses`). Its only dependency (`employees`) is implemented, so it can be built now to complete the back-office expense ledger.

## What Changes

- Add the **application + API layer** for the finance module (hexagonal).
- **Expense categories**: CRUD per tenant (name, active flag).
- **Expenses**: record a branch expense (category, description, positive amount, the employee who registered it, and an `incurred_at` that defaults to now or may be back-dated); list expenses (filter by branch and/or category) and get one. The expense category and branch MUST belong to the current tenant.
- Enforce **multi-tenant + multi-branch isolation** and **RBAC**: `finance.read` (reads), `finance.manage` (all writes).
- Register the new router in `main.py`.
- No ORM model changes expected — tables and the `finance` registration already exist; the `Expense` entity gets a minor tidy (`incurred_at` optional/server-defaulted).

### Explicitly out of scope (deferred)
- **Posting an expense to the cash drawer** (a cash `out` movement) — expenses here are an independent ledger; a future change could link cash-paid expenses to an open cash session.
- **Profit & loss / consolidated financial reports** — combining sales, purchases, expenses and cash into P&L belongs to a reporting change.
- **Customer store credit (fiado)** — already implemented in the `customers` module; not part of finance.

## Capabilities

### New Capabilities
- `finance-management`: Operating-expense ledger — expense categories and branch expenses. Tenant/branch-isolated and RBAC-protected.

### Modified Capabilities
<!-- None — no existing spec's requirements change. -->

## Impact

- **New code** under `src/restaurante/modules/finance/`: `domain/ports.py`, `application/use_cases/manage_finance.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`; minor restructure of `domain/entities.py` (`incurred_at` optional).
- **Modified**: `src/restaurante/main.py` (include `finance_router`).
- **Depends on** existing tables `employees` (staff), `branches` — validated for existence; and the identity RBAC `require_permission` dependency.
- **Reused**: tenant middleware, `shared/database.get_session`, `shared/domain/errors` (`NotFoundError`, `ConflictError`, `ValidationError`), RBAC `require_permission`.
- **APIs**: new `/finance/*` endpoints (categories, expenses). No breaking changes.
- **Tests**: new integration suite under `tests/modules/finance/` (sqlite, FK enforcement) — seeds an employee directly.
