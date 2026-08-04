## 1. Service layer

- [x] 1.1 Create `front/src/services/delivery.api.ts` with types `Route` (`id, branch_id, name, covered_zones, is_active`) and `RouteDriver` (`id, delivery_route_id, employee_id, is_active`)
- [x] 1.2 Add route calls: `listRoutes(branchId)` (`GET /delivery/routes`, branch_id param), `createRoute(input)` (`POST /delivery/routes`), `updateRoute(id, patch)` (`PATCH /delivery/routes/{id}`)
- [x] 1.3 Add driver calls: `listDrivers(routeId)`, `assignDriver(routeId, { employee_id })`, `removeDriver(routeId, employeeId)`
- [x] 1.4 Add service unit tests in `front/src/services/__tests__/delivery.api.spec.ts` (URLs, payloads, branch_id param, driver paths, returned shapes)

## 2. Store layer

- [x] 2.1 Create `front/src/stores/delivery.ts` (Pinia options) state: `routes`, `selectedRouteId`, `drivers`
- [x] 2.2 Add `loadRoutes(branchId)` and `selectRoute(id)` (loads that route's drivers); add `selectedRoute` and `activeRoutes` getters
- [x] 2.3 Add route mutations `createRoute` / `updateRoute` / `deactivateRoute` (the last calls `updateRoute(id, { is_active: false })`) — write-through refetch routes
- [x] 2.4 Add driver mutations `assignDriver` / `removeDriver` — write-through refetch the selected route's drivers
- [x] 2.5 Add store unit tests: routes load + active filter, route create/deactivate write-through, driver assign/remove write-through, select loads drivers

## 3. Screen, components, routing

- [x] 3.1 Add `/delivery` route (name `delivery`, `meta.permission: 'delivery.read'`) in `front/src/router/index.ts` and a nav link (`Domicilios`) in `front/src/components/AppSidebar.vue`
- [x] 3.2 Create `front/src/views/DeliveryView.vue` container + `DeliveryPanel.vue` orchestrator: active-branch guard, load (routes + staff), master list (name + zones, active filter, drill-down), refresh, error
- [x] 3.3 Create the new-route dialog (gated by `delivery.manage`): name + optional covered zones (textarea)
- [x] 3.4 Create `RouteDetail.vue`: name + covered zones edit form and a deactivate/reactivate action (via `updateRoute`), gated by `delivery.manage`
- [x] 3.5 Create the drivers section in the detail: list drivers by employee name; assign control (employee picker reusing staff, excluding already-assigned) with friendly 409 "ese conductor ya está asignado"; and a remove control
- [x] 3.6 Resolve driver employee names from staff; surface API errors with friendly messages (reuse `apiError` helpers)

## 4. Verification

- [x] 4.1 `pnpm type-check` and `pnpm lint` clean (and `pnpm build` succeeds)
- [x] 4.2 `pnpm test:unit` green (new service + store tests included)
- [ ] 4.3 Manual smoke against the running backend: create a route → edit name/zones → assign a driver (duplicate shows friendly conflict) → remove a driver → deactivate the route; verify a read-only user sees no manage controls
