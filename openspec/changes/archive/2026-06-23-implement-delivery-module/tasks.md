## 1. Domain layer

- [x] 1.1 Review `domain/entities.py`; confirm `DeliveryRoute`, `DeliveryRouteDriver`, `DeliveryRun`, `OrderDelivery` follow the convention (no change expected).
- [x] 1.2 Create `domain/ports.py` with a `DeliveryRepository` `Protocol`: existence checks (branch/employee/order); route create/get/list/update; route-driver attach/exists/list/active-driver-on-route/detach; delivery create/get-by-order/get/list(filter status)/update; run create/get/list(filter status)/update; `set_assigned_deliveries_in_transit(run_id)`. Reads take `tenant_id`.

## 2. Infrastructure — repository

- [x] 2.1 Create `infrastructure/repositories.py` with `SqlAlchemyDeliveryRepository(session)` implementing the port, filtering every query explicitly by `tenant_id` (and `branch_id` where applicable). Import staff (`EmployeeModel`) and orders (`OrderModel`) models for reference checks.
- [x] 2.2 Implement existence helpers + ORM→entity mappers.
- [x] 2.3 Implement routes (create/get/list by branch/update) and route-drivers (attach → catch unique violation → `ConflictError`; exists; list by route; `is_active_driver_on_route`; detach).
- [x] 2.4 Implement deliveries (create → catch unique `order_id` → `ConflictError`; get by order; get; list filter status; update) and runs (create; get; list filter status; update). Add `mark_run_deliveries_in_transit(tenant, run_id)` updating all `assigned` deliveries of the run to `in_transit`.

## 3. Application — service

- [x] 3.1 Create `application/use_cases/manage_delivery.py` with `DeliveryService(repo)`, status constants (delivery: `pending/assigned/in_transit/delivered/not_delivered`; run: `preparing/in_transit/finished`), and guards `_require_branch`, `_require_order`, `_require_route`, `_require_run`, `_require_delivery`.
- [x] 3.2 Routes: create (validate branch), list by branch, update, deactivate.
- [x] 3.3 Route drivers: attach (validate route + employee; duplicate → `ConflictError`), list by route, detach.
- [x] 3.4 Deliveries: create (validate order; one-per-order → `ConflictError`; address required), get by order, list (filter status), update address fields.
- [x] 3.5 Runs: create (validate route; employee MUST be an active driver of the route → else `ValidationError`/`NotFoundError`), get, list (filter status).
- [x] 3.6 Lifecycle: `assign_delivery` (run `preparing`; delivery `pending`/`assigned` → set run+route, status `assigned`); `depart_run` (`preparing→in_transit`, `departed_at`, cascade assigned→`in_transit`); `mark_delivered(delivered: bool)` (delivery `in_transit` → `delivered`/`not_delivered`, `delivered_at`); `finish_run` (`in_transit→finished`, `finished_at`). Guard out-of-order transitions with `ConflictError`.

## 4. API layer

- [x] 4.1 Create `infrastructure/api/deps.py` (`SessionDep`, `TenantDep`, `get_delivery_service`, `DeliveryServiceDep`).
- [x] 4.2 Create `infrastructure/api/schemas.py` with Pydantic v2 models: route create/update; attach-route-driver; create-delivery (address required, optional neighborhood/lat/long); update-delivery-address; create-run; mark-delivered (`delivered: bool`); responses for route, route-driver, delivery, run.
- [x] 4.3 Create `infrastructure/api/router.py` with `APIRouter(prefix="/delivery", tags=["delivery"])`. Permission deps: read=`delivery.read`, manage=`delivery.manage`, assign=`delivery.assign`. Endpoints: routes CRUD; route-drivers attach/list/detach; deliveries create/get-by-order/list/update; runs create/get/list; lifecycle `assign`, `depart`, `mark-delivered`, `finish`.
- [x] 4.4 Register `delivery_router` in `src/restaurante/main.py` (import + `app.include_router`).

## 5. Verification

- [x] 5.1 Confirm alembic alignment: no schema change expected (tables in `0002`); verify model↔migration statically (or autogenerate no-op if Postgres available).
- [x] 5.2 Write integration tests under `tests/modules/delivery/` (sqlite, FK enforcement on) covering: tenant isolation; route CRUD + unknown-branch 404; route-driver attach + duplicate 409 + detach; delivery create + one-per-order 409 + unknown-order 404 + list/filter; run create requires driver-on-route (reject otherwise); lifecycle assign (reject on departed run 409) → depart (cascades to in_transit) → mark delivered/not_delivered → finish (reject non-in_transit 409); RBAC 403 for read/manage/assign. Seed employees and delivery-channel orders directly.
- [x] 5.3 Run `poetry run ruff check .`, `poetry run mypy src`, and `poetry run pytest` — all green.
- [x] 5.4 Smoke-check `/delivery` routes appear in the OpenAPI schema; update `docs/ESTADO_PROYECTO.md` (delivery implemented).
