## 1. Domain layer

- [x] 1.1 Restructure `domain/entities.py` to the convention (business fields first; `id`, `created_at`, `updated_at`, `resolved_at`, `paid_at`, `received_quantity` defaulted) for all 7 entities.
- [x] 1.2 Create `domain/ports.py` with a `PurchasingRepository` `Protocol`: existence checks (branch/employee/ingredient/unit); supplier create/get/list/update; supplier-ingredient attach/exists/list/detach; request create-with-items/get/get-items/list/update; request-item bulk insert; order create-with-items/get/get-items/list/update; order-item update; payment create/list/sum-by-order; `receive_item(order_item, qty, employee, branch, order_id)` (writes inventory `in` + bumps received). Reads take `tenant_id`.

## 2. Infrastructure — repository

- [x] 2.1 Create `infrastructure/repositories.py` with `SqlAlchemyPurchasingRepository(session)` implementing the port, filtering by `tenant_id` (and `branch_id`). Import recipes (`IngredientModel`), catalog (`UnitOfMeasureModel`), staff (`EmployeeModel`), inventory (`InventoryStockModel`, `InventoryMovementModel`), shared `BranchModel`.
- [x] 2.2 Implement existence helpers + ORM→entity mappers for all entities.
- [x] 2.3 Suppliers (create/get/list filter active/update) and supplier-ingredients (attach → unique violation → `ConflictError`; exists; list by supplier; detach).
- [x] 2.4 Requests: create request + its items atomically; get; list (filter status); list items; update (status/approver/resolved_at). Orders: create order + items atomically (caller passes computed total); get; list (filter status); list items; update (status/payment_status/total); update order item.
- [x] 2.5 Goods receipt: `receive_item(tenant, order_item_id, qty, employee_id, branch_id, order_id)` — increment `received_quantity`, upsert `inventory_stocks` (+qty), insert `inventory_movements` (`in`/`purchase`, ref=order_id), commit once. Payments: create payment; `payments_total(order_id)`; list.

## 3. Application — service

- [x] 3.1 Create `application/use_cases/manage_purchasing.py` with `PurchasingService(repo)`, status constants (request `pending/approved/rejected`; order `created/partially_received/received`; payment `pending/partial/paid`), and guards `_require_*`.
- [x] 3.2 Suppliers: create/list/get/update/deactivate. Supplier-ingredients: attach (validate supplier/ingredient/unit; non-negative price; duplicate → `ConflictError`), list, detach.
- [x] 3.3 Requests: create (validate branch + requester; ≥1 item; each ingredient/unit valid; positive qty → else `ValidationError`); list/get with items; approve / reject (validate approver; only from `pending` → else `ConflictError`; set approver + `resolved_at`).
- [x] 3.4 Orders: create from an `approved` request (validate supplier; ≥1 item; positive qty/price; compute total); list/get with items.
- [x] 3.5 Receipt: `receive_items(order_id, [{order_item_id, quantity, ...}], received_by_employee_id)` — validate employee; for each line positive qty + belongs to order → `repo.receive_item`; recompute order status (`received` if all received≥ordered else `partially_received`).
- [x] 3.6 Payments: `register_payment(order_id, amount>0, method, employee)`; recompute `payment_status` from `payments_total` vs `total`; list payments.

## 4. API layer

- [x] 4.1 Create `infrastructure/api/deps.py` (`SessionDep`, `TenantDep`, `get_purchasing_service`, `PurchasingServiceDep`).
- [x] 4.2 Create `infrastructure/api/schemas.py` with Pydantic v2 models: supplier create/update; supplier-ingredient attach; request create (items: ingredient/qty>0/unit); approve/reject (employee); order create (request_id, supplier_id, items: ingredient/qty>0/unit_price≥0/unit); receive (items: order_item_id/qty>0, received_by); payment (amount>0, method, employee); responses for all entities (+ items).
- [x] 4.3 Create `infrastructure/api/router.py` with `APIRouter(prefix="/purchasing", tags=["purchasing"])`. Permission deps: read=`purchasing.read`, manage=`purchasing.manage`, approve=`purchasing.approve`. Endpoints: suppliers CRUD; supplier-ingredients attach/list/detach; requests create/list/get/approve/reject; orders create/list/get; `POST /purchasing/orders/{id}/receive`; payments create/list.
- [x] 4.4 Register `purchasing_router` in `src/restaurante/main.py` (import + `app.include_router`).

## 5. Verification

- [x] 5.1 Confirm alembic alignment: no schema change expected (tables in `0002`); verify model↔migration statically (or autogenerate no-op if Postgres available).
- [x] 5.2 Write integration tests under `tests/modules/purchasing/` (sqlite, FK enforcement on) covering: tenant isolation; supplier CRUD; supplier-ingredient attach + duplicate 409 + unknown 404; request create (with items) + empty/non-positive 422 + approve (approve-perm) + approve-non-pending 409; order from approved request + total computed + order-from-non-approved 409; receive increases stock + `in`/`purchase` movement + partial vs full status + non-positive 422; payment partial→paid + non-positive 422; RBAC 403 for read/manage/approve. Seed ingredients/units/employees directly.
- [x] 5.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 5.4 Smoke-check `/purchasing` routes appear in the OpenAPI schema; update `docs/ESTADO_PROYECTO.md` (purchasing implemented; inventory loop closed both ways).
