## Context

The kitchen module (KDS) routes an order's items to stations via a `route_order` use case: for each
item, `variant → product → ProductStation[]`, creating one ticket (`OrderItemStation`) per station,
each advancing `pending → in_progress → ready` independently. Routing is idempotent and is fired
automatically when an item is added (orders' `add_item` calls an optional outbound `KitchenRouting`
port; the adapter lives in `orders/.../deps.py`). Tickets carry only `order_item_id`; the frontend
resolves labels/table/channel via an `itemIndex` built from the menu + open orders. Tickets already
store `entered_at` and `ready_at`.

Three gaps motivated this change (from exploration):
1. A multi-station product (hamburguesa → Parrilla + Fríos) shows the same bare product name at both
   stations; no station is told which part it owns.
2. Station readiness never rolls up: each ticket's `ready` dies at the station; neither the waiter
   (dine-in) nor Dispatch (delivery) learns the food is up.
3. `entered_at`/`ready_at` exist but no time is ever shown.

## Goals / Non-Goals

**Goals:**
- Tell each station what it does for a product (role), captured at fire time.
- Derive an order-level kitchen readiness and push it to the audience that acts on it, per channel.
- Show prep/wait/cooling timers from data that already exists — no new timestamps.
- Reuse the existing outbound-port pattern; keep routing/advance behavior intact.

**Non-Goals:**
- Recipe/component-level routing (splitting a product into ingredient tickets) — explicitly out.
- A real "expo/assembly" station entity — the rollup gives an order-centric view without one.
- Inter-station sequencing/dependencies (all tickets remain independent, born `pending` together).
- Auto-creating delivery runs from a ready order — surfaced as an open question.

## Decisions

- **Role is denormalized onto the ticket at routing time** (not resolved live from the mapping). The
  role is an *instruction fixed when the dish is fired*; later edits to config must not rewrite chits
  already on the line. This mirrors how the order captures per-item `unit_price` at add time.
  *Alternative:* resolve role live from `ProductStation` (like the client resolves labels) — rejected
  because config edits would retroactively change in-flight chits.
- **Persist `Order.kitchen_state` (`none|in_kitchen|ready`) rather than compute on every read.** The
  Salón and Dispatch read many orders per render; a stored field is O(1) to read and avoids each
  surface cross-querying kitchen tickets. The risk (drift) is contained because the value is only
  written by the kitchen→orders port and recomputed on add-item, and can be rebuilt from tickets if
  ever needed. *Alternative:* pure derivation on read (always correct, no drift) — rejected for the
  read cost and cross-module coupling on every list; the derivation still exists as the source of
  truth the port applies.
- **A new outbound `OrdersReadiness` port, symmetric to `KitchenRouting`.** Kitchen already depends
  on orders indirectly; giving it a thin outbound port (`mark_ready(order_id)` / `recompute`) keeps
  the dependency one-way and matches the established pattern instead of inventing a new mechanism.
- **Readiness is emitted only on the transition to all-ready**, computed inside `advance_ticket`
  ("is this the last non-ready ticket of the order?"). The emit is a non-blocking side effect
  (try/except), exactly like the orders→kitchen auto-route, so the board never breaks on a
  cross-module hiccup.
- **Channel fan-out is mostly a frontend routing of one field, with one backend action for delivery.**
  The backend sets `kitchen_state`; the UI decides the audience: `dine_in` → table card;
  `takeaway` → no-table strip. For `delivery`, readiness additionally triggers a backend action (see
  next decision) so the order reaches Dispatch without a human step.
- **A ready `delivery` order auto-creates its delivery record (resolved).** When `kitchen_state`
  becomes `ready` on a `delivery` order, orders SHALL create that order's delivery record via an
  outbound port to the delivery module (idempotent — do nothing if one already exists), so it enters
  Dispatch as `pending`, ready to assign a driver. Creating/grouping the actual delivery *run* stays a
  manual dispatch action. This is the same non-blocking outbound-port pattern; a delivery-create
  failure SHALL NOT fail the ticket advance or the readiness update.
- **Timers are frontend-only, from `entered_at`/`ready_at`.** A shared reactive `now` tick (as the
  prototype floor used) drives elapsed calculations; thresholds are client constants to start. No
  backend change for timers — this is the cheapest, highest-visibility slice and can ship first.

## Risks / Trade-offs

- **`kitchen_state` drift vs. tickets** → Mitigation: single writer (the port) + recompute on
  add-item; treat tickets as source of truth and support a rebuild. Add a test that add→ready→add
  cycles keep the field honest.
- **`itemIndex` only covers open orders** → the ready rollup and role display rely on ticket data +
  index; a closed order with tickets still on the board degrades labels. Mitigation: readiness is
  computed from tickets (not the index), so the rollup stays correct even when labels degrade.
- **Threshold semantics are guesses** → amber/red minutes are product decisions; ship as constants,
  make configurable later. Log/annotate the chosen defaults.
- **Delivery handoff scope creep** → surfacing "ready to dispatch" is cheap; auto-creating a delivery
  run couples kitchen→delivery. Keep to a visible handoff for v1 (open question below).
- **Backend migration** → `ProductStation.role`, `OrderItemStation.role`, `Order.kitchen_state` are
  additive nullable/defaulted columns; safe, backward-compatible.

## Migration Plan

1. Backend kitchen: add `role` to `ProductStation` + `OrderItemStation`; copy role in `route_order`;
   add `OrdersReadiness` outbound port + adapter; emit on last-ready in `advance_ticket`.
2. Backend orders: add `Order.kitchen_state`; implement `mark_ready`/recompute; ensure add-item route
   recomputes to `in_kitchen`; expose `kitchen_state` and ticket/mapping `role` in schemas.
3. Frontend kitchen: show `role` on the chit; add prep/aging timers (frontend-only) from timestamps.
4. Frontend salón: table card progress + ready chip + cooling timer; no-table strip readiness;
   optional "Servida" action; Dispatch "ready to dispatch".
5. Sequence for value-first delivery: timers (no backend) → roles (A) → rollup + fan-out (B).

Rollback: columns are additive and nullable; dropping the port/emit and hiding the UI reverts
behavior with no data loss.

## Open Questions (resolved)

- **Auto-create delivery run/record?** → RESOLVED: **yes, immediately.** A `ready` delivery order
  auto-creates its delivery record (enters Dispatch as `pending`, ready to assign) via the orders→delivery
  outbound port. The delivery *run* grouping stays manual in Dispatch.
- **Ship "Servida / recogida" now?** → RESOLVED: **deferred.** v1 shows the cooling / awaiting-driver
  timer but no "served" action; the timer keeps running until the order is closed. Time-to-table
  capture is a follow-up.
- **Thresholds global or configurable?** → RESOLVED: **global constants** for v1 (documented in one
  place); per-station/branch configuration is a future enhancement.
