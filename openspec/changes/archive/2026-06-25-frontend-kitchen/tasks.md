## 1. Service layer

- [x] 1.1 Create `front/src/services/kitchen.api.ts` with types `KitchenStation`, `ProductStation`, `Ticket` (matching backend schemas)
- [x] 1.2 Add station calls: `listStations(branchId)`, `createStation(input)`, `updateStation(id, patch)`
- [x] 1.3 Add product-station calls: `listProductStations(productId)`, `attachProductStation(input)`, `detachProductStation(productId, stationId)`
- [x] 1.4 Add board calls: `routeOrder(orderId)`, `listTickets(stationId, status?)` (maps to `status_filter`), `advanceTicket(ticketId)`
- [x] 1.5 Add service unit tests in `front/src/services/__tests__/kitchen.api.spec.ts` (URLs, payloads, status_filter param, returned shapes)

## 2. Store layer

- [x] 2.1 Create `front/src/stores/kitchen.ts` state: `stations`, `selectedStationId`, `ticketsByStation`, `stationsByProduct`
- [x] 2.2 Add `loadStations(branchId)` and `selectStation(id)` (loads that station's tickets)
- [x] 2.3 Add station setup actions `createStation` / `updateStation` (write-through: refetch stations)
- [x] 2.4 Add mapping actions `loadProductStations(productId)` / `attachProduct` / `detachProduct` (write-through)
- [x] 2.5 Add `routeOrder(orderId)` and `advanceTicket(ticketId)` (write-through: refetch the selected station's tickets)
- [x] 2.6 Build the `order_item_id → label` index from open orders' items + menu variant index; add `ticketLabel(ticket)` getter with graceful fallback
- [x] 2.7 Add `columns(stationId)` getter grouping a station's tickets into pending / in_progress / ready
- [x] 2.8 Add store unit tests: stations load, select loads tickets, advance/route write-through refetch, label resolution + fallback, column grouping

## 3. Screen, components, routing

- [x] 3.1 Add `/kitchen` route (name `kitchen`, `meta.permission: 'kitchen.read'`) in `front/src/router/index.ts` and a nav link
- [x] 3.2 Create `front/src/views/KitchenView.vue` container: active-branch guard, station selector, area switch (Board / Setup / Routing)
- [x] 3.3 Create the Board component: status columns for the selected station, ticket cards (label + qty), advance action gated by `kitchen.update`, no advance on `ready`
- [x] 3.4 Create the Setup component (gated by `kitchen.update`): station CRUD (name, position, active) and product→station attach/detach
- [x] 3.5 Create the Routing component (gated by `kitchen.update`): list open orders + "Enviar a cocina" action calling `routeOrder`
- [x] 3.6 Add a manual refresh affordance for the board and surface API errors with friendly messages (reuse `apiError` helpers)

## 4. Verification

- [x] 4.1 `pnpm type-check` and `pnpm lint` clean
- [x] 4.2 `pnpm test:unit` green (new service + store tests included)
- [ ] 4.3 Manual smoke against the running backend: create station → map product → open+route an order → ticket appears → advance pending→in_progress→ready; verify read-only user sees no mutate controls
