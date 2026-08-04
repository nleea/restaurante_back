# Design: delivery-map-live-orders

## Context

`/delivery` (change `wire-delivery-routes-map`) shows active-route rings around the business
pin. `order_deliveries` rows carry optional `latitude/longitude` and a status
(`pending/assigned/in_transit/delivered/not_delivered`); `stores/dispatch.ts` already loads them
tenant-wide via `listDeliveries()`. Nothing plots them.

## Goals / Non-Goals

**Goals:** open deliveries as status-colored dots over the rings; toggle with live count;
unlocated open deliveries surfaced as a count; zero backend changes.

**Non-Goals:** no assignment/lifecycle actions from the map (that stays in `/dispatch`); no
polling/realtime (manual "Actualizar" + on-load is enough for an overview); no branch scoping
fix of the tenant-wide list (future multi-branch pass); no clustering (Riohacha-scale volumes).

## Decisions

- **D1 — Pure mapper in `lib/deliveryRoutes.ts`**: `openDeliveryPoints(deliveries)` returns
  `{ points: DeliveryPoint[], unlocated: number }` — filters status ∈ {pending, assigned,
  in_transit}, requires parseable lat/long, builds `{ id, coords, status, label }` (label =
  `address_text` + optional neighborhood). Unit-testable; the view stays thin.
- **D2 — Overlay in the existing controller**: `RingsController.setDeliveryPoints(points)`
  draws one small `circleMarker` per point (radius 5, white stroke for contrast on any ring
  fill), colored by status — pending `#6b7682` (steel), assigned `#3b7fd9` (info), in_transit
  `#f2933b` (ember) — with a sticky tooltip `label — estado`. Keyed by id: update in place,
  remove stale. Independent of the ring center (deliveries have absolute coords).
- **D3 — Reuse the dispatch store read-only**: the view calls
  `useDispatchStore().loadDeliveries()` inside its `load()`; the computed overlay derives from
  `dispatch.deliveries`. No new store state.
- **D4 — Toggle pill docked top-right** of the map: "Pedidos (N)" (N = plotted count), ember
  when on, on by default; beneath it a quiet `N sin ubicación` line when applicable.

## Risks / Trade-offs

- [Tenant-wide list may include other branches' deliveries] → single-branch reality today;
  noted in the proposal for the multi-branch pass.
- [Stale dots between refreshes] → acceptable for an overview; "Actualizar" is one tap, and the
  screen reloads on branch change/mount.
- [Dot colors vs ring colors could collide] → dots are small, white-stroked and status-colored
  (never route-colored), so they read as a separate layer.

## Migration Plan

Frontend-only, single commit; revert restores the previous map.

## Open Questions

None.
