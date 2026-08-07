## Context

The backend `/kitchen` module is complete but unconsumed. Its contract:

- **Stations**: `POST /kitchen/stations`, `GET /kitchen/stations`, `PATCH /kitchen/stations/{id}`.
  `KitchenStation = { id, branch_id, name, position, is_active }`. Perms `kitchen.read` (read) /
  `kitchen.update` (write).
- **Product→station**: `POST /kitchen/product-stations`,
  `GET /kitchen/products/{product_id}/stations`, `DELETE /kitchen/products/{pid}/stations/{sid}`.
- **Routing**: `POST /kitchen/orders/{order_id}/route` (kitchen.update) → creates one ticket per
  routable order item, **idempotent**, returns the tickets.
- **Board**: `GET /kitchen/stations/{station_id}/tickets?status_filter=` (kitchen.read);
  `POST /kitchen/tickets/{ticket_id}/advance` (kitchen.update). The advance use case is a strict
  forward machine `pending → in_progress → ready` (`_NEXT_STATUS`), setting `ready_at` on ready
  and raising a conflict from the terminal state.
- `Ticket = { id, branch_id, order_item_id, kitchen_station_id, status, entered_at, ready_at }`.

Two facts drive the design: (1) **nothing auto-creates tickets** — seed creates no stations/maps
and closing an order does not route — so the screen must own setup + routing to be usable; and
(2) **a ticket names only `order_item_id`**, with no product label or order reference, so labels
must be resolved client-side. The frontend stack and conventions follow the existing screens
(Vue 3 `<script setup>`, Pinia, PrimeVue + Tailwind, single Axios instance, active-branch scope,
mobile-first master–detail as in RBAC/Orders).

## Goals / Non-Goals

**Goals:**
- A self-sufficient KDS: configure stations, map products, route open orders, and run the
  cook-facing board (advance pending→in_progress→ready) — all from one screen, branch-scoped.
- Reuse existing menu/orders data and store patterns (write-through, `can()` gating) rather than
  new infrastructure.
- Resolve readable ticket labels with graceful fallback.

**Non-Goals:**
- Realtime/push or auto-refresh (manual refresh this slice).
- Recall/un-advance, per-ticket SLA timers, station load balancing, receipt/printer output.
- Editing the orders screen (routing lives on the KDS per the chosen scope).

## Decisions

**1. One `KitchenView` with three areas, not three screens.** Board, Setup, and Routing live in
one view using the house master–detail/tabbed pattern; the board is the default (cook-facing)
area, Setup and Routing are gated by `kitchen.update`. Alternative (separate config screen) was
rejected to keep the slice cohesive and usable on a fresh tenant.

**2. Ticket labels resolved client-side via an `order_item_id → label` index.** The store builds
the index from open orders' items (`listOrders` + `listItems`) crossed with the menu-derived
variant index (the same `variantIndex` the orders store builds: variant_id → product/variant name
+ price). Each ticket card shows `"<product · variant> ×<qty>"`; when an item isn't in the index
(e.g. order already closed/aged out) it falls back to a short ref like `#<ticket id slice>`.
Alternatives considered: a backend change to fatten `TicketResponse` (out of scope — frontend-only
change) and a per-item GET (no such endpoint). The index is best-effort and explicitly degrades.

**3. Board is station-scoped and fetched per selection.** Tickets are listed per station
(`GET /stations/{id}/tickets`), so the board requires a selected station; selecting one (or
switching) loads its tickets. Columns are derived client-side by grouping on `status` (single
fetch, no per-status calls). Advancing/routing is write-through: refetch the selected station's
tickets afterward. This matches `orders.ts` discipline and avoids guessing server state.

**4. Routing UI reuses the orders API, not a kitchen-specific orders endpoint.** The Routing area
lists open orders via the existing `listOrders({ branchId, status: 'open' })` and calls
`routeOrder(orderId)`. Because backend routing is idempotent, the UI can offer "Enviar a cocina"
without tracking a per-order "routed" flag; re-routing is safe. (A future enhancement could hide
already-routed orders, but there's no backend signal for it today — noted, not built.)

**5. Permission model mirrors existing screens.** Route guard `meta.permission: 'kitchen.read'`;
within the view, `auth.can('kitchen.update')` gates every mutate control (create/edit station,
attach/detach product, route, advance). Read-only users see the board and config without action
affordances.

**6. Store shape** parallels `orders.ts`: `stations`, `selectedStationId`,
`ticketsByStation: Record<string, Ticket[]>`, `stationsByProduct` (for the mapping UI), plus the
derived `ticketLabel(ticket)` and a `columns(stationId)` grouping getter. Actions:
`loadStations(branchId)`, `selectStation(id)` (loads tickets), `createStation`, `updateStation`,
`attachProduct`, `detachProduct`, `routeOrder`, `advanceTicket` — each write-through.

## Risks / Trade-offs

- **Label resolution is best-effort** → tickets for orders not in the loaded open-orders set show
  a fallback ref. Mitigation: load open orders + their items when the board opens; degrade clearly
  rather than show blanks. Acceptable for a single-branch pilot KDS.
- **No realtime** → cooks must refresh to see new tickets. Mitigation: a manual refresh control
  and write-through after local actions; a polling/websocket pass is a deliberate later slice.
- **Stale "open orders to route" list** → the Routing list reflects the last fetch; idempotent
  routing means re-routing is harmless, so the cost of staleness is low.
- **Many fetches on board open** (open orders + items per order + stations + tickets) → bounded by
  the pilot's small order volume; the same `Promise.all` fan-out pattern as `orders.ensureLoaded`.

## Migration Plan

Pure additive frontend change; no backend deploy, no data migration. Ship behind existing
`kitchen.read` / `kitchen.update` permissions. Rollback = revert the new files, the router entry,
and the nav link; no persisted client state.

## Open Questions

- Should already-routed orders be filtered out of the Routing list? No backend signal exists
  today; deferred (idempotent routing makes it non-blocking).
- Auto-refresh cadence for the board (polling vs websocket) — deferred to a follow-up slice.
