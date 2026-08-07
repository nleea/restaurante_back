## Context

The `finance` module has 2 ORM tables (`expense_categories` tenant-scoped, `expenses` branch-scoped) and domain dataclasses but no functional layer. It complements orders (sales), purchasing (cost of goods) and cash (drawer) with operating expenses. Only dependency is `employees` (staff ✅). Constraints from `CLAUDE.md`: hexagonal layering, row-level multi-tenancy, multi-branch via `branch_id`, English identifiers, "small complete system".

Facts confirmed in code:
- `expense_categories`: `name`, `is_active`. `expenses`: `expense_category_id`, `description`, `amount`, `employee_id`, `incurred_at` (server-defaulted).
- Permissions `finance.read` / `finance.manage` exist (their catalog description mentions "credits", but customer credit/fiado lives in the `customers` module; finance here is expenses only).
- `ExpenseCategory` already follows the convention; `Expense.incurred_at` is required before `id` → make optional/server-defaulted.
- `finance` is registered in `models_registry.py`; tables in migration `0002`. Shared `ValidationError` (→422) exists.

## Goals / Non-Goals

**Goals:**
- Domain ports, application service, SQLAlchemy repository, API router for expense categories and branch expenses.
- Tenant/branch isolation, reference validation, RBAC (read/manage).
- Integration tests (sqlite, FK enforcement).

**Non-Goals (deferred):**
- Posting an expense to the cash drawer (cash `out`).
- P&L / consolidated financial reporting across modules.
- Recurring/scheduled expenses, approvals, attachments.

## Decisions

**1. Mirror the established layout; one `FinanceService`.**
`domain/ports.py` (`FinanceRepository`), `application/use_cases/manage_finance.py` (`FinanceService`), `infrastructure/repositories.py` (`SqlAlchemyFinanceRepository`), `infrastructure/api/{deps,schemas,router}.py`. Smallest module so far; the pattern is unchanged.

**2. Expenses are an independent ledger (not coupled to cash).**
Recording an expense does not create a cash movement. Rationale: many expenses are paid by transfer/card or from petty cash outside the POS drawer; coupling them to a cash session now would force a model decision better made when reporting is built. A future change can optionally post a cash `out` for drawer-paid expenses. Documented.

**3. `incurred_at` is client-optional, server-defaulted.**
The request may supply `incurred_at` (back-dating a real expense) or omit it to default to now. Rationale: expenses are frequently logged after the fact; matches how `cash`/`staff` handle server-defaulted timestamps.

**4. Validation split: Pydantic for shape, service for cross-entity rules.**
Pydantic: positive amount, required description/category/employee. Service: reference existence (branch/category/employee) in tenant. Errors reuse `shared/domain/errors`.

**5. RBAC: read vs manage.**
`finance.read` for reads; `finance.manage` for all writes (categories and expenses). Matches the two existing permissions.

## Risks / Trade-offs

- **Expenses not reflected in the arqueo** → intentional; the cash drawer and the expense ledger are reconciled in a future reporting/integration change.
- **No approval workflow** → expenses are recorded directly; acceptable at pilot scale (the registering employee is captured for audit).
- **sqlite vs Postgres** → `Numeric` arithmetic and FK behavior consistent; FK enforcement enabled in tests.

## Migration Plan

1. No schema change — both tables exist in migration `0002`. Autogenerate should be a no-op (verify statically if Postgres unavailable).
2. Deploy is additive — new `/finance` endpoints, router in `main.py`. Reverting removes them.

## Open Questions

- Should drawer-paid expenses post a cash `out` movement now or later? (Default: later.)
- Should expenses support filtering by date range for reporting? (Default: branch/category filters now; date range with reporting.)
