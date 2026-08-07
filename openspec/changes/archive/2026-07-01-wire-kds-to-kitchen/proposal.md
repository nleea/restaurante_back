# Proposal: wire-kds-to-kitchen

## Why

A modern KDS UI prototype (order dockets with per-component status, station rail with live
metrics, expo alert panel, my-station list mode, live clock) was built and validated at `/kds`,
but it runs entirely on mock data. Meanwhile the production kitchen screen (`/kitchen`) is
functionally correct but visually dated and only refreshes on a manual button press. This change
replaces the production kitchen board with the KDS UI wired to real backend data, so cooks get
the modern screen without waiting for future backend work (dish→component decomposition, recipes,
realtime push).

## What Changes

- The cook-facing board at `/kitchen` is replaced by the KDS UI (dockets, station rail, expo
  panel, my-station mode, top bar) fed by real tickets from the existing kitchen store — the
  mock seed is no longer used in production.
- A frontend adapter translates real tickets (`order_item × station`, labels resolved via the
  store's item index) into the KDS view model; phase 1 maps **1 ticket = 1 KDS component** (no
  dish decomposition — that is a future backend change).
- Dynamic DB stations replace the KDS prototype's fixed 6-station enum: two-letter tag derived
  from the station name, cold-hold threshold (`waitMin`) becomes a frontend config with a default.
- Status cycling conforms to the forward-only backend: `pending → in_progress → ready`, no reset
  back to pending; a docket "bump" advances all of the order's remaining tickets via the existing
  advance endpoint.
- Order-level readiness ("all components ready") is derived client-side from the order's tickets.
- The recipe drawer is hidden (no backend data source yet).
- The board auto-refreshes by polling (~10 s) replacing the manual "Actualizar" button as the
  primary refresh path.
- The mock `/kds` route is removed from production navigation (dev-only or deleted).
- Setup (stations, product mapping) and routing ("Enviar a cocina") remain available from the
  kitchen screen, restyled at most — their behavior does not change.
- **No backend changes.**

## Capabilities

### New Capabilities

_None — this modernizes an existing frontend capability._

### Modified Capabilities

- `frontend-kitchen`: the cook-facing board requirements change — KDS docket presentation with
  per-item alert severity, station filter rail with live metrics, expo panel, my-station list
  mode, order-level ready rollup and bump action, automatic polling refresh, dynamic station
  tags. Service layer, setup, routing, label resolution, and permission gating requirements are
  unchanged.

## Impact

- **Frontend only**: `front/src/views/KitchenView.vue` (replaced by KDS composition),
  `front/src/components/kds/*` (wired to real data, recipe affordances hidden),
  `front/src/components/kitchen/KitchenBoard.vue` (retired), `front/src/lib/kds/*` (types
  generalized to dynamic stations; seed confined to dev/tests), new adapter module,
  `front/src/stores/kitchen.ts` (multi-station ticket loading + polling), router (`/kds` mock
  route removed/dev-gated).
- **No API, schema, or backend changes.** Existing endpoints (`listTickets`, `advanceTicket`,
  `routeOrder`, station CRUD) are consumed as-is.
- Existing tests for `KitchenBoard` presentation will be replaced by adapter + KDS-with-real-data
  tests; `lib/kds/logic.ts` unit tests remain valid.
