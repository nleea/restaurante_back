## 1. Permission & roles (backend)

- [x] 1.1 Add `delivery.drive` to the permission catalog (`modules/identity` permissions catalog) in the `delivery` module
- [x] 1.2 Grant `delivery.drive` to the `courier` base role in the RBAC seed; keep provisioning additive and idempotent (no schema migration for the catalog)
- [x] 1.3 Add/adjust tests: seed inserts `delivery.drive`, `courier` holds it and still does NOT hold `delivery.address`; re-seeding is a no-op

## 2. Not-delivered reason (backend data + lifecycle)

- [x] 2.1 Add an additive nullable `order_deliveries.not_delivered_reason` column (Alembic migration, no backfill); update the `OrderDelivery` model/entity
- [x] 2.2 Extend the mark-delivered use case + request schema to accept optional `reason` (fixed list) and `comment`, persisting them only when `delivered == false`
- [x] 2.3 Tests: marking not-delivered with/without a reason persists correctly; marking delivered ignores/clears reason

## 3. Driver identity & ownership (backend)

- [x] 3.1 Add a helper to resolve the current auth user → active `Employee` for delivery driver actions (reuse `get_employee_for_user`); 404/403 when no active employee link
- [x] 3.2 Add an ownership guard usable by all driver endpoints: `run.employee_id == current_employee.id` (and delivery→run ownership for mark-delivered)

## 4. Driver self-service run (backend use cases + API)

- [x] 4.1 Use case: driver self-opens a despacho — resolve the driver's active route(s); if exactly one, use it; if several, require a chosen `delivery_route_id`; if none, reject. Create a `preparing` run with `employee_id = self`
- [x] 4.2 Same use case: pull eligible pending deliveries (same branch, `pending`, unassigned; **zone-agnostic** — not filtered by route) onto the run as `assigned`, reusing the existing assign transition/guards
- [x] 4.3 Idempotency: if the driver already has an active (`preparing`/`in_transit`) run, return it instead of creating a second
- [x] 4.3a Unassign own pulled delivery while `preparing`: return it to `pending` with no run/route; reject once departed
- [x] 4.4 Read model: `GET /delivery/me/run` returns the caller's active run + deliveries ordered by `route_position`, each enriched with an order summary (code, customer, phone, item lines, total, payment method/state) via a batched read across `modules/orders`; empty when no active run
- [x] 4.5 Own-run lifecycle endpoints under `delivery.drive` + ownership: open, depart, finish, mark-delivered/not-delivered (may wrap the existing lifecycle use cases behind the ownership check)
- [x] 4.6 Wire the router with `delivery.drive` on all driver endpoints; keep dispatcher endpoints on `delivery.assign`/`delivery.manage` unchanged
- [x] 4.7 Tests: self-open pulls only eligible deliveries; no-route rejects; second-open is idempotent; `me/run` returns enriched, position-ordered, caller-only data; a driver cannot depart/finish/mark another driver's run (403/404); driver without `delivery.drive` is 403

## 5. Frontend API + store

- [x] 5.1 Add driver functions to `services/delivery.api.ts`: `openMyRun(routeId?)`, `getMyRun()`, `departMyRun()`, `finishMyRun()`, `markMyDelivered(deliveryId, delivered, reason?, comment?)`; add the enriched run/stop TypeScript types
- [x] 5.2 Resolve current-user → employee for driver identity (via `/staff/employees/me`); expose the driver's display name
- [x] 5.3 Rewrite `stores/driver.ts` to write-through against the API (call + refetch `me/run`); map real statuses (`assigned`/`in_transit`) and derive `nextStop` from `route_position` + terminal status
- [x] 5.4 Delete `lib/driver/mockDriver.ts` (retain only the geolocation "Tú" constant to move into Change 2)

## 6. Frontend view wiring

- [x] 6.1 `EmptyRun` → real "Abrir despacho" (calls `openMyRun`), surfacing the no-route error; `ActiveRun`/`NextStopCard`/`StopRail` bind to the real enriched run
- [x] 6.2 `StatusPill` reconciled for real states; `StopDetailSheet` shows enriched order data (customer/phone/items/total/payment) with one-tap call
- [x] 6.3 `FailReasonSheet` → real not-delivered with reason + comment; delivered/not-delivered call the API and advance to the next stop
- [x] 6.4 `RunMap` plots stops from real destination coordinates; surface unlocated stops (driver's own position stays out of scope)
- [x] 6.5 Guard `/driver` route on `delivery.drive`; ensure the driver view does not require `orders.read`

## 7. Verify end-to-end

- [x] 7.1 Backend quality gate: ruff, mypy, and the delivery/staff test suites pass
- [x] 7.2 Frontend quality gate: type-check, lint, build pass
- [x] 7.3 Drive the full real flow (seed a courier + pending deliveries): login as courier → abrir despacho → salir → entregar / no-entregar con motivo → finalizar; confirm the dispatcher still creates and works runs unchanged
- [x] 7.4 Update `front/CLAUDE.md` / delivery docs with the driver self-service endpoints and the `delivery.drive` permission
