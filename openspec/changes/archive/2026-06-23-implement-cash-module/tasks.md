## 1. Domain layer

- [x] 1.1 Restructure `domain/entities.py` so `CashSession.opened_at` is optional (server-defaulted), keeping the convention (business fields first, `id`/server-defaults optional). `CashMovement` already conforms.
- [x] 1.2 Create `domain/ports.py` with a `CashRepository` `Protocol`: branch/employee existence checks; session create/get/list (filter status)/get-open-by-branch/update-fields; movement create/list-by-session; `cash_totals(session_id)` returning summed cash-method in/out for reconciliation. Reads take `tenant_id`.

## 2. Infrastructure — repository

- [x] 2.1 Create `infrastructure/repositories.py` with `SqlAlchemyCashRepository(session)` implementing the port, filtering every query explicitly by `tenant_id` (and `branch_id`).
- [x] 2.2 Implement existence helpers (`branch_exists`, `employee_exists`) and ORM→entity mappers.
- [x] 2.3 Implement session methods (create; get; list by branch + optional status; `get_open_session(branch_id)`; update) and movement methods (create; list by session).
- [x] 2.4 Implement `cash_totals(tenant_id, session_id)` → sum of `amount` for `method='cash'` split by type `in`/`out` (via SQL aggregate), for `expected_amount` computation.

## 3. Application — service

- [x] 3.1 Create `application/use_cases/manage_cash.py` with `CashService(repo)`, a `CASH_METHOD = "cash"` constant, and guards `_require_branch`, `_require_employee`, `_require_session`, `_require_open_session` raising `NotFoundError`/`ConflictError`.
- [x] 3.2 `open_session`: validate branch + employee; reject negative opening amount (`ValidationError`); reject if branch already has an open session (`ConflictError`); create with status `open`.
- [x] 3.3 Reads: `get_session`, `list_sessions` (filter status), `get_open_session` (404 if none), `list_movements`.
- [x] 3.4 `register_movement`: require open session; validate type in/out and positive amount (`ValidationError`); persist.
- [x] 3.5 `close_session`: require open session; validate employee; reject negative counted amount; compute `expected_amount = opening + cash_in − cash_out` via `cash_totals`; set `difference`, `counted_amount`, `closed_at`, `closed_by_employee_id`, status `closed`.

## 4. API layer

- [x] 4.1 Create `infrastructure/api/deps.py` (`SessionDep`, `TenantDep`, `get_cash_service`, `CashServiceDep`) mirroring `inventory/.../deps.py`.
- [x] 4.2 Create `infrastructure/api/schemas.py` with Pydantic v2 models: open-session, register-movement (`type` `Literal["in","out"]`, `amount` `gt=0`), close-session (`counted_amount` `ge=0`); responses for session and movement. `opening_amount` `ge=0`.
- [x] 4.3 Create `infrastructure/api/router.py` with `APIRouter(prefix="/cash", tags=["cash"])`. Permission deps: read=`cash.read`, open=`cash.open`, close=`cash.close`, move=`cash.move`. Endpoints: open session; list sessions (branch + status filter); get session; get branch open session; close session; register movement; list session movements.
- [x] 4.4 Register `cash_router` in `src/restaurante/main.py` (import + `app.include_router`).

## 5. Verification

- [x] 5.1 Confirm alembic alignment: run `alembic revision --autogenerate` if Postgres is available (expect no-op); otherwise verify model↔migration statically for `cash_sessions`/`cash_movements`.
- [x] 5.2 Write integration tests under `tests/modules/cash/` (sqlite, FK enforcement on) covering: tenant isolation, open session + unknown branch/employee 404 + negative opening 422 + second-open 409, register movement (open) + non-positive 422 + on-closed 409, get-open-session 404 when none, close with reconciliation (expected = opening + cash_in − cash_out; difference; non-cash methods excluded) + close-twice 409 + negative counted 422, and RBAC 403 for read/open/move. Seed a branch + employee directly.
- [x] 5.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 5.4 Smoke-check `/cash` routes appear in the OpenAPI schema; update `docs/ESTADO_PROYECTO.md` (cash implemented; note orders→cash payment integration still pending).
