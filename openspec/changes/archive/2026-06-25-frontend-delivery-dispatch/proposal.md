## Why

The delivery **route + driver configuration** shipped (`frontend-delivery`), but the operational
half — turning an order into a delivery, building a dispatch run, and running it through
assign→depart→deliver→finish — still has no frontend. This is the part that actually gets food to a
customer: without it the own-fleet operation can't be dispatched from the UI. It completes the
delivery module and gives drivers and dispatchers a board to work from.

## What Changes

- Extend the **Delivery service layer** (`delivery.api.ts`) with the dispatch endpoints over
  `/delivery`: deliveries — create (`POST /deliveries`), list (`GET /deliveries?status_filter=`),
  get by order (`GET /orders/{orderId}/delivery`), update address (`PATCH /deliveries/{id}`); runs —
  create (`POST /runs`), list (`GET /runs?status_filter=`), get (`GET /runs/{id}`); and the
  lifecycle — assign a delivery to a run (`POST /deliveries/{id}/assign`), depart a run
  (`POST /runs/{id}/depart`), mark delivered/not-delivered
  (`POST /deliveries/{id}/mark-delivered` with `{ delivered }`), and finish a run
  (`POST /runs/{id}/finish`).
- Add a **Dispatch store** (`dispatch.ts`): the tenant's deliveries and runs (the list endpoints are
  tenant-wide — no branch filter), with client-side groupings (deliveries by status, a run's
  deliveries via `delivery_run_id`) and label resolution — a run's route name and driver name from
  the delivery + staff data, a delivery's order label from the orders store. The lifecycle mutations
  are write-through.
- Add the **DispatchView** screen with two areas, mobile-first master–detail:
  - **Domicilios** (deliveries): list by status; create a delivery for an open order (pick the order,
    capture the address + neighborhood); per delivery, **assign to a preparing run** (gated by
    `delivery.assign`) and, once in transit, **mark entregado / no entregado**. Creating a delivery
    needs `delivery.manage`.
  - **Despachos** (runs): list by status; create a run (pick a route + one of its drivers), gated by
    `delivery.manage`; per run, see its assigned deliveries, **salir** (depart: preparing→in_transit,
    moving its deliveries to in_transit) and **finalizar** (finish), both gated by `delivery.assign`.
- Add the **route + nav entry** (`/dispatch`, permission `delivery.read`) and a navigation link.
- Unit tests for the new service functions and the store (URLs/payloads/status filters, run-delivery
  grouping, write-through lifecycle refetch, and route/driver/order label resolution).

Non-goals: cash-on-delivery capture (the order is paid through the orders→cash flow);
auto-assignment by zone / route optimization; live GPS tracking; reflecting delivery state back into
the order's status; and editing a run's route/driver after creation — all out of the backend
capability's scope. Branch scoping on the lists is not available server-side (tenant-wide); at the
single-branch pilot this is moot and is flagged for the multi-branch phase.

## Capabilities

### New Capabilities
- `frontend-delivery-dispatch`: the dispatch frontend — create per-order delivery records, build
  dispatch runs from routes + drivers, and drive the assign→depart→deliver/not-delivered→finish
  lifecycle, gated by `delivery.read` / `delivery.manage` / `delivery.assign`, with route, driver,
  and order labels resolved from the delivery, staff, and orders data.

### Modified Capabilities
<!-- None. Consumes the existing delivery-management backend unchanged; route/driver, employee and
     order data are read-only from frontend-delivery, staff-management and order-management. -->

## Impact

- **Frontend code**: extend `front/src/services/delivery.api.ts`; new `front/src/stores/dispatch.ts`,
  `front/src/views/DispatchView.vue`, and `front/src/components/dispatch/*`; a route in
  `front/src/router/index.ts` and a nav link in `front/src/components/AppSidebar.vue`. New tests
  under `front/src/services/__tests__` and `front/src/stores/__tests__`.
- **Reuses**: the delivery store (routes + a route's drivers, for run creation), the staff store
  (driver names), the orders store (open orders for delivery creation + order labels), the active-
  branch context (order/route pickers), the shared `http` axios instance, and the `apiError` helpers.
- **Backend**: none — consumes existing `/delivery` deliveries/runs/lifecycle endpoints.
- **Permissions/RBAC**: relies on `delivery.read` (board), `delivery.manage` (create delivery/run),
  and `delivery.assign` (assign/depart/mark/finish). No new permission codes.
- **Dependencies**: no new packages; PrimeVue + Tailwind + Axios as elsewhere.
