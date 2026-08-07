## 1. Domain layer

- [x] 1.1 Review `domain/entities.py`; confirm `DiningTable`, `Order`, `OrderItem`, `OrderItemAddon`, `Cancellation`, `ReceiptPrint` follow the convention. (Skip `OrderPayment` — payments deferred.)
- [x] 1.2 Create `domain/ports.py` with an `OrdersRepository` `Protocol`: reference checks (branch/employee/table-in-branch/variant/addon); dining-table CRUD; order create/get/list/update-fields; order-with-detail read; item add/get/update/delete + list-by-order; addon attach/detach + list-by-item; cancellation create; receipt create + exists-for-order. Reads take `tenant_id`.

## 2. Infrastructure — repository

- [x] 2.1 Create `infrastructure/repositories.py` with `SqlAlchemyOrdersRepository(session)` implementing the port, filtering every query explicitly by `tenant_id` (and `branch_id` where applicable).
- [x] 2.2 Implement reference helpers: `branch_exists`, `employee_exists`, `table_in_branch`, `variant_exists` (menu `ProductVariantModel`), `addon_exists` (menu `AddonModel`). Add ORM→entity mappers.
- [x] 2.3 Implement dining-table methods (create → catch unique violation → `ConflictError`; get/list/update).
- [x] 2.4 Implement order + item + addon + cancellation + receipt persistence, plus a `recompute_totals(order_id)` helper that sums line subtotals and sets `subtotal`/`total`. Group multi-row writes (item+addons, recompute) so a mutation commits once.

## 3. Application — service

- [x] 3.1 Create `application/use_cases/manage_orders.py` with `OrderService(repo)` and guards `_require_order`, `_require_open_order`, `_require_table`, `_require_employee`, `_require_branch` raising `NotFoundError`/`ConflictError`.
- [x] 3.2 Dining tables: create (positive capacity; duplicate number → `ConflictError`), list by branch, update, deactivate.
- [x] 3.3 Orders: open (validate channel literal, branch/employee/table; set table `occupied` for dine-in), get (with items+addons), list (filter status/table).
- [x] 3.4 Items: add (open order; variant exists; quantity>0; snapshot unit_price; compute line_subtotal; recompute totals), update quantity, remove (recompute totals).
- [x] 3.5 Addons: attach (addon exists; recompute line + totals), detach (recompute).
- [x] 3.6 Discount: set discount (0 ≤ discount ≤ subtotal → else `ValidationError`); recompute total.
- [x] 3.7 Cancellations: cancel item (record + mark item cancelled + recompute) and cancel order (record + status `cancelled` + free table); guard non-open → `ConflictError`.
- [x] 3.8 Close order (open→closed, stamp `closed_at`, free table; guard non-open). Receipt print (create row; `is_reprint` = order already has a print).

## 4. API layer

- [x] 4.1 Create `infrastructure/api/deps.py` (`SessionDep`, `TenantDep`, `get_order_service`, `OrderServiceDep`) mirroring `inventory/.../deps.py`.
- [x] 4.2 Create `infrastructure/api/schemas.py` with Pydantic v2 models: table create/update; order open (channel `Literal["dine_in","takeaway","delivery"]`); add-item; update-item-qty; attach-addon; set-discount; cancel; and responses (table, order, order-with-items, item, cancellation, receipt) — with `gt=0`/`ge=0` validators.
- [x] 4.3 Create `infrastructure/api/router.py` with `APIRouter(prefix="/orders", tags=["orders"])`. Permission deps: read=`orders.read`, create=`orders.create`, update=`orders.update`, cancel=`orders.cancel`. Endpoints: tables (`/orders/tables…`); orders open/list/get; items add/update/remove; addons attach/detach; discount; cancel order/item; close; receipts.
- [x] 4.4 Register `orders_router` in `src/restaurante/main.py` (import + `app.include_router`).

## 5. Verification

- [x] 5.1 Confirm alembic alignment: run `alembic revision --autogenerate` if Postgres is available (expect no-op); otherwise verify model↔migration statically for the 7 order tables.
- [x] 5.2 Write integration tests under `tests/modules/orders/` (sqlite, FK enforcement on) covering: tenant isolation, table CRUD + duplicate-number 409, open order (dine-in marks table occupied) + unknown-ref 404 + bad channel 422, add/update/remove items with totals recompute, addon attach/detach totals, discount bounds 422, cancel item + cancel order (frees table) + non-open 409, close (frees table) + non-open 409, receipt first/reprint, and RBAC 403 for read/create/cancel. Seed product variants + addons directly (menu has no variant API).
- [x] 5.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 5.4 Smoke-check `/orders` routes appear in the OpenAPI schema; update `docs/ESTADO_PROYECTO.md` (orders core implemented; note payments + inventory-deduction deferred).
