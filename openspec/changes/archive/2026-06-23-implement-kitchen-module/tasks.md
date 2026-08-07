## 1. Domain layer

- [x] 1.1 Restructure `domain/entities.py` so `OrderItemStation.entered_at` is optional (server-defaulted), keeping the convention. `KitchenStation`/`ProductStation` already conform.
- [x] 1.2 Create `domain/ports.py` with a `KitchenRepository` `Protocol`: existence checks (branch/product/station/order); station create/get/list/update; product-station attach/exists/list/detach; `variant_product_id(variant_id)`; order non-cancelled items read; ticket create/exists(item,station)/list-by-station(filter status)/get/update. Reads take `tenant_id`.

## 2. Infrastructure — repository

- [x] 2.1 Create `infrastructure/repositories.py` with `SqlAlchemyKitchenRepository(session)` implementing the port, filtering every query explicitly by `tenant_id` (and `branch_id` where applicable). Import menu (`ProductModel`, `ProductVariantModel`) and orders (`OrderModel`, `OrderItemModel`) models for cross-module reads.
- [x] 2.2 Implement existence helpers (`branch_exists`, `product_exists`, `station_in_tenant`, `order_exists`) and ORM→entity mappers.
- [x] 2.3 Implement station methods (create/get/list by branch/update) and product-station methods (attach → catch unique violation → `ConflictError`; exists; list by product; detach).
- [x] 2.4 Implement routing support: `variant_product_id(tenant, variant_id)`; `list_non_cancelled_items(tenant, order_id)`; `ticket_exists(tenant, order_item_id, station_id)`; `create_ticket(...)`. Implement board reads: `list_tickets(tenant, station_id, status=None)`, `get_ticket`, `update_ticket`.

## 3. Application — service

- [x] 3.1 Create `application/use_cases/manage_kitchen.py` with `KitchenService(repo)`, status constants (`pending`/`in_progress`/`ready`), and guards `_require_branch`, `_require_product`, `_require_station`, `_require_order`, `_require_ticket`.
- [x] 3.2 Stations: create (validate branch), list by branch, update, deactivate.
- [x] 3.3 Product routing: attach (validate product + station; duplicate → `ConflictError`), list by product, detach.
- [x] 3.4 `route_order`: validate order; for each non-cancelled item resolve product via variant, find its stations, and create a `pending` ticket per (item, station) not already present (idempotent); skip items with no station.
- [x] 3.5 Board: `list_tickets` (validate station; optional status filter); `advance_ticket` (`pending→in_progress→ready`; stamp `ready_at`; reject advancing a `ready` ticket → `ConflictError`).

## 4. API layer

- [x] 4.1 Create `infrastructure/api/deps.py` (`SessionDep`, `TenantDep`, `get_kitchen_service`, `KitchenServiceDep`).
- [x] 4.2 Create `infrastructure/api/schemas.py` with Pydantic v2 models: station create/update; attach-product-station; responses for station, product-station, ticket; optional status query for the board.
- [x] 4.3 Create `infrastructure/api/router.py` with `APIRouter(prefix="/kitchen", tags=["kitchen"])`. Permission deps: read=`kitchen.read`, write=`kitchen.update`. Endpoints: stations CRUD; product-station attach/list/detach; `POST /kitchen/orders/{order_id}/route`; `GET /kitchen/stations/{station_id}/tickets`; `POST /kitchen/tickets/{ticket_id}/advance`.
- [x] 4.4 Register `kitchen_router` in `src/restaurante/main.py` (import + `app.include_router`).

## 5. Verification

- [x] 5.1 Confirm alembic alignment: no schema change expected (tables in `0002`); verify model↔migration statically (or autogenerate no-op if Postgres available).
- [x] 5.2 Write integration tests under `tests/modules/kitchen/` (sqlite, FK enforcement on) covering: tenant isolation, station CRUD + unknown-branch 404, product-station attach + duplicate 409 + detach, route order creates tickets per station / skips no-station items / skips cancelled / idempotent, board list by station + status filter, advance lifecycle pending→in_progress→ready (ready_at set) + advance-ready 409, and RBAC 403 for read/update. Seed products/variants and order items directly.
- [x] 5.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 5.4 Smoke-check `/kitchen` routes appear in the OpenAPI schema; update `docs/ESTADO_PROYECTO.md` (kitchen implemented).
