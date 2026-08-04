# Tasks: wire-kds-to-kitchen

## 1. Generalize KDS types to dynamic stations

- [x] 1.1 Replace the closed `Station` union in `front/src/lib/kds/types.ts` with a station id
      string plus a `StationMeta` shape (id, label, tag, waitMin); keep status/severity types and
      timing constants as-is
- [x] 1.2 Add station-meta derivation helpers (two-letter tag from name with deterministic
      uniquify on collision; `waitMin` lookup by normalized name with global default) with unit
      tests
- [x] 1.3 Update `lib/kds/logic.ts` and its spec to consume `StationMeta` instead of the enum
      (`STATION_META` lookup replaced by injected meta); all existing logic tests still pass
- [x] 1.4 Confine `lib/kds/seed.ts` to dev/test usage (seed builds mock stations through the new
      meta helpers)

## 2. Store: whole-board tickets + polling

- [x] 2.1 Add `loadAllTickets()` to `front/src/stores/kitchen.ts`: fan-out `listTickets` over
      active stations, merge into state keyed for group-by-order and filter-by-station
- [x] 2.2 Point write-through refetches (advance, route) at the merged board load so mutations
      refresh the whole board
- [x] 2.3 Add polling control to the store (start/stop, ~10 s cadence, skip-if-in-flight, keep
      last good data on failure)
- [x] 2.4 Store unit tests: merged multi-station load, write-through refetch, poll skip/failure
      behavior

## 3. Adapter: tickets → KDS view model

- [x] 3.1 Create `front/src/lib/kds/adapter.ts`: group tickets by order into `KdsOrder[]`
      (1 ticket = 1 item with 1 component; status map pending/in_progress/ready →
      pending/cooking/done; `startedAt = min(entered_at)`, `doneAt = ready_at`; table/channel
      from `itemIndex`; label degrade to short ticket reference)
- [x] 3.2 Adapter unit tests: grouping, status mapping, timestamp mapping, unresolvable-label
      fallback, order readiness rollup (all tickets ready)

## 4. Wire the KDS UI

- [x] 4.1 Rework `useKdsBoard.ts` to consume the kitchen store through the adapter instead of the
      seed; expose the same view state (filters, expo, my-station, clock) plus real actions
- [x] 4.2 Component tap advances forward only (no-op on `done`); actions gated by
      `kitchen.update`
- [x] 4.3 Implement docket bump: advance every non-ready ticket of the order to `ready`
      (sequential advance calls), disabled while in flight, single refetch after
- [x] 4.4 Drive `KdsStationRail.vue` and station filters from DB stations via `StationMeta`
- [x] 4.5 Hide recipe affordances (drawer + buttons) behind a single flag, off in production

## 5. Screen swap

- [x] 5.1 Replace the pass area of `front/src/views/KitchenView.vue` with the KDS board
      composition (top bar, rail, dockets, expo, my-station); keep configuración and ruteo tabs
      working unchanged
- [x] 5.2 Start/stop store polling from the board (mount/unmount, hidden tab); keep a manual
      refresh affordance in the top bar
- [x] 5.3 Retire `front/src/components/kitchen/KitchenBoard.vue` and its presentation tests;
      migrate any still-relevant assertions to the new composition
- [x] 5.4 Dev-gate or remove the mock `/kds` route in the router

## 6. Validation

- [x] 6.1 `npm run type-check`, unit tests, and build all green in `front/`
- [x] 6.2 Cypress/visual pass on `/kitchen`: dockets with real data, rail counts, advance/bump,
      expo panel, my-station mode, read-only rendering without `kitchen.update`
- [x] 6.3 Manual end-to-end against dev backend: route an order, watch it appear via polling,
      advance components, bump, verify orders-side `kitchen_state` flips to ready
