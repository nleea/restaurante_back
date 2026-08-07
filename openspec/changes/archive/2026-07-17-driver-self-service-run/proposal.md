## Why

The driver ("domiciliario") view at `/driver` is built but 100% mock-backed: it opens fake runs, lists fake stops, and marks deliveries only in memory. Drivers cannot actually see or work their real deliveries. The backend has the delivery/run model but exposes no driver-scoped, self-service path — a driver has no way to see *their* run, and every lifecycle action (depart, finish, mark delivered) requires the dispatcher permission `delivery.assign`. Not every business runs a dispatcher, so a driver must be able to open and work a despacho on their own.

## What Changes

- Introduce a driver self-service permission **`delivery.drive`** and a driver role bundle, so a courier can act on **their own** run without dispatcher permissions (`delivery.assign`/`delivery.manage`).
- **Dual-path run opening**: a driver can self-open a despacho (create a run owned by themselves and pull eligible pending deliveries of their branch/route into it); the dispatcher's existing create+assign path is unchanged. Neither depends on the other.
- New **driver-scoped read**: an identity-resolved endpoint (e.g. `GET /delivery/me/run`) returns the driver's active run with **enriched stops** — each delivery joined to its order summary (code, customer, phone, items, total, payment method/status) — so the driver app never needs branch-wide `orders.read`.
- A driver can **depart** and **finish** their own run, and **mark stops delivered / not-delivered**, all gated by `delivery.drive` with an ownership check (`run.employee_id == me`).
- **Not-delivered reason**: `mark-delivered` accepts an optional reason/comment and persists it (today it takes only a boolean). Fixed reason list: cliente no contesta, dirección incorrecta / no la encuentra, cliente rechazó, cliente canceló, otro (texto libre).
- **Frontend**: wire `DriverView` / `useDriverStore` to the real endpoints and retire the mock data layer — except geolocation, which is out of scope here. The "siguiente pedido" is derived from `route_position` + terminal status (since `depart` flips all run deliveries to `in_transit` at once).

## Capabilities

### New Capabilities
- `driver-run`: the driver's self-service run lifecycle — resolve own identity, open/read/depart/finish **their own** run, and mark their own deliveries, all scoped by `delivery.drive` and run ownership, with order-enriched stop reads.
- `frontend-driver`: the driver mobile view wired to real data — real run open/read, real delivered/not-delivered with reason, real destination pins; mocks removed.

### Modified Capabilities
- `delivery-management`: `mark-delivered` records an optional not-delivered reason; run creation permits a driver to self-create a run for themselves (in addition to dispatcher-created runs); add the `delivery.drive` permission code, gate driver self-service endpoints with it, and include it in a driver-facing base role.

## Impact

- **Backend** (`modules/delivery`): new driver-scoped router/use-cases (open own run + pull deliveries, `GET /delivery/me/run` enriched read, own-run depart/finish/mark), ownership guard, order-summary join (read across `modules/orders`); `mark-delivered` schema + persistence gains a reason (likely a new `not_delivered_reason` column via migration, or reuse of `notes` — decided in design). `modules/identity` permissions catalog + role bundle gains `delivery.drive`. `GET /staff/employees/me` reused for identity.
- **Frontend** (`front/src`): `stores/driver.ts` + `views/DriverView.vue` + `components/driver/*` call `services/delivery.api.ts` (new driver functions) and a current-user→employee resolution; `lib/driver/mockDriver.ts` removed (geolocation constant stays until Change 2). `StatusPill`/rail reconcile the real `assigned`→`in_transit` transition.
- **Out of scope** (Change 2 `driver-live-location`): browser geolocation, storing the driver's position trail, and the driver marker on the dispatcher's map.
- Multi-tenant/branch scoping preserved (branch derived from the employee, never client-supplied). English identifiers; Spanish only in UI copy.
