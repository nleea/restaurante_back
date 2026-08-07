## Why

Delivery opens the third sales channel end to end. The product uses an **own fleet** (no Rappi-style integrations), so it needs real driver management, route configuration, dispatch runs, and explicit per-order delivery states — not just a status field. Orders can already be opened on the `delivery` channel, but there is nowhere to capture the delivery address, assign a driver, or track "on the way / delivered / not delivered". The module exists only as a data layer (`delivery_routes`, `delivery_route_drivers`, `delivery_runs`, `order_deliveries`). With `staff` (drivers are employees) and `orders` implemented, delivery can be built now.

## What Changes

- Add the **application + API layer** for the delivery module, mirroring the reference modules (hexagonal).
- **Routes**: CRUD for a branch's delivery routes (name, covered zones, active flag).
- **Route drivers**: assign/unassign employees as drivers of a route, list a route's drivers (bridge `delivery_route_drivers`).
- **Order delivery record**: create the delivery detail for an order (address, neighborhood, optional lat/long); get it by order; list deliveries (filter by status); update the address. One delivery record per order.
- **Dispatch runs**: create a run for a route + a driver (who MUST be an active driver of that route); list/get runs.
- **Assignment + lifecycle** (`delivery.assign`): assign a delivery to a run (→ `assigned`); depart a run (`preparing → in_transit`, stamping `departed_at`, moving its assigned deliveries to `in_transit`); mark a delivery `delivered` or `not_delivered` (stamping `delivered_at`); finish a run (`in_transit → finished`).
- Explicit states — order delivery: `pending → assigned → in_transit → delivered | not_delivered`; run: `preparing → in_transit → finished` — with forward-only guards.
- Enforce **multi-tenant + multi-branch isolation** and **RBAC** using existing `delivery.read` / `delivery.assign` / `delivery.manage` permissions.
- Register the new router in `main.py`.
- No ORM model changes expected — tables and the `delivery` registration already exist; entities already follow the convention.

### Explicitly out of scope (deferred)
- **Cash-on-delivery payment capture** — recording the collected cash is the existing orders→cash payment flow (`POST /orders/{id}/payments`); delivery only tracks the delivery state. A future change could auto-prompt payment on `delivered`.
- **Auto-assignment by zone / route optimization** — assignment is manual here; `route_position`/geo are stored for a later routing/optimization change.
- **Live driver GPS tracking** — only the static delivery geo and discrete states are modeled.

## Capabilities

### New Capabilities
- `delivery-management`: Own-fleet delivery — routes, route drivers, per-order delivery records with explicit states, and dispatch runs with an assign → depart → deliver → finish lifecycle. Tenant/branch-isolated and RBAC-protected.

### Modified Capabilities
<!-- None — no existing spec's requirements change. -->

## Impact

- **New code** under `src/restaurante/modules/delivery/`: `domain/ports.py`, `application/use_cases/manage_delivery.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`.
- **Modified**: `src/restaurante/main.py` (include `delivery_router`).
- **Depends on** existing tables `employees` (staff), `orders` (orders), `branches` — validated for existence; and the identity RBAC `require_permission` dependency.
- **Reused**: `shared/api/deps.get_tenant_id`, `shared/database.get_session`, tenant auto-filter, `shared/domain/errors` (`NotFoundError`, `ConflictError`, `ValidationError`).
- **APIs**: new `/delivery/*` endpoints (routes, route-drivers, deliveries, runs, lifecycle). No breaking changes.
- **Tests**: new integration suite under `tests/modules/delivery/` (sqlite, FK enforcement) — seeds employees and delivery-channel orders directly.
