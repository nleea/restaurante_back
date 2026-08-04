## 1. Service layer

- [x] 1.1 Extend `front/src/services/delivery.api.ts` with types `Delivery` (`id, order_id, delivery_route_id?, delivery_run_id?, address_text, neighborhood?, latitude?, longitude?, delivery_status, route_position?, delivered_at?`) and `Run` (`id, delivery_route_id, employee_id, status, departed_at?, finished_at?`)
- [x] 1.2 Add delivery calls: `createDelivery(input)`, `listDeliveries(status?)`, `getOrderDelivery(orderId)`, `updateDelivery(id, patch)`
- [x] 1.3 Add run calls: `createRun(input)`, `listRuns(status?)`, `getRun(id)`
- [x] 1.4 Add lifecycle calls: `assignDelivery(deliveryId, { delivery_run_id })`, `departRun(runId)`, `markDelivered(deliveryId, delivered)` (`POST .../mark-delivered` with `{ delivered }`), `finishRun(runId)`
- [x] 1.5 Add service unit tests in `front/src/services/__tests__/delivery.dispatch.api.spec.ts` (URLs, payloads, status filters, mark-delivered body, returned shapes)

## 2. Store layer

- [x] 2.1 Create `front/src/stores/dispatch.ts` (Pinia options) state: `deliveries`, `runs`, `selectedDeliveryId`, `selectedRunId`
- [x] 2.2 Add `loadDeliveries(status?)` / `loadRuns(status?)`; getters `deliveriesByStatus`, `runsByStatus`, `deliveriesOfRun(runId)`, `pendingDeliveries`, `preparingRuns`
- [x] 2.3 Add `createDelivery` / `createRun` write-through (refetch the affected list)
- [x] 2.4 Add lifecycle actions `assignDelivery` (refetch deliveries), `departRun` (refetch runs + deliveries — cascade), `markDelivered` (refetch deliveries), `finishRun` (refetch runs)
- [x] 2.5 Add store unit tests: load + status grouping, run-delivery grouping, assign/depart/mark/finish write-through refetch (incl. the depart cascade refetching both lists)

## 3. Screen, components, routing

- [x] 3.1 Add `/dispatch` route (name `dispatch`, `meta.permission: 'delivery.read'`) in `front/src/router/index.ts` and a nav link (`Despacho`) in `front/src/components/AppSidebar.vue`
- [x] 3.2 Create `front/src/views/DispatchView.vue` container + `DispatchPanel.vue` orchestrator: load deliveries/runs + ensure delivery routes / staff / open orders loaded, area switch (Domicilios / Despachos), refresh, error
- [x] 3.3 Create the Domicilios area: deliveries list by status (master) + delivery detail (address, neighborhood, status, order label) with assign-to-run (gated `delivery.assign`, only when `pending`) and mark entregado/no-entregado (only when `in_transit`)
- [x] 3.4 Create the new-delivery dialog (gated `delivery.manage`): open-order picker (reuse orders store), address, optional neighborhood; friendly 409 "ese pedido ya tiene un domicilio"
- [x] 3.5 Create the Despachos area: runs list by status (master) + run detail (route name, driver name, status, its deliveries) with salir (depart, only `preparing`) and finalizar (finish, only `in_transit`), gated `delivery.assign`
- [x] 3.6 Create the new-run dialog (gated `delivery.manage`): route picker (active-branch routes from the delivery store) → driver picker (that route's drivers); friendly errors
- [x] 3.7 Resolve route/driver/order labels from the delivery, staff and orders stores; surface API errors (incl. out-of-order 409s) with friendly messages (reuse `apiError`)

## 4. Verification

- [x] 4.1 `pnpm type-check` and `pnpm lint` clean (and `pnpm build` succeeds)
- [x] 4.2 `pnpm test:unit` green (new service + store tests included)
- [ ] 4.3 Manual smoke against the running backend: create a delivery for an open order → create a run (route + driver) → assign the delivery → depart the run (delivery goes in_transit) → mark delivered → finish the run; verify out-of-order actions show friendly conflicts and a read-only/manage-only user sees the right gated controls
