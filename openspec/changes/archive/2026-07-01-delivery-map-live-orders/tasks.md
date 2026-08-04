# Tasks: delivery-map-live-orders

## 1. Implementation

- [x] 1.1 `lib/deliveryRoutes.ts`: `openDeliveryPoints(deliveries)` pure mapper (status filter,
      coord parsing, label, unlocated count) + unit tests
- [x] 1.2 `useLeafletRings.ts`: `setDeliveryPoints(points)` — status-colored circleMarkers with
      tooltips, keyed update/removal, independent of the ring center
- [x] 1.3 `DeliveryRoutesView.vue`: load deliveries via `useDispatchStore` in `load()`, computed
      overlay, "Pedidos (N)" toggle pill (top-right, on by default) + "N sin ubicación" note,
      sync dots on data/toggle changes

## 2. Validation

- [x] 2.1 Frontend gates green (`pnpm type-check`, `test:unit`, `lint`, `build`)
- [x] 2.2 E2E on dev: create a delivery with coordinates near the pin via API → dot appears with
      tooltip; mark it delivered → refresh removes it; one without coordinates → counted as
      "sin ubicación"
