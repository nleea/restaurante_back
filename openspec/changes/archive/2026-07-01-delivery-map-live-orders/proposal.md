# Proposal: delivery-map-live-orders

## Why

Every per-order delivery already carries coordinates (`order_deliveries.latitude/longitude`),
but that data is invisible — no screen plots it. Painting the open deliveries over the coverage
rings turns `/delivery` from a configuration screen into a live operations board: where tonight's
demand is, which order fell outside coverage, and which route each one belongs to — at a glance.
Especially apt for Riohacha's compact scale, where the whole city fits in one view.

## What Changes

- The coverage map at `/delivery` plots the branch-tenant's **open deliveries**
  (`pending` / `assigned` / `in_transit`) that carry coordinates, as dots colored by status
  (pending = steel, assigned = info blue, in transit = ember), each with a tooltip (address ·
  status).
- A "Pedidos (N)" toggle pill on the map shows/hides the overlay (on by default) and carries the
  live count; open deliveries **without** coordinates are surfaced as a small "N sin ubicación"
  note so they aren't silently missing.
- Data comes from the existing `GET /delivery/deliveries` via the existing dispatch store —
  loaded with the screen and refreshed by the same "Actualizar" action. **No backend changes.**

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `frontend-delivery`: the coverage map gains a live open-deliveries overlay (dots by status,
  toggle with count, no-coordinates note).

## Impact

- **Frontend only**: `lib/deliveryRoutes.ts` (pure mapper: deliveries → plottable points +
  unlocated count, unit-tested), `components/deliveryroutes/useLeafletRings.ts`
  (`setDeliveryPoints`), `views/DeliveryRoutesView.vue` (load via `useDispatchStore`, toggle
  pill), no API/store schema changes (reuses `stores/dispatch.ts` read-only).
- Note: the deliveries list endpoint is tenant-wide (not branch-scoped) — acceptable at current
  single-branch scale; flagged for the future multi-branch pass.
