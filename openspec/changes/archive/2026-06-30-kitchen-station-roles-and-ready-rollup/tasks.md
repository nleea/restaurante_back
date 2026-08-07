## 1. Timers (frontend-only, ships first — no backend)

- [x] 1.1 Add pure helpers for kitchen time: `elapsedSince(ts, now)`, `prepTime(entered_at, ready_at)`, and a `heatLevel(minutes, {amber, red})` mapping; unit-test with fixed `now`.
- [x] 1.2 KDS chit (`KitchenBoard.vue`): show each ticket's elapsed time since `entered_at`, escalating past amber/red thresholds; degrade gracefully when `entered_at` is null. Drive elapsed from a shared reactive `now` tick, cleared on unmount; respect reduced-motion.
- [x] 1.3 Define default thresholds as documented client constants (e.g. amber 10m, red 15m) in one place.

## 2. Station roles — backend (A)

- [x] 2.1 Add nullable `role` (≤60 chars) to `ProductStation` and to `OrderItemStation` (ticket) entities + models + migration (additive, backward-compatible).
- [x] 2.2 `attach_product_station` accepts and stores `role`; expose set/clear via the existing product-station endpoint(s) and schemas.
- [x] 2.3 `route_order`: copy the mapping's `role` onto each created ticket; keep idempotency (do not rewrite the role of an existing ticket).
- [x] 2.4 Expose `role` on ticket and product-station response schemas.
- [x] 2.5 Backend tests: multi-station product → one ticket per station each with its own role; role frozen when mapping edited after ticket exists; empty role preserved.

## 3. Station roles — frontend (A)

- [x] 3.1 `kitchen.api.ts` / store: add `role` to `ProductStation` and `Ticket` types; thread it through attach/list.
- [x] 3.2 `KitchenSetup.vue`: role input when mapping a product to a station; show role in the mapping list; clearable.
- [x] 3.3 `KitchenBoard.vue`: render the ticket `role` beneath the item label; nothing when empty.
- [x] 3.4 Store/helper tests for role plumbing.

## 4. Ready rollup — backend (B)

- [x] 4.1 Add `kitchen_state` (`none | in_kitchen | ready`, default `none`) to `Order` entity + model + migration.
- [x] 4.2 Implement the readiness derivation over an order's non-cancelled tickets (source of truth) in the kitchen service.
- [x] 4.3 Add an outbound `OrdersReadiness` port (kitchen domain) + adapter wiring to orders (symmetric to the existing `KitchenRouting` port); orders exposes `mark_kitchen_ready(order_id)` / recompute.
- [x] 4.4 `advance_ticket`: when the advanced ticket is the last non-ready ticket of its order, emit readiness as a non-blocking side effect (try/except); ticket advance never fails on notify error.
- [x] 4.5 On `add_item` auto-route, recompute so a previously-`ready` order returns to `in_kitchen`.
- [x] 4.6 Expose `kitchen_state` on the order response schema.
- [x] 4.7 When a `delivery` order becomes `ready`, auto-create its delivery record via a new outbound orders→delivery port (idempotent — skip if a record exists; non-blocking — failure never fails the advance/readiness).
- [x] 4.8 Backend tests: mixed→in_kitchen, all-ready→ready + order flagged, notify-failure still advances, add-item-after-ready→in_kitchen, never-routed→none, delivery-ready→delivery record created once (idempotent), dispatch-create failure still advances.

## 5. Channel fan-out + Salón/Dispatch surfaces — frontend (B)

- [x] 5.1 `orders.api.ts` / store: add `kitchen_state` to `Order`; expose a per-order ready-count (`ready tickets / total`) helper for progress (from kitchen tickets or a lightweight endpoint).
- [x] 5.2 Salón table card (`TableCard`/floor): show in-kitchen progress (`n/total`) while `in_kitchen`, a "🔔 Lista, recoger" state when `ready`, and a "ready since" cooling timer; keep El Pase styling (ready → success/pulse, aging → ember/alert).
- [x] 5.3 Salón no-table strip: show takeaway readiness ("listo para entregar") + a "ready since" timer; show delivery orders' in-kitchen/ready state.
- [x] 5.4 Dispatch surface: the auto-created delivery record (from task 4.7) appears as a `pending` delivery ("listo para asignar"); no new dispatch action needed beyond surfacing it.

> Deferred (out of scope for v1): the "Servida / recogida" action to stop the cooling timer.

## 6. Verify

- [x] 6.1 Confirm the resolved decisions hold in code: delivery ready auto-creates its dispatch record (4.7), "Servida" is not built, thresholds are global constants (1.3).
- [ ] 6.2 End-to-end parity walk: fire hamburguesa → two stations show distinct roles → advance each → order flips to ready → dine-in card shows 🔔; repeat for a delivery order → delivery record auto-created and shows in Dispatch as pending.
- [x] 6.3 `pnpm type-check`, `pnpm exec vitest run`, `pnpm lint` (frontend) and backend test suite pass.
- [x] 6.4 `openspec validate --changes kitchen-station-roles-and-ready-rollup --strict` passes.
