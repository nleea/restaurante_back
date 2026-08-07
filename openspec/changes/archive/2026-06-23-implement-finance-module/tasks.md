## 1. Domain layer

- [x] 1.1 Restructure `domain/entities.py` so `Expense.incurred_at` is optional (server-defaulted), keeping the convention. `ExpenseCategory` already conforms.
- [x] 1.2 Create `domain/ports.py` with a `FinanceRepository` `Protocol`: existence checks (branch/employee/category); category create/get/list(filter active)/update; expense create/get/list(filter branch/category). Reads take `tenant_id`.

## 2. Infrastructure — repository

- [x] 2.1 Create `infrastructure/repositories.py` with `SqlAlchemyFinanceRepository(session)` implementing the port, filtering by `tenant_id` (and `branch_id`). Import staff (`EmployeeModel`) and shared `BranchModel` for reference checks.
- [x] 2.2 Implement existence helpers + ORM→entity mappers.
- [x] 2.3 Categories (create/get/list filter active/update) and expenses (create — pass optional `incurred_at`; get; list filter branch/category).

## 3. Application — service

- [x] 3.1 Create `application/use_cases/manage_finance.py` with `FinanceService(repo)` and guards `_require_branch`, `_require_employee`, `_require_category`.
- [x] 3.2 Categories: create, list (filter active), update, deactivate.
- [x] 3.3 Expenses: record (validate branch/category/employee; positive amount → else `ValidationError`; optional `incurred_at`), get, list (filter branch/category).

## 4. API layer

- [x] 4.1 Create `infrastructure/api/deps.py` (`SessionDep`, `TenantDep`, `get_finance_service`, `FinanceServiceDep`).
- [x] 4.2 Create `infrastructure/api/schemas.py` with Pydantic v2 models: category create/update; record-expense (category_id, branch_id, description, amount>0, employee_id, optional incurred_at); responses for category and expense.
- [x] 4.3 Create `infrastructure/api/router.py` with `APIRouter(prefix="/finance", tags=["finance"])`. Permission deps: read=`finance.read`, manage=`finance.manage`. Endpoints: categories create/list/update; expenses create/list(filter branch/category)/get.
- [x] 4.4 Register `finance_router` in `src/restaurante/main.py` (import + `app.include_router`).

## 5. Verification

- [x] 5.1 Confirm alembic alignment: no schema change expected (tables in `0002`); verify model↔migration statically (or autogenerate no-op if Postgres available).
- [x] 5.2 Write integration tests under `tests/modules/finance/` (sqlite, FK enforcement on) covering: tenant isolation; category CRUD; expense record + non-positive 422 + unknown branch/category/employee 404; list filtered by branch/category; RBAC 403 for read/manage. Seed an employee directly.
- [x] 5.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 5.4 Smoke-check `/finance` routes appear in the OpenAPI schema; update `docs/ESTADO_PROYECTO.md` (finance implemented).
