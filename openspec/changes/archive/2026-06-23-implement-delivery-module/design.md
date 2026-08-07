## Context

The `delivery` module has ORM models (`delivery_routes`, `delivery_route_drivers`, `delivery_runs`, `order_deliveries`) and domain dataclasses but no functional layer. `staff` (drivers are employees) and `orders` are implemented. Binding decisions from `CLAUDE.md`: **own fleet, no external apps**; real driver management, manual/auto assignment, explicit states (`pendiente → asignado → en camino → entregado/no entregado`); cash-on-delivery touches Caja. Plus hexagonal layering, row-level multi-tenancy, multi-branch via `branch_id`, English identifiers.

Facts confirmed in code:
- `delivery_routes` is branch-scoped; `delivery_route_drivers`, `delivery_runs`, `order_deliveries` are tenant-scoped (they hang off a route/order that fixes the branch).
- `delivery_route_drivers` bridges route↔employee, unique on the pair.
- `delivery_runs`: `delivery_route_id`, `employee_id`, `status` (`preparing` default), `departed_at`, `finished_at`.
- `order_deliveries`: `order_id` (unique), nullable `delivery_route_id`/`delivery_run_id`, address/neighborhood/lat/long, `delivery_status` (`pending` default), `route_position`, `delivered_at`.
- Dependencies `employees` and `orders` exist; permissions `delivery.read` / `delivery.assign` / `delivery.manage` exist. Entities already follow the convention.
- `delivery` is registered in `models_registry.py`; tables in migration `0002`. Shared `ValidationError` (→422) exists.

## Goals / Non-Goals

**Goals:**
- Domain ports, application service, SQLAlchemy repository, and API router for: routes CRUD; route drivers; per-order delivery records; dispatch runs; and the assign → depart → deliver → finish lifecycle with explicit states.
- Tenant/branch isolation, cross-module reference validation, RBAC split across the three delivery permissions.
- Integration tests (sqlite, FK enforcement).

**Non-Goals (deferred):**
- Cash-on-delivery payment capture (use the existing orders→cash payment flow).
- Auto-assignment by zone and route optimization (manual assignment now; geo/`route_position` stored for later).
- Live GPS tracking.
- Reflecting delivery state back into the order's `orders` status.

## Decisions

**1. Mirror the established module layout; one `DeliveryService`.**
`domain/ports.py` (`DeliveryRepository` Protocol), `application/use_cases/manage_delivery.py` (`DeliveryService`), `infrastructure/repositories.py` (`SqlAlchemyDeliveryRepository`), `infrastructure/api/{deps,schemas,router}.py`. Rationale: consistency with seven working references.

**2. Two explicit state machines, forward-only.**
Delivery: `pending → assigned → in_transit → delivered | not_delivered`. Run: `preparing → in_transit → finished`. Each transition is guarded (e.g. assign requires a `preparing` run and a `pending`/`assigned` delivery; mark-delivered requires `in_transit`; finish requires `in_transit`) and rejects out-of-order moves with `ConflictError`. Rationale: the scope demands explicit states, not a free-text field; guards prevent nonsensical jumps.

**3. A run's driver must be an active driver of its route.**
Creating a run validates that `employee_id` is an active `delivery_route_drivers` entry for the route (else `NotFoundError`/`ValidationError`). Rationale: gives `delivery_route_drivers` a real enforcement purpose and matches "real driver management"; you cannot dispatch a driver who does not serve the route.

**4. Departing a run cascades its assigned deliveries to `in_transit`.**
`depart_run` flips the run and, in the same transaction, moves every `assigned` delivery on that run to `in_transit` and stamps the run's `departed_at`. Rationale: a single dispatch event; keeping it atomic avoids deliveries stuck `assigned` after the driver left. Marking individual deliveries `delivered`/`not_delivered` stays per-delivery (drivers report each drop).

**5. One delivery record per order (enforced by the unique `order_id`).**
`create_delivery` rejects a second record for the same order (`ConflictError`), via a pre-check plus the DB unique constraint. Rationale: an order has a single destination.

**6. RBAC split: manage vs assign vs read.**
`delivery.manage` for configuration/creation (routes, route drivers, delivery records, runs); `delivery.assign` for operational lifecycle (assign, depart, mark delivered, finish); `delivery.read` for reads. Rationale: a dispatcher who assigns/advances need not be able to reconfigure routes; matches the three existing permissions.

**7. Validation split: Pydantic for shape, service for business rules.**
Pydantic: required address, optional geo, status filter literals. Service: reference existence (branch/order/route/employee) in tenant, driver-on-route check, one-delivery-per-order, state guards. Errors reuse `shared/domain/errors`.

## Risks / Trade-offs

- **Manual assignment only** → a dispatcher assigns each delivery to a run by hand; fine for pilot volumes. Auto-assignment by zone is a later change (geo already captured).
- **Cash-on-delivery not auto-captured** → the driver collects cash and it is recorded via the existing order payment endpoint; a future change can prompt payment on `delivered`. Documented to avoid a half-built money path.
- **Concurrent depart/assign** could race (assign to a run being departed) → acceptable at pilot scale; guards + single-session transactions cover the common path.
- **No back-link to order status** → intentional; cross-module status sync is out of scope.
- **sqlite vs Postgres** → enum-as-string states, FK and unique constraints behave consistently; FK enforcement enabled in tests.

## Migration Plan

1. No schema change — all four tables exist in migration `0002`. Autogenerate should be a no-op for delivery (verify statically if Postgres unavailable).
2. Deploy is additive — new `/delivery` endpoints, router in `main.py`. Reverting removes them.

## Open Questions

- Should marking a delivery `delivered` prompt/record the cash-on-delivery payment automatically? (Default: no; use the existing payment endpoint.)
- Should auto-assignment by covered zone be added now or later? (Default: later; manual now.)
- Should finishing a run require all its deliveries to be terminal (`delivered`/`not_delivered`)? (Default: no hard requirement; revisit if needed.)
