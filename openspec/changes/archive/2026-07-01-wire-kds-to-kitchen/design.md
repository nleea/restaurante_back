# Design: wire-kds-to-kitchen

## Context

Two parallel kitchen frontends exist today:

- **Production** (`/kitchen`): `KitchenView.vue` + `KitchenBoard.vue`, fed by `stores/kitchen.ts`
  → `services/kitchen.api.ts`. A ticket is one `order_item × station` row
  (`pending|in_progress|ready`, `entered_at`, `ready_at`). Labels, quantity, table and channel
  are resolved client-side via the store's `itemIndex` (menu + open orders join). One station's
  tickets are loaded at a time; refresh is a manual button.
- **Prototype** (`/kds`): `views/KdsView.vue` + `components/kds/*` + `lib/kds/{types,logic,seed}.ts`
  + `useKdsBoard.ts`, entirely mock. Model: `KdsOrder → KdsItem → KdsComponent(station, status,
  doneAt)`, fixed 6-station enum, pure alert/severity logic driven by timestamps. The wiring seam
  is already annotated in `useKdsBoard.ts`.

The mapping is clean: `ticket.status` ↔ component status, `entered_at`/`ready_at` feed
`logic.ts` unchanged. The gap is purely shape (enum stations, per-dish components) and freshness
(no polling).

## Goals / Non-Goals

**Goals:**

- Cooks see the KDS UI at `/kitchen`, showing real tickets, with working advance/bump actions.
- Board data refreshes automatically (~10 s polling) with the manual refresh retained.
- Dynamic DB stations drive the rail/filters; no hardcoded station enum in production paths.
- Preserve the existing service layer, setup (stations/mapping), routing tab, label-resolution
  fallback, and permission gating exactly as specified today.

**Non-Goals:**

- No backend changes: no dish→component decomposition, no recipes/allergens endpoint, no
  order-bump endpoint, no websocket/SSE, no board-response enrichment.
- No un-advance/recall (backend is forward-only).
- No changes to orders-side `kitchen_state` behavior (backend rollup stays as is).

## Decisions

### D1 — Adapter over rewrite

A pure module `front/src/lib/kds/adapter.ts` converts store state (tickets across stations +
`itemIndex` + stations list) into `KdsOrder[]`. KDS visual components and `logic.ts` stay
untouched and keep their unit tests. *Alternative rejected:* teaching KDS components to consume
`Ticket` directly — touches every visual component and forfeits the tested pure-logic layer.

Mapping rules:

- Group tickets by order id → one `KdsOrder` per order. `startedAt = min(entered_at)`,
  `table`/`type` from `itemIndex` (channel/tableNumber), waiter/guests omitted (not available).
- **1 ticket = 1 `KdsItem` with exactly 1 `KdsComponent`** (name = resolved label, station =
  ticket's station, `doneAt = ready_at`). Unresolvable labels degrade to the short ticket
  reference (existing spec behavior).
- Status map: `pending→pending`, `in_progress→cooking`, `ready→done`.

### D2 — Dynamic stations

`Station` stops being a closed union in production paths; the adapter emits the station's DB id
and a `StationMeta` computed per branch: label = station name, tag = first two significant
letters of the name uppercased (uniquified on collision by swapping the second letter), `waitMin`
= lookup in a small frontend config keyed by normalized name with a global default. The mock
seed/enum survive only for dev/tests. *Alternative rejected:* per-station `waitMin` column in DB
— backend change, not needed to ship the UI.

### D3 — Multi-station load + polling in the store

The board shows all stations at once, so `stores/kitchen.ts` gains `loadAllTickets()` (fan-out
`listTickets(stationId)` over active stations, merged into state) and a 10 s poll started by the
board and stopped on unmount/hidden tab. Overlapping polls are skipped (in-flight guard); a
failed poll keeps the last good data and retries next tick. Mutations stay **write-through**
(refetch after success), per the existing spec. *Alternative rejected:* polling inside
`useKdsBoard` with its own fetch layer — duplicates store logic and bypasses the write-through
contract.

### D4 — Forward-only actions

Component tap: `pending → in_progress → ready` via `advanceTicket`; tapping a `done` component is
a no-op (no reset). Docket **bump** = for each non-ready ticket of the order, call advance until
`ready` (two calls for a `pending` ticket), then refetch once; the button is disabled while in
flight. Order-level "ready" (rollup) is derived client-side: all of the order's tickets `ready`.
*Alternative rejected:* new backend bump endpoint — out of scope by decision.

### D5 — Composition of the screen

`KitchenView.vue` keeps its three areas — **pass / configuración / ruteo** — but the pass area
renders the KDS board (top bar, rail, dockets, expo, my-station) instead of `KitchenBoard.vue`,
which is retired. Setup and routing components remain functionally unchanged. The recipe drawer
and its affordances are not rendered (single flag in the KDS view layer, so re-enabling later is
one switch). The mock `/kds` route is `import.meta.env.DEV`-gated. Permission gating is
unchanged: route needs `kitchen.read`; advance/bump/setup/route actions render only with
`kitchen.update`.

## Risks / Trade-offs

- [One request per station per poll] → only active stations, 10 s cadence, skip-if-in-flight;
  acceptable at current station counts (≤ ~8/branch).
- [Bump issues several sequential advances; partial failure possible] → write-through refetch
  shows true server state after any failure; button disabled during flight; no client-side
  optimistic state to un-wind.
- [Labels depend on menu + open orders being loaded] → same dependency as today; adapter reuses
  the existing degrade-to-reference fallback.
- [Two-letter tags can collide or read oddly for arbitrary names] → deterministic uniquify; label
  always shown alongside in rail tooltips.
- [1 ticket = 1 component under-uses the KDS component UI] → accepted for phase 1; the UI renders
  identically, and a future `kitchen-item-components` change fills the split without UI rework.

## Migration Plan

Pure frontend swap, no data migration. Ship order: adapter + store additions (tested) → KitchenView
pass-area swap → retire `KitchenBoard.vue` and its presentation tests → dev-gate `/kds`.
Rollback = revert the view swap commit; store additions are additive and harmless.

## Open Questions

- Default `waitMin` value and which station names get overrides — pick pragmatic defaults
  (mirror the prototype's values for matching names), tune with kitchen feedback.
