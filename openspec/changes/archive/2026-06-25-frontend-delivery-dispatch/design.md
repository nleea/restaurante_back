## Context

`frontend-delivery` shipped route + driver configuration; this change builds the operational
dispatch half. The contract (deliveries/runs are tenant-scoped — the list endpoints take only
`status_filter`, no `branch_id`):

- **Deliveries**: `POST /delivery/deliveries` (`{ order_id, address_text, neighborhood?, latitude?,
  longitude? }`), `GET /delivery/deliveries?status_filter=`, `GET /delivery/orders/{orderId}/delivery`,
  `PATCH /delivery/deliveries/{id}` (address fields). `Delivery = { id, order_id, delivery_route_id?,
  delivery_run_id?, address_text, neighborhood?, latitude?, longitude?, delivery_status, route_position?,
  delivered_at? }`. Status: `pending | assigned | in_transit | delivered | not_delivered`.
- **Runs**: `POST /delivery/runs` (`{ delivery_route_id, employee_id }`),
  `GET /delivery/runs?status_filter=`, `GET /delivery/runs/{id}`. `Run = { id, delivery_route_id,
  employee_id, status, departed_at?, finished_at? }`. Status: `preparing | in_transit | finished`.
- **Lifecycle** (`delivery.assign`): `POST /deliveries/{id}/assign` (`{ delivery_run_id }`),
  `POST /runs/{id}/depart`, `POST /deliveries/{id}/mark-delivered` (`{ delivered: bool }` — true →
  `delivered`, false → `not_delivered`), `POST /runs/{id}/finish`.
- Reads `delivery.read`; create delivery/run `delivery.manage`; transitions `delivery.assign`.

Three facts drive the design: (1) the lists are **tenant-wide** (no branch param), so the board shows
all the tenant's deliveries/runs filtered by status — fine at the single-branch pilot, flagged for
multi-branch; (2) records are **id-only** — a delivery names an `order_id` (no embedded order data)
and an address, a run names a `delivery_route_id` + `employee_id` — so labels are resolved from the
delivery routes (already in the delivery store), staff (driver names), and the orders store (open
orders for creation + a best-effort order label); the **address is the delivery's primary label**;
and (3) it is a **two-entity state machine** (delivery: pending→assigned→in_transit→delivered/
not_delivered; run: preparing→in_transit→finished, departing a run cascades its deliveries), so each
action is offered only in the allowing state and write-through refetches both collections to reflect
cascades. Conventions follow the existing screens (Vue 3 `<script setup>`, Pinia options stores,
PrimeVue + Tailwind, the shared `@/lib/http` axios instance, mobile-first master–detail/tabbed as in
Procurement).

## Goals / Non-Goals

**Goals:**
- A working dispatch board: turn open orders into deliveries, build runs from routes + drivers, and
  drive assign→depart→deliver→finish — state-aware and permission-gated.
- Reuse the delivery routes/drivers, staff, and orders data for labels and pickers rather than new
  infrastructure.
- Mirror the established store discipline (write-through, `can()` gating) and the tabbed two-area UX.

**Non-Goals:**
- Cash-on-delivery (orders→cash), auto-assignment/optimization, live GPS, order-status reflection,
  and editing a run's route/driver after creation — all out of the backend capability's scope.

## Decisions

**1. One `DispatchView` with two areas (Domicilios / Despachos), each master–detail.** The two
entities share a screen via the house tabbed pattern; deliveries is the default. A run's detail lists
its deliveries and carries the depart/finish controls; a delivery's detail carries assign and
mark-delivered. Rejected: separate screens — the assign step bridges the two and reads better in one
place.

**2. Tenant-wide lists, status-filtered.** Because the endpoints take only `status_filter`, the store
loads by status (or all) with no branch filter. Create-delivery still sources its order from the
active branch's open orders, and create-run from the active branch's routes, so new records are
branch-relevant even though the list is tenant-wide. The branch-filter gap is documented, not hidden.

**3. Address-centric delivery labels; best-effort order link.** A delivery renders `address_text`
(+ `neighborhood`) as its primary identity — that is what a driver needs. The order link is a
best-effort label from the orders store (channel/table) with a short `#order` fallback; resolving it
is optional and never blocks the board.

**4. Run creation reuses routes + their drivers; the driver must be a route driver.** The create-run
form picks a route (from the delivery store's active-branch routes) and then one of that route's
drivers (the delivery store's `selectRoute` loads them). This matches the backend rule that a run's
driver must be an active driver of the route, so the picker can't produce an invalid run.

**5. State-gated actions with cascade-aware refetch.** Assign shows only for `pending` deliveries and
targets only `preparing` runs; depart only for `preparing` runs; mark-delivered only for `in_transit`
deliveries; finish only for `in_transit` runs. Because departing a run cascades its deliveries to
`in_transit`, depart's write-through refetches **both** runs and deliveries. Out-of-order attempts
surface the backend's 409 as a friendly message.

**6. A dedicated `dispatch` store, separate from the `delivery` (config) store.** Config (routes/
drivers) is master data; deliveries/runs are operational transactions with their own lifecycle, so
they get their own store. The dispatch store *reads* the delivery store (route names + a route's
drivers), the staff store (driver names), and the orders store (open orders + order labels) — it does
not duplicate them, and ensures they're loaded on open. State: `deliveries`, `runs`,
`selectedDeliveryId`, `selectedRunId`. Getters: `deliveriesByStatus`, `runsByStatus`,
`deliveriesOfRun(runId)`, `pendingDeliveries`, `preparingRuns`. Actions (write-through):
`loadDeliveries(status?)`, `loadRuns(status?)`, `createDelivery`, `createRun`, `assignDelivery`,
`departRun` (refetch runs + deliveries), `markDelivered`, `finishRun`.

**7. Permission model mirrors the backend's three levels.** Route guard `delivery.read`; create
controls gated by `delivery.manage`; lifecycle controls by `delivery.assign`. Read-only users see the
board without actions.

## Risks / Trade-offs

- **No branch filter on lists** → a multi-branch tenant sees all branches' deliveries/runs. →
  Mitigation: single-branch pilot; create flows are branch-scoped; flagged for a backend `branch_id`
  filter later.
- **Label resolution is best-effort** → an order not in the loaded open-orders set, or a driver/route
  not loaded, shows a short ref. → Mitigation: load routes/staff/open-orders when the board opens;
  degrade clearly. The address always identifies a delivery regardless.
- **Two-entity cascade** (depart moves run + deliveries) → a naive refetch of only runs would leave
  deliveries stale. → Mitigation: depart refetches both collections.
- **Order picker coupling to orders store** → reuses `listOrders(branchId, 'open')`; if an order
  already has a delivery the create 409s → surfaced as a friendly message and the order can be
  skipped.

## Migration Plan

Pure additive frontend change; no backend deploy, no data migration. Ship behind existing
`delivery.read` / `delivery.manage` / `delivery.assign` permissions. Rollback = revert the service
additions, the new store/view/components, the router entry, and the nav link; no persisted client
state.

## Open Questions

- Should deliveries/runs gain a backend `branch_id` filter for multi-branch dispatch? Deferred —
  client shows all at pilot scale; flagged for the multi-branch phase.
- Should departing offer to bulk-assign a run's remaining pending deliveries first? Out of scope —
  assign is per-delivery this slice; a batch-assign affordance is a possible later nicety.
