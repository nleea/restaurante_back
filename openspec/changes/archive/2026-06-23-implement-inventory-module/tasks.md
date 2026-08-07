## 1. Domain layer

- [x] 1.1 Restructure `domain/entities.py` to the project convention (business fields first; `id`, `created_at`, `updated_at` optional with defaults) for `InventoryStock` and `InventoryMovement`, framework-free.
- [x] 1.2 Create `domain/ports.py` with an `InventoryRepository` `Protocol`: branch/ingredient/employee existence checks; get/list stock; list low-stock; upsert min_stock; get-or-create stock row; `apply_movement` (atomic: insert movement + update stock); list movements. Reads take `tenant_id` and return entity-or-`None`.

## 2. Infrastructure — repository

- [x] 2.1 Create `infrastructure/repositories.py` with `SqlAlchemyInventoryRepository(session)` implementing `InventoryRepository`, filtering every query explicitly by `tenant_id` (and `branch_id`).
- [x] 2.2 Implement existence helpers: `branch_exists`, `ingredient_exists` (query `IngredientModel` scoped by tenant), `employee_exists` (query `EmployeeModel` scoped by tenant).
- [x] 2.3 Implement `apply_movement`: read-or-create the `(ingredient_id, branch_id)` stock row, adjust `current_quantity`, insert the `inventory_movements` row, and `commit()` once (single transaction). Add ORM→entity mappers.
- [x] 2.4 Implement `set_min_stock` (upsert stock row, set threshold), `get_stock`, `list_stock`, `list_low_stock`, `list_movements`.

## 3. Application — service

- [x] 3.1 Create `application/use_cases/manage_inventory.py` with `InventoryService(repo)` and private guards `_require_branch`, `_require_ingredient`, `_require_employee` raising `NotFoundError`.
- [x] 3.2 Implement read use cases: `get_stock`, `list_stock`, `list_low_stock` (validate branch).
- [x] 3.3 Implement `set_min_stock`: validate branch + ingredient, reject negative threshold (`ValidationError`).
- [x] 3.4 Implement `register_movement` (type `in`/`out`): validate branch/ingredient/employee; reject quantity ≤ 0 (`ValidationError`); reject `out` exceeding on-hand (`ConflictError`); delegate to `apply_movement`.
- [x] 3.5 Implement `recount`: validate refs; reject negative counted value; compute delta vs current on-hand and record an `adjustment` movement via `apply_movement`.
- [x] 3.6 Implement `list_movements` (validate branch + ingredient).

## 4. API layer

- [x] 4.1 Create `infrastructure/api/deps.py` (`SessionDep`, `TenantDep`, `get_inventory_service`, `InventoryServiceDep`) mirroring `staff/.../deps.py`.
- [x] 4.2 Create `infrastructure/api/schemas.py` with Pydantic v2 request/response models (stock, movement, set-threshold, register-movement, recount) with positive-quantity / non-negative-threshold validators and a `type` literal `in`/`out`.
- [x] 4.3 Create `infrastructure/api/router.py` with `APIRouter(prefix="/inventory", tags=["inventory"])`; reads use `Depends(require_permission("inventory.read"))`, writes use `Depends(require_permission("inventory.adjust"))`. Endpoints for stock view, low-stock, set threshold, register movement, recount, movement history (branch in path).
- [x] 4.4 Register `inventory_router` in `src/restaurante/main.py` (import + `app.include_router`).

## 5. Verification

- [x] 5.1 Confirm alembic alignment: run `alembic revision --autogenerate` if Postgres is available (expect no-op); otherwise verify model↔migration statically for `inventory_stocks`/`inventory_movements`.
- [x] 5.2 Write integration tests under `tests/modules/inventory/` (sqlite, FK enforcement on) covering: tenant isolation, unknown branch/ingredient/employee 404, stock-in creates row + increases, stock-out decreases, over-draw 409, non-positive quantity 422, recount records delta, low-stock view, movement history order, and RBAC 403 for read/write without permission. Add a helper that inserts an `ingredient` directly (recipes has no API yet).
- [x] 5.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 5.4 Smoke-check `/inventory` routes appear in the OpenAPI schema.
