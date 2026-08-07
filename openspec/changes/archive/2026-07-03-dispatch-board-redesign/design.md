## Context

The approved design prototype lives at `/dispatch/design`
(`front/src/views/DispatchDesignView.vue` + `front/src/lib/dispatchDesignMock.ts`): a three-pane
board (stats/filters rail · list · detail) in El Pase styling, with the stop strip as its
signature and KDS-style heat for overdue domicilios. It was deliberately built on the backend's
status vocabulary (`pending/assigned/in_transit/delivered/not_delivered` mapped to Spanish copy,
runs `preparing/in_transit/finished`), so wiring is mostly mechanical.

The wired production screen at `/dispatch` (`DispatchPanel` + `DeliveriesArea` + `RunsArea`) uses
the `dispatch` Pinia store (write-through: every mutation refetches) plus `delivery` (routes),
`staff` (driver names/phones) and `orders` (open orders, order labels) stores.

Backend gaps found during exploration:
- `OrderDeliveryModel` has no `TimestampMixin` → no `created_at`, so "Recibido", elapsed labels
  and heat cannot be computed.
- No `notes` field on deliveries.
- `RunOut` does not expose the run's `created_at` (the column exists via `TimestampMixin`).
- No direct driver-on-delivery assignment (by design: drivers come from runs), no cancel before
  `in_transit`, no run-driver change. The UI adapts to these instead of adding endpoints.

## Goals / Non-Goals

**Goals:**
- The board at `/dispatch` runs entirely on real data with the approved layout and interactions.
- Preserve every existing lifecycle rule and permission gate (`delivery.read` / `delivery.manage` /
  `delivery.assign`) exactly as the current screen enforces them.
- Additive-only backend change: timestamps + notes + exposed `created_at`s.
- Delete the prototype route/mock and the old dispatch components once replaced.

**Non-Goals:**
- Coordinate capture in the delivery form (belongs to the in-progress `delivery-address-picker`
  change, which lands on top of the new form afterwards).
- New lifecycle endpoints (cancel-before-transit, change run driver, unassign). If operations need
  them, that is a future backend change.
- Realtime (SSE) updates for dispatch; the manual "Actualizar" refresh stays.
- Branch scoping of the deliveries/runs lists (they are tenant-wide today; unchanged).

## Decisions

1. **Wire the prototype file, then promote it.** Port `DispatchDesignView.vue` in place to the
   stores, then point `/dispatch` at it, delete `DispatchView.vue` + `components/dispatch/*` +
   `dispatchDesignMock.ts` + the `/dispatch/design` route. Alternative — retrofitting the board
   into the three old components — was rejected: the layout differs structurally (three panes,
   cross-cutting filters, two detail kinds) and the old components would survive only as dead
   wrappers.

2. **Backend: `TimestampMixin` on `OrderDeliveryModel` + `notes` column, one migration.**
   `created_at` backfills naturally (server default `now()`); historical deliveries show "recibido"
   as the migration time, which is acceptable for an operational (today-focused) screen.
   `notes: String(500), nullable` rides the existing PATCH (`update_delivery`) and requires
   `delivery.manage`, same as address edits. Alternative — client-only timestamps — rejected:
   heat/elapsed would reset on every reload and lie across operators.

3. **Timeline steps derive from available timestamps only.** Recibido = `delivery.created_at`;
   Asignado = state-only (no `assigned_at` is stored — the step renders without a time);
   En ruta = the run's `departed_at` (resolved via `delivery_run_id`); Entregado/No entregado =
   `delivered_at`. Alternative — adding an `assigned_at` column — deferred: it serves only one
   timeline row and can ship later without UI changes.

4. **"Asignar a despacho" replaces direct driver assignment.** The unassigned-delivery primary
   action opens a picker of `preparing` runs (plus a shortcut to the two-step "Nuevo despacho"
   modal pre-seeded with that delivery). Moving an `assigned` delivery to another `preparing` run
   reuses the same picker (`assignDelivery` accepts `pending` and `assigned`). The prototype's
   free-floating "driver without run" state disappears — it does not exist server-side.

5. **Heat thresholds stay client-side constants** (warm ≥ 35 min, hot ≥ 50 min since
   `created_at`), matching the KDS approach. Making them per-branch settings is out of scope.

6. **Store evolution, not replacement.** `stores/dispatch.ts` keeps its write-through discipline;
   additions are limited to what the board needs (e.g. a `runsById`/progress helper, loading both
   collections for the stop strip). Stats are computed client-side from the loaded lists — "hoy"
   figures use `created_at` dates, no new endpoints.

## Risks / Trade-offs

- [Deliveries/runs lists are tenant-wide, stats say "hoy"] → compute stats from `created_at`
  client-side; if list volume grows, a future backend change adds date filtering — the UI won't
  change.
- [Old screen deleted in the same change] → the port must reach feature parity on lifecycle flows
  before the swap; tasks order the swap last, after unit tests pass.
- [`delivery-address-picker` touches the same form] → this change keeps the "Nuevo domicilio"
  modal minimal and that change rebases onto it; coordinate in tasks.md of that change, don't
  implement coordinates here.
- [Historical deliveries get `created_at` = migration time] → acceptable: heat/elapsed only
  matter for today's open deliveries; delivered/closed cards don't render heat.

## Migration Plan

1. Backend model + migration + schema fields ship first (additive, deployable alone).
2. Frontend port lands behind the existing `/dispatch/design` route for verification.
3. Route swap: `/dispatch` → new board, `/dispatch/design` removed, old components deleted.
   Rollback = revert the frontend commit; the backend change is additive and safe to keep.

## Open Questions

None blocking. Deferred (explicitly out of scope): `assigned_at` timestamp, cancel-before-transit,
run driver change, SSE realtime.
