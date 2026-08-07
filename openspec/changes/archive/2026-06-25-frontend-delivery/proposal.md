## Why

The backend `/delivery` module runs an own-fleet delivery operation — routes, route drivers,
per-order delivery records, dispatch runs, and the assign→depart→deliver→finish lifecycle — but has
no frontend. The foundation everything else depends on is **route + driver configuration**: you
can't build a dispatch run or assign a delivery without routes and the drivers assigned to them.
This change builds that configuration first, so the operational dispatch board (deliveries, runs,
lifecycle) can land as a follow-up against real routes and drivers.

## What Changes

- Add a **Delivery service layer** (`delivery.api.ts`) over the route slice of `/delivery`: list
  routes for a branch (`GET /delivery/routes?branch_id=`), create (`POST /delivery/routes`),
  update/deactivate (`PATCH /delivery/routes/{id}` — the same endpoint edits name/zones and flips
  `is_active`), list a route's drivers (`GET /delivery/routes/{id}/drivers`), assign a driver
  (`POST /delivery/routes/{id}/drivers`), and remove one
  (`DELETE /delivery/routes/{id}/drivers/{employeeId}`).
- Add a **Delivery store** (`delivery.ts`): the active branch's routes and the selected route's
  drivers, with the driver employees resolved to names from the staff directory.
- Add the **DeliveryView** screen, mobile-first master–detail (the house pattern):
  - **Route list** (master): name, covered zones, active badge, with an "solo activas" filter. Read
    needs `delivery.read`.
  - **Route detail**: name and covered zones with an edit form and a deactivate/reactivate action,
    plus the route's **drivers** — each row showing the employee name, with **assign** (pick an
    employee) and **remove** controls. All mutations gated by `delivery.manage`.
- Add the **route + nav entry** (`/delivery`, permission `delivery.read`) and a navigation link.
- Unit tests for the service and store (URLs/payloads, the branch filter, write-through refetch,
  driver-name resolution, and the duplicate-assign conflict).

Non-goals (deferred to a follow-up `frontend-delivery-dispatch` change): per-order delivery records,
dispatch runs, and the assign→depart→deliver/not-delivered→finish lifecycle (which uses the separate
`delivery.assign` permission). Also out of scope: cash-on-delivery capture (handled by the
orders→cash flow), auto-assignment/route optimization, live GPS, and reflecting delivery state back
into the order — all explicitly out of the backend capability's scope.

## Capabilities

### New Capabilities
- `frontend-delivery`: the delivery route-configuration frontend — create/edit/deactivate
  branch-scoped delivery routes (name, covered zones) and manage each route's drivers
  (assign/remove employees), with driver names resolved from staff and all mutations gated by
  `delivery.read` / `delivery.manage`.

### Modified Capabilities
<!-- None. Consumes the existing delivery-management backend unchanged (route + driver slice only);
     employee data is read-only from staff-management. -->

## Impact

- **Frontend code**: new `front/src/services/delivery.api.ts`, `front/src/stores/delivery.ts`,
  `front/src/views/DeliveryView.vue`, and `front/src/components/delivery/*`; a route in
  `front/src/router/index.ts` and a nav link in `front/src/components/AppSidebar.vue`. New tests
  under `front/src/services/__tests__` and `front/src/stores/__tests__`.
- **Reuses**: the staff store (employee names + the assign picker), the active-branch context
  (routes are branch-scoped), the shared `http` axios instance, and the `apiError` helpers.
- **Backend**: none — consumes existing `/delivery` route + driver endpoints.
- **Permissions/RBAC**: relies on `delivery.read` (screen + read) and `delivery.manage` (route
  create/edit/deactivate, driver assign/remove); `delivery.assign` is for the deferred dispatch
  slice. No new permission codes.
- **Dependencies**: no new packages; PrimeVue + Tailwind + Axios as elsewhere.
