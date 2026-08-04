## Why

Today a product that needs more than one station (a hamburguesa → Parrilla for the patty, Fríos
for the vegetables) is routed to both, but **each station only sees the bare product name** — no one
is told *which part* they own — and **nobody is told when the whole dish is done**: each ticket goes
`ready` independently and the signal dies there. The waiter watching a table (and dispatch watching a
delivery) has no idea the food is up. Meanwhile the ticket already stores `entered_at` / `ready_at`,
so prep and wait times are computable but never shown. This closes the three gaps together: say what
each station does (A), roll station-readiness up to the order and fan it out by channel (B), and
surface the timers that already exist in the data.

## What Changes

- **Station roles (A):** the product↔station mapping gains an optional `role` ("Carne y armado",
  "Vegetales"). Routing copies the role onto each ticket, so every KDS chit shows what that station
  is responsible for. Empty role = today's behavior.
- **Ready rollup (B):** an order's kitchen state is **derived** — `in_kitchen` while any non-cancelled
  ticket is unfinished, `ready` when all are `ready`, `none` before routing. Advancing the last open
  ticket of an order emits a kitchen→orders signal that sets `Order.kitchen_state`, mirroring the
  existing orders→kitchen auto-route port. Adding an item later recomputes it (drops back to
  `in_kitchen`) — no manual flag to forget.
- **Channel fan-out:** the same `ready` signal reaches a different audience by channel —
  `dine_in` → the table card in the Salón ("🔔 Lista, recoger"); `takeaway` → the no-table strip. For
  `delivery`, readiness **auto-creates the order's delivery record** so it enters Dispatch as
  `pending` (ready to assign a driver) with no manual step; the delivery *run* grouping stays manual.
- **Timers:** from the existing `entered_at`/`ready_at`, surface live times without new backend data —
  per-ticket prep time and per-order "since fired" aging on the KDS (amber/red past **global**
  thresholds), and a "ready / cooling" (dine-in) or "ready / awaiting driver" (delivery) timer on the
  Salón surfaces.
- **Deferred:** a "servida / recogida" action (to stop the cooling timer and capture time-to-table)
  is explicitly out of scope for v1.

## Capabilities

### New Capabilities
- `kitchen-station-roles`: A per (product, station) role that is captured on the ticket at routing
  time and shown on the KDS board and in kitchen setup.
- `kitchen-ready-rollup`: Order-level kitchen readiness derived from its tickets, persisted as
  `Order.kitchen_state`, emitted by a kitchen→orders port when the last ticket is ready, and
  surfaced per channel (Salón table card / no-table strip / Dispatch) with live timers.

### Modified Capabilities
<!-- None: route_order and advance_ticket keep their existing requirements; roles and the
     ready-emit are additive. Order lifecycle requirements are unchanged; kitchen_state is a new
     read-model field, not a change to open/close/cancel behavior. -->

## Impact

- **Backend — kitchen:** `ProductStation` gains `role`; `OrderItemStation` (ticket) gains `role`,
  copied in `route_order`. `advance_ticket`, on reaching the last `ready` ticket of an order, calls a
  new outbound `OrdersReadiness` port (symmetric to the existing `KitchenRouting` port used by
  orders). Endpoints/schemas expose `role`.
- **Backend — orders:** `Order` gains `kitchen_state` (`none | in_kitchen | ready`); a
  `mark_kitchen_ready` / recompute path driven by the port. `add_item` auto-route already re-fires;
  recompute must reset a previously-ready order to `in_kitchen`.
- **Frontend — kitchen:** KDS chit shows `role`; station board shows per-ticket prep + since-fired
  timers with thresholds.
- **Frontend — salón:** table card shows `kitchen_state` (progress `n/total` + 🔔 ready + cooling
  timer); the no-table strip shows delivery/takeaway readiness; optional "Servida" action.
- **Backend — orders→delivery:** when a `delivery` order becomes `ready`, orders auto-creates its
  delivery record via a new outbound port to the delivery module (idempotent, non-blocking), so it
  enters Dispatch as `pending`.
- **Frontend — dispatch:** the auto-created delivery record appears in Dispatch as "listo para
  despachar / asignar" like any pending delivery.
- **Resolved decisions:** delivery auto-creates its record on ready; "servida" action deferred;
  thresholds are global constants. `kitchen_state` is persisted on the order (not computed per read).
  No change to tenancy, auth, or money handling.
