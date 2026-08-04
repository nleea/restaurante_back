# Design: wire-delivery-routes-map

## Context

Gap analysis (explore session, 2026-07-01) established:

- Backend `modules/delivery` already models routes (`DeliveryRouteModel`: name,
  `covered_zones: String(500)` free text, `is_active`, branch-scoped), route↔driver bridge
  (`DeliveryRouteDriverModel` → `employees.id`, unique pair, `is_active`), runs
  (`preparing/in_transit/finished`) and per-order deliveries
  (`pending/assigned/in_transit/delivered/not_delivered`). Endpoints under `/delivery` with
  `delivery.read/manage/assign`.
- Missing for the map: business coordinates (branches have address text only), ring band width,
  route color, structured zones, driver status.
- Frontend: `DeliveryView.vue` (route config, forms) is superseded by the prototype
  (`DeliveryRoutesView.vue` + `components/deliveryroutes/*` + `lib/deliveryRoutes.ts`), which is
  currently mock-only at public `/delivery-routes`. `DispatchView` stays.
- User decisions: **uniform ring step per branch** (one `ring_step_km`, band = route position);
  **location asked first (device geolocation as suggestion), then adjustable by clicking the
  map**.

## Goals / Non-Goals

**Goals:**

- `/delivery` shows the ring map on real data: create/edit/deactivate routes (name, zones,
  color), assign/remove drivers, tune `ring_step_km`, set/relocate the business pin.
- Zero-config first run guided: no settings → onboarding to place the pin; no map until there is
  a center.
- Driver pills reflect reality: `on_route` derived from active runs.

**Non-Goals:**

- No changes to dispatch/lifecycle, runs, per-order deliveries, or their screens.
- No per-route custom radius (uniform step by decision); no polygon/zone geo-shapes — zones stay
  names.
- No route reordering UI in this change (position = creation order; a future drag-to-reorder can
  build on `position`).
- No realtime push here (manual refresh + write-through is enough for a config screen).

## Decisions

### D1 — `delivery_settings`: one row per branch, owned by the delivery module

New model `DeliverySettingModel` (`delivery_settings`): `branch_id` (FK, **unique**),
`latitude`/`longitude` `Numeric(10,7)` **nullable** (no pin yet = onboarding state),
`ring_step_km` `Numeric(4,2)` default `1.0`. Endpoints:

- `GET /delivery/settings?branch_id=` (`delivery.read`) — returns the row, creating the default
  lazily so the frontend always has one shape (null coords = needs onboarding).
- `PATCH /delivery/settings/{id}` or keyed by branch (`delivery.manage`) — partial update of
  coords/step; step clamped to `0.5–5.0`.

*Alternative rejected:* lat/long on `BranchModel` — touches the identity module for a
delivery-only concern and couples modules; the settings row keeps map config where it's consumed.

### D2 — Route map data as columns; zones become a JSON list

`delivery_routes` gains `color` `String(7)` nullable (hex; frontend falls back to its palette by
position when null), `position` `Integer` NOT NULL (band order), and `zones` JSON NOT NULL
default `[]`. Migration backfills: `zones` from `covered_zones` split on commas (trimmed,
empties dropped), `position` sequential per branch by creation order (id order), then **drops
`covered_zones`** — one source of truth, and its only consumer (old DeliveryView) retires in
this same change. API schemas swap `covered_zones: str|null` for `zones: list[str]`
(≤20 zones, each ≤60 chars — same bounded-JSON pattern as recipe steps and station tasks).
New routes take `position = max(position)+1` per branch.

### D3 — Driver status is a read-model derivation

`list_route_drivers` response gains `status: "on_route" | "available" | "inactive"`:
`inactive` when the assignment (or employee) is inactive; `on_route` when the employee has a run
in `preparing/in_transit`; else `available`. One aggregated query in the repository — no new
state, no writes; the dispatch flow already produces the underlying facts. The assign-modal pool
keeps using the staff employees list (as the old view did), decorated with the same derivation
when listed per route.

### D4 — Frontend: the prototype's seed seam becomes the store

`stores/delivery.ts` extends with `settings` + `loadSettings/saveSettings`, routes carrying
`color/zones/position`, and driver lists with status. The prototype view swaps its in-memory
`reactive(seedRoutes())` for store-backed state with write-through (create/update/deactivate
route, assign/remove driver → API then refetch). `lib/deliveryRoutes.ts` keeps the pure ring
math and types; the seed stays for unit tests only. Slider persists `ring_step_km` debounced
(~500 ms) after the drag settles; the map redraws optimistically from local state meanwhile.

### D5 — Location onboarding

When `settings.latitude` is null: the map renders with an onboarding banner ("Marca la ubicación
de tu negocio"), tries `navigator.geolocation` once to center the map as a *suggestion* (denial
is fine — map stays on a country-level default), and the next map click places the pin →
"Guardar ubicación" persists it and the rings appear. Afterwards, a "Reubicar" affordance in the
radius panel re-enters the same pick-on-map mode. The rings never render without a center.

### D6 — Routing and permissions

`/delivery` keeps its name/label and now renders the map view (`requiresAuth`,
`delivery.read`; mutations gated by `delivery.manage` in-UI). The public `/delivery-routes`
route is deleted; old `DeliveryView.vue` and its route-form components are removed. Sidebar
unchanged ("Domicilios" already points here). `AppShell` wraps the view like other authed
screens.

## Risks / Trade-offs

- [Dropping `covered_zones` is destructive] → the migration backfills `zones` first in the same
  revision; downgrade re-serializes `zones` back to a comma-joined string.
- [Ring semantics change meaning of existing routes] → bands derive from creation order, which
  matches how the seed data was entered; reordering is a future change on top of `position`.
- [Geolocation prompt may be denied/unavailable] → it is only a centering suggestion; the pin is
  always placed by map click, so onboarding never blocks on the permission.
- [Slider writes per drag could spam the API] → debounce, and only PATCH when the value settled
  and differs.
- [Prototype `DeliveryRoute` type vs API `Route` type name clash in front] → the adapter layer
  maps API rows into the prototype's view types in one place (`stores` → view props), mirroring
  the KDS adapter seam.

## Migration Plan

1. Migration `0008_delivery_settings_and_route_map_data`: create `delivery_settings`; add
   `color`/`position`/`zones` to `delivery_routes`; backfill zones + position; drop
   `covered_zones`. `alembic upgrade head` on deploy.
2. Deploy backend, then frontend (old frontend won't send `covered_zones` writes anymore once
   swapped; the window between deploys only affects the route-edit form, acceptable in dev).
3. First visit per branch walks the location onboarding.
4. Rollback: revert frontend; backend downgrade restores `covered_zones` from `zones`.

## Open Questions

- None blocking. (Drag-to-reorder ring bands and zone polygons noted as future work.)
